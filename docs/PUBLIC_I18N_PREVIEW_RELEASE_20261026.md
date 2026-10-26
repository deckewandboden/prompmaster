# PROMPTFINISHER – Public Preview / I18N Release Candidate

**Scope:** Ten-language Free/Pro UI and prompt generation, portal, public marketing, and legal navigation, based on the reviewed PR #85. The release candidate is isolated in `release/i18n-public-preview-20261026`. Source PRs #85/#88/#89 and `main` are not altered by this candidate.

## Strict noncommercial launch contract

1. **New payments are locked in production by code**, not just by an empty `.env`: `mollie_runtime_ready()` returns `False` when `ENVIRONMENT=production`, even with database-stored Mollie live credentials, profile, and checkout approval. This disables public `catalog.json.checkoutEnabled`, public POST `/api/v1/checkout/start/`, portal license purchases and renewals that use the shared readiness gate. Existing account, license usage, Free and Pro prompt features remain separate. This release is **not** the paid launch.
2. **German legal bodies remain the only legal document content**. For all six public legal types and all ten UI languages, the document text remains German and carries `lang="de"`; non-German UI shows an explicit warning in the selected language. No automatic legal translations, review bypass, approval claim or new signed consent rollout.
3. This candidate does **not** include the unapproved new legal governance/migrations and account/checkout snapshot feature flags from PR #88/#89. It is intentionally a smaller publication surface.
4. Juridical and commercial launch remain separate. Issues #87 and #91 are open. Nothing here verifies external professional review of contract, withdrawal, consent or data-protection language.

## Conditions before any publication

- All four GitHub Actions workflows `CI`, `Full Dependency Security`, `Release Safety Gates` and `Shell Syntax` must show `completed/success` on the **exact head commit of this release candidate**. The source PR #85 success is not a substitute.
- Staging/live simulation must verify ten UI languages and generated Free/Pro prompts, all six legal pages, `catalog.json.checkoutEnabled=false`, and **actual public + authenticated purchase POSTs blocked before creating orders or contacting Mollie**.
- Backup, recovery/rollback procedure, current deployment SHA and configuration checks must pass on the actual target server. The server must be reachable and its TLS/DNS/forwarded-host and CSRF config must be verified. Production website has not been confirmed accessible from the assistant's external network at time of preparation.
- Confirm legal minimum for even a no-purchase public launch (imprint/privacy and any registration consent) with the responsible person, and ensure production data handling is compliant.
- A separate, explicit operator release decision is required before merging or deploying. The candidate branch itself is **not a deployment approval**.

## Scope beyond the preview

To accept paid orders, create a separately reviewed release that replaces the hardcoded production preview lock after Mollie live validation, all relevant signed/legal evidence and external legal sign-off. Do not simply change `ENVIRONMENT` to `staging` on a public system; that would violate the deployment contract and weaken other environment-specific protections.
