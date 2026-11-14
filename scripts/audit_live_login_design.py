#!/usr/bin/env python3
"""Read-only production acceptance of the shared PROMPTFINISHER login page.

Runs on GitHub-hosted CI, without credentials or production mutations.
Only HTTPS GET requests to the fixed first-party origin are allowed.
The test checks *served* HTML and CSS, not local checked-out templates.
"""
from __future__ import annotations

import html
import re
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import Request, urlopen

ORIGIN = "https://promptmaster.decke-wand-boden.de"
LOGIN = ORIGIN + "/auth/login/?next=%2Fns-admin%2F"
LANGUAGES = ("de", "en", "es", "pt", "tr", "ru", "pl", "fr", "it", "nl")
CSS_PATH = "/static/css/app.css"
MAIN_APP_CSS = re.compile(r"^/static/css/app(?:\.[0-9a-fA-F]{12})?\.css$")
CAPTIONS = {
    "de": ("Konto anlegen", "Passwort vergessen?"),
    "en": ("Create account", "Forgot password?"),
    "es": ("Crear cuenta", "¿Olvidó la contraseña?"),
    "pt": ("Criar conta", "Esqueceu a palavra-passe?"),
    "tr": ("Hesap oluştur", "Parolanızı mı unuttunuz?"),
    "ru": ("Создать учётную запись", "Забыли пароль?"),
    "pl": ("Utwórz konto", "Zapomniałeś hasła?"),
    "fr": ("Créer un compte", "Mot de passe oublié ?"),
    "it": ("Crea account", "Password dimenticata?"),
    "nl": ("Account aanmaken", "Wachtwoord vergeten?"),
}

def is_main_app_css(path: str) -> bool:
    """Allow original or Django ManifestStaticFilesStorage hashed app CSS."""
    return bool(MAIN_APP_CSS.fullmatch(path))
CSS_REVISION = "20261113-login-actions1"
OLD_COPY = "Ein Zugang für PROMPTFINISHER, Kundenportal und netstyle Admin"
OLD_REGISTER = "Noch kein Konto? Konto erstellen"
REGISTER_PATH = "/auth/register/"
RESET_PATH = "/auth/password-reset/"


class LoginDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.actions = []
        self.stylesheets = []
        self.action_depth = 0
        self.current_link = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set(attrs.get("class", "").split())
        if tag == "div":
            if self.action_depth:
                self.action_depth += 1
            elif "login-secondary-actions" in classes:
                self.action_depth = 1
        if tag == "a" and self.action_depth:
            self.current_link = {
                "href": attrs.get("href", ""),
                "classes": classes,
                "text": "",
            }
        if tag == "link" and "stylesheet" in attrs.get("rel", "").split():
            self.stylesheets.append(attrs.get("href", ""))

    def handle_data(self, data):
        if self.current_link is not None:
            self.current_link["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            self.current_link["text"] = " ".join(self.current_link["text"].split())
            self.actions.append(self.current_link)
            self.current_link = None
        if tag == "div" and self.action_depth:
            self.action_depth -= 1


def read_public(url: str, *, language: str = "de") -> str:
    parsed = urlsplit(url)
    expected = urlsplit(ORIGIN)
    if parsed.scheme != "https" or parsed.netloc != expected.netloc or parsed.username or parsed.password:
        raise ValueError("Origin guard blocked URL")
    request = Request(
        url,
        headers={
            "Cookie": f"promptfinisher_language={language}",
            "Accept-Language": language,
            "User-Agent": "PROMPTFINISHER-R5-ReadOnly-LiveAudit/1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    with urlopen(request, timeout=35) as response:
        final = urlsplit(response.url)
        if final.scheme != "https" or final.netloc != expected.netloc:
            raise ValueError("Redirect left the approved HTTPS origin")
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        data = response.read(3 * 1024 * 1024 + 1)
        if len(data) > 3 * 1024 * 1024:
            raise ValueError("Unexpected oversized response")
        return data.decode("utf-8", errors="replace")


def check_login(language: str) -> tuple[bool, list[str], str | None]:
    checks = []
    document = html.unescape(read_public(LOGIN, language=language))
    parsed = LoginDocument()
    parsed.feed(document)
    if OLD_COPY in document:
        checks.append("OLD_EXPLANATORY_COPY_VISIBLE")
    if OLD_REGISTER in document:
        checks.append("OLD_REGISTER_CAPTION_VISIBLE")
    if "login-main-card" not in document:
        checks.append("NEW_CARD_MARKER_MISSING")
    if len(parsed.actions) != 2:
        checks.append(f"EXPECTED_TWO_SECONDARY_ACTIONS_GOT_{len(parsed.actions)}")
    elif not all({"btn", "secondary"} <= link["classes"] for link in parsed.actions):
        checks.append("SECONDARY_BUTTON_STYLES_MISSING")
    else:
        register, reset = parsed.actions
        register_url = urlsplit(urljoin(LOGIN, register["href"]))
        reset_url = urlsplit(urljoin(LOGIN, reset["href"]))
        if register_url.path != REGISTER_PATH:
            checks.append("REGISTER_TARGET_CHANGED")
        if parse_qs(register_url.query).get("next") != ["/ns-admin/"]:
            checks.append("REGISTER_NEXT_LOST")
        if reset_url.path != RESET_PATH:
            checks.append("RESET_TARGET_CHANGED")
        expected_register, expected_reset = CAPTIONS[language]
        if register["text"] != expected_register:
            checks.append("REGISTER_CAPTION_NOT_LOCALIZED")
        if reset["text"] != expected_reset:
            checks.append("RESET_CAPTION_NOT_LOCALIZED")
    css_matches = [
        urljoin(LOGIN, source)
        for source in parsed.stylesheets
        if is_main_app_css(urlsplit(urljoin(LOGIN, source)).path)
    ]
    if len(css_matches) != 1:
        checks.append(f"EXPECTED_ONE_MAIN_CSS_GOT_{len(css_matches)}")
        checks.append("CSS_LINK_PATHS=" + ",".join(urlsplit(urljoin(LOGIN, source)).path for source in parsed.stylesheets)[:200])
        css_url = None
    else:
        css_url = css_matches[0]
        if parse_qs(urlsplit(css_url).query).get("v") != [CSS_REVISION]:
            checks.append("LOGIN_CSS_REVISION_STALE")
    return not checks, checks, css_url


def run() -> int:
    failed = 0
    css_url = None
    for language in LANGUAGES:
        try:
            passed, checks, locale_css = check_login(language)
            css_url = css_url or locale_css
            failed += int(not passed)
            print(
                f"R5_LIVE_LOGIN={language};RESULT={'PASS' if passed else 'FAIL'};"
                f"CHECKS={','.join(checks) if checks else '-'}",
                flush=True,
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            failed += 1
            print(f"R5_LIVE_LOGIN={language};RESULT=BLOCKED_NETWORK;ERROR={type(exc).__name__}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"R5_LIVE_LOGIN={language};RESULT=FAIL;ERROR={type(exc).__name__}:{exc}", flush=True)

    if css_url:
        try:
            css = read_public(css_url)
            required = (
                ".login-card .login-secondary-actions",
                "grid-template-columns:repeat(2,minmax(0,1fr))",
                "height:44px",
                ".login-main-card > h1",
            )
            missing = [token for token in required if token not in css]
            if missing:
                failed += 1
                print("R5_LIVE_LOGIN_CSS=FAIL;MISSING=" + ",".join(missing), flush=True)
            else:
                print("R5_LIVE_LOGIN_CSS=PASS", flush=True)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            failed += 1
            print("R5_LIVE_LOGIN_CSS=BLOCKED_NETWORK;ERROR=" + type(exc).__name__, flush=True)
    else:
        failed += 1
        print("R5_LIVE_LOGIN_CSS=FAIL;NO_VALID_CSS_URL", flush=True)

    print(f"R5_LIVE_LOGIN_FINAL={'PASS' if failed == 0 else 'REVIEW_REQUIRED'};FAILURES={failed}", flush=True)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(run())
