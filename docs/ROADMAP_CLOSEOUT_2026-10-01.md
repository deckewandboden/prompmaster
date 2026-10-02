# PromptMaster Roadmap Closeout — 2026-10-01

This document consolidates the late-September/1-October closeout work and separates
code-complete items from provider/human acceptance that cannot be completed by source
changes alone.

## Code-complete on main before this closeout

- Free/Pro V2 surfaces and legacy rollback routes
- complete Pro catalog and explicit Free-in-Pro parity
- Prompt-Check missing-step handling and progress UI
- customer portal with tenant isolation
- netstyle admin backend, system-wide sortable DataGrids and permission tests
- support conversation history, staff replies, audit logging and resilient mail queueing
- checkout/legal/customer data model and 365-day license behavior
- configurable mail identity, SMTP1/SMTP2/Microsoft Graph routing and conservative failover
- stable SMTP Message-ID using the configured sender domain
- PromptMaster triangle branding on the public Pro card; crown removed
- Pro title gradient aligned to the PromptMaster triangle

## Included in this closeout branch

- system-wide admin form-spacing contract so selected controls/help/error text cannot overlap
- durable Gmail plus-alias support for demo identities
- dedicated netstyle presentation demo: DEMO-NETSTYLE, 12 active users, Rainer Spickermann as MFA-required company admin, 10 PRO licenses (9 assigned/1 free), 3 Free users, 3 synthetic orders (1/7/+2), 1 open PRO request and no outbound mail/provider calls
- safe in-place demo-user readdress command that preserves user IDs/password hashes/relationships
- one canonical default support-reply template contract, while the runtime remains backward compatible

## Production facts already verified

- public PromptMaster target is deployed behind the external Caddy setup
- real IONOS SMTP submission works
- real Gmail delivery works
- SPF passes
- DKIM passes
- DMARC passes
- TLS is active
- sender-domain Message-ID is present in real delivered mail
- Google Postmaster Tools ownership for decke-wand-boden.de is verified

Gmail spam placement for a fresh recipient was reproduced even with SPF/DKIM/DMARC/TLS
and the corrected Message-ID. A manually sent message from the new
promptmaster@decke-wand-boden.de sender was also placed in spam. This is therefore tracked
as sender/deliverability reputation, not as an unresolved PromptMaster application defect.

## Remaining external / human acceptance

These are not source-code defects and require real provider/operator evidence:

1. Mollie end-to-end acceptance against the intended production/test provider configuration,
   including webhook and payment-state transitions.
2. External restic/S3 backup + isolated restore drill against the final production repository.
3. Monitoring/alert recipients and emergency-access procedure verified with real recipients.
4. Human legal/tax review of the production legal texts and checkout wording.
5. Brand/name decision: the product name PromptMaster remains intentionally unchanged for now.
6. Gmail/Postmaster reputation observation after real, non-synthetic traffic; do not use repeated
   artificial bursts as a deliverability benchmark.

## Final release procedure

After this closeout PR is green:

1. squash-merge to main;
2. deploy web + worker + beat for backend/management-command changes;
3. run migrations (safe even when none are pending);
4. collect static files;
5. rebuild/recreate caddy because the latest public marketing change is part of the same final release;
6. remove the obsolete orphan Mailpit container if it is still present;
7. run health/readiness checks;
8. run targeted production smoke checks for public marketing, Free, Pro, customer portal and netstyle admin;
9. execute the external/human acceptance items above before declaring final production release.
