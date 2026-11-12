# Issue #105 – confirmed production UI defects, 6 November 2026

Baseline: a57468e673d22163ccf55efea9ec28738e2cf0dd.

Live Chromium reproduction on /free/: select Copilot Chat, summarize content,
enter synthetic context and complete audience/focus/output. A terminal period
in the requested outcome receives another period. The composer now preserves
existing terminal punctuation and adds the contract period only when needed.

In English, the Pro-area expander, selected badge, comparison/briefing teasers,
summary field hints, several locked focus labels, bullet/prose options and the
rebranded Microsoft trademark notice remain German. Add explicit translations
for all nine non-German locales, including the review-progress accessible label.
Correct the Dutch/Polish date labels which referred to fruit.

No schema, migration, entitlement, payment or persistence changes. Immutable
Golden Masters remain unchanged. Scope: existing UI translation and prompt
formatting defects; no new product functionality. User authorized confirmed
code fixes and CI in the production acceptance request. Production merge and
deployment still require the existing human review and release gates.

Verification: Python/static/repository/domain/asset validators; nine-language
catalogue regression; composer regression across contracts and punctuation.
Full production acceptance remains open pending authenticated test accounts,
all task/locale/device combinations, and post-release verification of fixes.

Follow-up 10 November: Free Word license dialog interpolation and stable required-tier metadata avoid untranslated headings, requirements and CTAs. Translate confirmed Word task previews, hints and known PRO-suffixed labels without touching inputs or Golden Masters. Remove duplicated translation entries and register acceptance evidence in the audit manifest.

Container gate remediation: require Alpine musl/musl-utils >=1.2.5-r24 in Caddy; rebuild Go binaries with x/net v0.62.0 and matching x/crypto v0.58.0; explicitly update Debian zlib1g and enforce the scanner-reported fixed version in the web build. No scanner suppression or relaxation. Full stack passed at c4ecac3; new zlib/UI changes require fresh CI and human review. These are build-time corrections only; production remains unchanged.

Follow-up 12 November: authenticated French backend showed German loading, sorting and confirmation UI because shared app.js supported only five of ten locales. Add FR/IT/NL/PL/RU dictionaries and locale-aware collation; correct French Bestellungen to Commandes. Extend the executed catalogue contract across all ten languages. Production SHA verified from operations UI; active django monitoring and disk warnings recorded, not hidden or resolved by this translation patch.
