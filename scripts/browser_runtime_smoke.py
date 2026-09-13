#!/usr/bin/env python3
"""Optional browser smoke for the derived Pro runtime without network access.

The test injects a deterministic in-page fetch stub before PromptMaster code is
executed. It validates the 34-app server catalog bridge, task rendering,
server-compose payload and deliberate rating/feedback flow.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'backend/private_assets/promptmaster_pro_runtime.html'
DATA = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'


def mock_catalog() -> dict:
    data = json.loads(DATA.read_text(encoding='utf-8'))
    apps = []
    access = data.get('ACCESS_RULES') or {}
    task_access = data.get('TASK_ACCESS_RULES') or {}
    for sort_order, (code, app) in enumerate((data.get('APP') or {}).items()):
        tasks = []
        for task in app.get('tasks') or []:
            tasks.append({
                'id': task['id'], 'title': task.get('title') or task['id'], 'intent': task.get('intent') or '',
                'required': task.get('required') or [], 'optional': task.get('optional') or [],
                'area': task.get('area') or '', 'family': task.get('family') or 'analysis',
                'sources': task.get('sources') or [], 'outputs': task.get('outputs') or [],
                'focus': task.get('focus') or [], 'audiences': task.get('audiences') or [],
                'access': task.get('access'), 'status': task.get('status') or app.get('status') or '',
                'maxChars': task.get('maxChars'), 'prompt_version': 1, 'policy_version': 1,
                'minimum_tier_rank': int((task_access.get(task['id']) or {}).get('tier', 0)),
                'promptmaster_entitled': True,
            })
        apps.append({
            'code': code, 'name': app.get('name') or code, 'group': app.get('group') or 'm365',
            'icon': app.get('icon') or '', 'color': app.get('color') or '#0c71c3',
            'copy': app.get('copy') or '', 'access': app.get('access') or '',
            'status': app.get('status') or '', 'target': app.get('target') or app.get('name') or code,
            'rule': app.get('rule') or '', 'evidence': app.get('evidence') or [], 'sort_order': sort_order,
            'minimum_tier_rank': int((access.get(code) or {}).get('tier', 0)),
            'promptmaster_entitled': True, 'tasks': tasks,
        })
    return {
        'product_code': 'PRO', 'policy_version': 1, 'source_labels': data.get('SRC_LABEL') or {},
        'application_count': len(apps), 'task_count': sum(len(app['tasks']) for app in apps),
        'applications': apps,
    }


def injected_fetch(catalog: dict) -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False).replace('</', '<\\/')
    return f"""<script>
window.__pmSmokeCompose=[]; window.__pmSmokeRatings=[];
window.fetch=async function(url, options){{
  const u=String(url); const method=String(options?.method||'GET').toUpperCase();
  const jsonResponse=(payload,status=200)=>new Response(JSON.stringify(payload),{{status,headers:{{'Content-Type':'application/json'}}}});
  if(u.includes('/api/v1/prompts/?product=PRO')) return jsonResponse({{'ok':true,'catalog':{catalog_json}}});
  if(u.endsWith('/api/v1/prompts/compose/') && method==='POST'){{
    const body=JSON.parse(options?.body||'{{}}'); window.__pmSmokeCompose.push(body);
    return jsonResponse({{'ok':true,'result':{{'prompt':'SERVER TEST PROMPT','ready':true,'progress_percent':100,'task_id':body.task_id,'app_code':'copilot_chat','policy_version':1,'prompt_version':1,'persisted':false}}}});
  }}
  if(u.includes('/rating/') && method==='POST'){{
    const body=JSON.parse(options?.body||'{{}}'); window.__pmSmokeRatings.push(body);
    return jsonResponse({{'ok':true,'rating':{{'stars':body.stars,'feedback_saved':!!body.feedback,'quality_status':'OK','recent_average':'4.50','rating_count':2}}}});
  }}
  return jsonResponse({{'ok':false,'error':{{'message':'unexpected '+u}}}},404);
}};
</script>"""


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(f'BROWSER SMOKE SKIPPED: playwright fehlt ({exc})')
    executable = os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
    catalog = mock_catalog()
    if (catalog['application_count'], catalog['task_count']) != (34, 194):
        raise SystemExit('BROWSER SMOKE FAIL: catalog count drift')
    html = RUNTIME.read_text(encoding='utf-8')
    # Prevent all asset network access and inject the mocked API before product JS.
    html = html.replace('https://netstyle.de/public_pictures/netstyle%20Logo%20OHNE%20Netz%20FREIGESTELLT.png', 'data:image/gif;base64,R0lGODlhAQABAAAAACw=')
    html = html.replace('</head>', injected_fetch(catalog) + '</head>', 1)

    with sync_playwright() as pw:
        launch_kwargs = {'headless': True, 'args': ['--no-sandbox']}
        if executable:
            launch_kwargs['executable_path'] = executable
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_content(html, wait_until='domcontentloaded')
        page.wait_for_function("document.querySelectorAll('#catalog .app-card').length === 34")
        app_ids = page.locator('#catalog .app-card').evaluate_all("els => els.map(e => e.dataset.app)")
        if len(app_ids) != 34 or len(set(app_ids)) != 34:
            raise AssertionError(f'expected 34 unique app cards, got {len(app_ids)}/{len(set(app_ids))}')
        if 'power_automate' not in app_ids or 'github_copilot' not in app_ids:
            raise AssertionError('expanded 34-app catalog is not visible')

        page.locator('[data-app="copilot_chat"]').click()
        page.wait_for_function("document.querySelectorAll('#taskGrid [data-task]').length === 5")
        page.locator('[data-task="PM20-001"]').click()
        page.locator('.task-input').first.fill('Wie verbessern wir den Support?')
        page.wait_for_function("document.querySelector('#promptOutput').value === 'SERVER TEST PROMPT'")
        compose_bodies = page.evaluate('window.__pmSmokeCompose')
        if not compose_bodies or compose_bodies[-1].get('task_id') != 'PM20-001':
            raise AssertionError('server compose was not called for PM20-001')
        if compose_bodies[-1].get('input', {}).get('fields', {}).get('Fragestellung') != 'Wie verbessern wir den Support?':
            raise AssertionError('required field did not reach compose payload')

        page.locator('#pmRatingButton').click()
        page.locator('[data-pm-stars="2"]').click()
        page.wait_for_function("!document.querySelector('#pmFeedback').classList.contains('hidden')")
        page.locator('#pmFeedbackText').fill('Mehr Kontext wäre hilfreich.')
        page.locator('#pmFeedbackSend').click()
        page.wait_for_function("document.querySelector('#pmRatingState').textContent.includes('gespeichert')")
        ratings = page.evaluate('window.__pmSmokeRatings')
        if not ratings or ratings[-1].get('feedback') != 'Mehr Kontext wäre hilfreich.':
            raise AssertionError('optional low-rating feedback was not sent')
        browser.close()

    print('BROWSER RUNTIME SMOKE OK: 34-app central catalog + compose + rating/feedback bridge')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
