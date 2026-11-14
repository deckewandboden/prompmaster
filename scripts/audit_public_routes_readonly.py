#!/usr/bin/env python3
"""Anonymous HTTPS GET-only public route and access-boundary acceptance.

No login, POST, browser storage, payment, email, user account or server writes.
Never follow redirects outside the configured first-party production origin.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = "https://promptmaster.decke-wand-boden.de"
HOST = urlsplit(BASE).netloc
OUT = Path("browser-artifacts/public-route-check")
PUBLIC_HTML = (
    "/", "/preise/", "/vergleich/", "/checkout/", "/unternehmen/", "/kontakt/",
    "/auth/login/", "/auth/register/", "/auth/password-reset/", "/free/",
    "/legal/imprint/", "/legal/privacy/", "/legal/terms/", "/legal/license/",
    "/legal/withdrawal/", "/legal/accessibility/",
    "/vertrag-widerrufen/", "/vertraege-kuendigen/",
)
PROTECTED_REDIRECT = ("/pro/", "/pro-old/", "/ns-admin/", "/portal/dashboard/")
SENSITIVE_DENIED = (
    "/.env", "/.git/config", "/compose.yaml", "/Dockerfile",
    "/metrics/internal/anything", "/api/v1/mcp/health/",
)


def first_party_https(url: str) -> bool:
    item = urlsplit(url)
    return item.scheme == "https" and item.netloc == HOST and not (item.username or item.password)


class FirstPartyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not first_party_https(newurl):
            raise ValueError("External or non-HTTPS redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_get(path: str):
    url = urljoin(BASE + "/", path.lstrip("/"))
    if not first_party_https(url):
        raise ValueError("Off-origin request refused")
    req = Request(
        url,
        headers={"User-Agent": "PROMPTFINISHER-go-live-readonly/1",
                 "Cache-Control": "no-cache", "Accept-Encoding": "identity"},
        method="GET",
    )
    opener = build_opener(FirstPartyRedirect)
    try:
        with opener.open(req, timeout=35) as resp:
            final_url = resp.geturl()
            if not first_party_https(final_url):
                raise ValueError("Off-origin response refused")
            payload = resp.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise ValueError("Unexpected oversized response")
            return resp.status, urlsplit(final_url).path, payload
    except HTTPError as exc:
        if exc.code in (403, 404, 405):
            return exc.code, urlsplit(exc.url).path, b""
        raise


def run() -> int:
    rows = []
    for path in PUBLIC_HTML + PROTECTED_REDIRECT + SENSITIVE_DENIED + ("/catalog.json", "/health/live/", "/health/ready/"):
        category = (
            "html" if path in PUBLIC_HTML else
            "protected" if path in PROTECTED_REDIRECT else
            "denied" if path in SENSITIVE_DENIED else
            "json" if path == "/catalog.json" else "health"
        )
        row = {"path": path, "category": category, "result": "FAIL"}
        try:
            status, final, payload = read_get(path)
            if category == "html":
                passed = status == 200 and b"<html" in payload[:10000].lower()
            elif category == "protected":
                passed = status == 200 and final == "/auth/login/" and b"<html" in payload[:10000].lower()
            elif category == "denied":
                passed = status in (403, 404)
            elif category == "json":
                passed = status == 200 and isinstance(json.loads(payload), dict)
            else:
                passed = status == 200
            row.update(status=status, final=final, result="PASS" if passed else "FAIL")
        except Exception as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)[:200]
        print(f"PF_PROD_ROUTE={path};CATEGORY={category};RESULT={row['result']};HTTP={row.get('status','ERROR')};FINAL={row.get('final','-')}", flush=True)
        rows.append(row)
    passes = sum(r["result"] == "PASS" for r in rows)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_GET_NO_AUTH",
        "origin": BASE,
        "passed": passes,
        "total": len(rows),
        "result": "PASS" if passes == len(rows) else "REVIEW_REQUIRED",
        "rows": rows,
        "limitation": "Anonymous HTTP-only. No authenticated or business-operation acceptance."
    }
    (OUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PF_PROD_ROUTE_FINAL={report['result']};PASS={passes}/{len(rows)}", flush=True)
    return 0 if passes == len(rows) else 2


if __name__ == "__main__":
    sys.exit(run())
