#!/usr/bin/env python3
"""Compare the public PROMPTFINISHER Free JS asset against this Git checkout.

This is deliberately *asset parity*, not proof of the installed backend commit.
GET-only, no authentication, no SSH, no deployment, no production writes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_ASSET = "backend/static/js/promptfinisher_product_i18n.20261011.js"
ASSET_BASENAME = "promptfinisher_product_i18n.20261011.js"
ORIGIN = "https://promptmaster.decke-wand-boden.de"
FREE_URL = ORIGIN + "/free/"
ARTIFACT_DIR = ROOT / "browser-artifacts" / "production-parity"
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_ASSET_BYTES = 5 * 1024 * 1024


class ScriptSources(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        src = dict(attrs).get("src")
        if src:
            self.sources.append(src)


def product_script_url(html: str) -> str:
    parser = ScriptSources()
    parser.feed(html)
    matches = [
        urljoin(FREE_URL, src)
        for src in parser.sources
        if urlsplit(urljoin(FREE_URL, src)).path.endswith("/" + ASSET_BASENAME)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one public product-locale script, found {len(matches)}"
        )
    target = matches[0]
    if urlsplit(target).scheme != "https" or urlsplit(target).netloc != urlsplit(ORIGIN).netloc:
        raise ValueError("Product-locale script is not served from the expected HTTPS origin")
    return target


def read_public(url: str, max_bytes: int) -> tuple[bytes, int]:
    request = Request(
        url,
        headers={
            "User-Agent": "PROMPTFINISHER-Release-Parity/1.0 (GET-only)",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urlopen(request, timeout=45) as response:
        status = response.status
        if status != 200:
            raise ValueError(f"Unexpected HTTP status {status}: {urlsplit(url).path}")
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Public response exceeds safe read limit")
        encoding = response.headers.get("Content-Encoding", "").lower()
        if encoding == "gzip":
            payload = gzip.decompress(payload)
            if len(payload) > max_bytes:
                raise ValueError("Decompressed public response exceeds safe read limit")
        elif encoding not in ("", "identity"):
            raise ValueError(f"Unexpected content encoding: {encoding}")
    return payload, status


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "scope": "PUBLIC_STATIC_ASSET_ONLY",
        "mode": "GET_ONLY",
        "production_backend_sha_verified": False,
        "authenticated_live_test": False,
        "source_revision": os.getenv("GITHUB_SHA", "local-checkout"),
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "free_url": FREE_URL,
        "asset_path": RELATIVE_ASSET,
    }
    result = "ERROR"
    exit_code = 3
    try:
        source = (ROOT / RELATIVE_ASSET).read_bytes()
        report["repository_sha256"] = sha256(source)
        html, html_status = read_public(FREE_URL, MAX_HTML_BYTES)
        report["html_http_status"] = html_status
        script_url = product_script_url(html.decode("utf-8", errors="replace"))
        report["deployed_asset_url"] = script_url
        deployed, asset_status = read_public(script_url, MAX_ASSET_BYTES)
        report["asset_http_status"] = asset_status
        report["deployed_sha256"] = sha256(deployed)
        report["repository_bytes"] = len(source)
        report["deployed_bytes"] = len(deployed)
        if source == deployed:
            result, exit_code = "PASS_ASSET_PARITY", 0
        else:
            result, exit_code = "DEPLOYMENT_PENDING_ASSET_MISMATCH", 2
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[:350]}"
        result, exit_code = "UNVERIFIED_PUBLIC_ACCESS", 3
    report["result"] = result
    (ARTIFACT_DIR / "result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"R5_PROD_ASSET_PARITY={result};BACKEND_SHA=NOT_VERIFIED;MODE=GET_ONLY")
    if result != "PASS_ASSET_PARITY":
        print("R5_PROD_ASSET_PARITY_ACTION=VERIFY_PRODUCTION_DEPLOYMENT")
    print(f"R5_PROD_ASSET_REPORT={ARTIFACT_DIR / 'result.json'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
