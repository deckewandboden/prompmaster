#!/usr/bin/env python3
"""Read-only production browser acceptance for the public PROMPTFINISHER Free V2 surface.

Runs on GitHub-hosted CI; no SSH, local Windows scripts, login, checkout or
production mutations. PR CI verifies proposed code separately; this script
reports the *currently deployed* public site, not the PR's deployment status.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ORIGIN = "https://promptmaster.decke-wand-boden.de"
URL = ORIGIN + "/free/"
EXPECTED = {
  "hero": {
    "de": "Sag Copilot genauer, was du brauchst.",
    "en": "Tell Copilot exactly what you need.",
    "es": "Dile a Copilot exactamente qué necesitas.",
    "pt": "Diga ao Copilot exatamente do que precisa.",
    "tr": "Copilot'a neye ihtiyacınız olduğunu açıkça söyleyin.",
    "ru": "Объясните Copilot, что именно вам нужно.",
    "pl": "Powiedz Copilotowi dokładnie, czego potrzebujesz.",
    "fr": "Dites précisément à Copilot ce dont vous avez besoin.",
    "it": "Spiega a Copilot esattamente di cosa hai bisogno.",
    "nl": "Vertel Copilot precies wat je nodig hebt."
  },
  "progress": {
    "de": "Fortschritt",
    "en": "Progress",
    "es": "Progreso",
    "pt": "Progresso",
    "tr": "İlerleme",
    "ru": "Прогресс",
    "pl": "Postęp",
    "fr": "Progression",
    "it": "Avanzamento",
    "nl": "Voortgang"
  },
  "tone": {
    "de": "Professionell",
    "en": "Professional",
    "es": "Profesional",
    "pt": "Profissional",
    "tr": "Profesyonel",
    "ru": "Профессиональный",
    "pl": "Profesjonalny",
    "fr": "Professionnel",
    "it": "Professionale",
    "nl": "Professioneel"
  },
  "modal": {
    "de": "Funktionsvergleich & zusätzliche Anwendungen",
    "en": "Feature comparison & additional applications",
    "es": "Comparación de funciones y aplicaciones adicionales",
    "pt": "Comparação de funcionalidades e aplicações adicionais",
    "tr": "Özellik karşılaştırması ve ek uygulamalar",
    "ru": "Сравнение возможностей и дополнительные приложения",
    "pl": "Porównanie funkcji i dodatkowe aplikacje",
    "fr": "Comparatif des fonctions et applications supplémentaires",
    "it": "Confronto delle funzionalità e applicazioni aggiuntive",
    "nl": "Functievergelijking en extra toepassingen"
  },
  "close": {
    "de": "Schließen",
    "en": "Close",
    "es": "Cerrar",
    "pt": "Fechar",
    "tr": "Kapat",
    "ru": "Закрыть",
    "pl": "Zamknij",
    "fr": "Fermer",
    "it": "Chiudi",
    "nl": "Sluiten"
  }
}
ARTIFACTS = Path("browser-artifacts/live-locale")
ARTIFACTS.mkdir(parents=True, exist_ok=True)
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def inspect(page):
    """Read the *rendered, visible* V2 DOM, never the hidden Golden Master text."""
    return page.evaluate("""() => {
      const one = s => document.querySelector(s);
      const visible = el => Boolean(el && el.getClientRects().length &&
        getComputedStyle(el).display !== 'none' &&
        getComputedStyle(el).visibility !== 'hidden');
      const hero = one('.pmv2-hero-copy h1');
      const progress = one('.pmv2-progress-host .progress-line span');
      const legacyTitle = one('.pmv2-progress-host .hero-card-title');
      const modal = one('#generalProModal');
      return {
        htmlLang: document.documentElement.lang,
        localeCode: window.PF_PRODUCT_LOCALE?.code || '',
        selected: one('select[data-pf-product-language]')?.value || '',
        v2Ready: document.body.dataset.pmv2Ready === '1',
        hero: hero?.textContent.trim() || '',
        heroVisible: visible(hero),
        progress: progress?.textContent.trim() || '',
        progressVisible: visible(progress),
        configExists: Boolean(one('#pmv2ConfigScroll')),
        configSteps: document.querySelectorAll('#pmv2ConfigScroll > .pmv2-section').length,
        legacyTitleExists: Boolean(legacyTitle),
        legacyTitleVisible: visible(legacyTitle),
        tone: one('#toneSelect option[value="professional"]')?.textContent.trim() || '',
        modalTitle: modal?.querySelector('.modal-head h2')?.textContent.trim() || '',
        modalClose: modal?.querySelector('[data-close="generalProModal"]')?.textContent.trim() || '',
      };
    }""")


def run():
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for lang in EXPECTED["hero"]:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    service_workers="block",
                    ignore_https_errors=False,
                )
                context.add_cookies([{
                    "name": "promptfinisher_language",
                    "value": lang,
                    "url": ORIGIN,
                    "sameSite": "Lax",
                }])
                blocked = []

                def read_only(route):
                    method = route.request.method.upper()
                    if method not in READ_METHODS:
                        blocked.append(method + " " + route.request.url.split("?")[0])
                        route.abort("blockedbyclient")
                    else:
                        route.continue_()

                context.route("**/*", read_only)
                page = context.new_page()
                entry = {"language": lang, "result": "FAIL", "checks": {}}
                try:
                    response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
                    if response is None or response.status != 200:
                        raise AssertionError("HTTP status: " + str(response.status if response else None))
                    page.wait_for_function(
                        """() => document.body.dataset.pmv2Ready === '1' &&
                         window.PF_PRODUCT_LOCALE?.code === document.documentElement.lang &&
                         document.querySelector('.pmv2-progress-host .progress-line span')?.textContent?.trim()""",
                        timeout=30000,
                    )
                    page.locator("#generalProModal").evaluate("(el) => el.classList.add('open')")
                    page.wait_for_function(
                        """() => document.querySelector('#generalProModal.open .modal-head h2')?.textContent?.trim()""",
                        timeout=8000,
                    )
                    state = inspect(page)
                    checks = {
                        "html_lang": state["htmlLang"] == lang,
                        "js_locale": state["localeCode"] == lang,
                        "selector": state["selected"] == lang,
                        "v2_ready": state["v2Ready"],
                        "visible_hero": state["heroVisible"] and state["hero"] == EXPECTED["hero"][lang],
                        "visible_progress": state["progressVisible"] and state["progress"] == EXPECTED["progress"][lang],
                        "config_layout": state["configExists"] and state["configSteps"] >= 5,
                        "hidden_legacy_title": state["legacyTitleExists"] and not state["legacyTitleVisible"],
                        "professional_tone": state["tone"] == EXPECTED["tone"][lang],
                        "visible_modal_title": state["modalTitle"] == EXPECTED["modal"][lang],
                        "visible_modal_close": state["modalClose"] == EXPECTED["close"][lang],
                        "no_mutation_request": not blocked,
                    }
                    entry.update(
                        checks=checks,
                        actual=state,
                        blocked_methods=blocked,
                        result="PASS" if all(checks.values()) else "FAIL",
                    )
                    if entry["result"] != "PASS":
                        page.screenshot(path=str(ARTIFACTS / (lang + "-failure.png")))
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ": " + str(exc)[:500]
                    entry["blocked_methods"] = blocked
                    try:
                        page.screenshot(path=str(ARTIFACTS / (lang + "-error.png")))
                    except Exception:
                        pass
                finally:
                    context.close()
                results.append(entry)
                status = entry["result"]
                failures = [key for key, ok in entry["checks"].items() if not ok]
                print(
                    f"R5_PROD_FREE_LANG={lang};RESULT={status};FAILED_CHECKS={','.join(failures) or '-'}",
                    flush=True,
                )
        finally:
            browser.close()

    passing = sum(item["result"] == "PASS" for item in results)
    report = {
        "mode": "READ_ONLY",
        "url": URL,
        "tested": len(results),
        "pass_count": passing,
        "result": "PASS" if passing == 10 else "REVIEW_REQUIRED",
        "results": results,
        "scope": "Public production Free only; Pro and authenticated backends separately tested in isolated CI.",
    }
    (ARTIFACTS / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"R5_PRODUCTION_LIVE_PASS_COUNT={passing}/10")
    print("R5_PRODUCTION_LIVE_RESULT=" + report["result"])
    return 0 if passing == 10 else 2


if __name__ == "__main__":
    sys.exit(run())
