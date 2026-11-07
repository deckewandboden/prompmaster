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
