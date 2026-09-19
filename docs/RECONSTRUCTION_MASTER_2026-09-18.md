# PromptMaster — Canonical Reconstruction Master 2026-09-18

This branch reconstructs the product UI without reverting the hardened commercial backend.

## Source priority
1. Current hardened GitHub backend/security/runtime code.
2. `PromptMaster_COMPLETE_BACKUP_ALL_FILES_2026-09-13` (RC14 consolidation evidence and Golden Masters).
3. Recovered customer portal and netstyle Admin UI prototypes/screenshots.
4. Marketing V15 conversation evidence (commit `2f78921327346233c3f31053eeb670fc372ca1fb`).
5. Latest user-supplied PromptMaster v13 Direct Tracking V2 wallpaper code for the hero renderer.

## Binding UI surfaces
- Marketing / sales frontend.
- PromptMaster Free Golden Master.
- PromptMaster Pro / PM20 34 apps, 194 tasks.
- Customer portal: dashboard, team, licenses, purchase, devices, orders/payments, company, settings/security, help/contact.
- netstyle Admin: dashboard, customers, licenses, orders/payments, products/prices, Prompt Studio, content/FAQ, mail, Mollie, statistics, operations, API, legal, support, audit, users/roles, settings.

## Reconstruction patch 01
- Keep Caddy compatibility-route fix and query preservation.
- Replace the old 16k-particle hero renderer with the latest recovered 22k/8.2k renderer including topology detail, dissolve, landscape lights, stars and light trails.
- Preserve `prefers-reduced-motion` and context-loss fallback; do not render a visible motion/pause control.
- Remove camera/webcam tracking completely. Head interaction is pointer-only; no camera permission or camera API is part of the marketing runtime.
- Restore V15 hero/content wording where exact evidence is available.
- Restore the final Free catalog contract: all 34 current applications visible, exactly 6 legacy Free app areas / 16 reviewed Free tasks usable, the remaining 28 applications visibly Pro-locked. The byte-exact FREE 1.2.4 Golden Master remains immutable and is augmented only by a versioned visibility bridge.
- Remove obsolete public-preview copy from compatibility pages/footer.
- Make mandatory 2FA setup/recovery a dedicated security flow instead of showing portal navigation that cannot be used before setup completes.
- Restore Pro rating UX: 1–3 stars show a separate `Feedback ergänzen` action and only then may the optional text field open; 4–5 stars complete the rating without an additional feedback prompt.
- Make deployment on hosts with an existing external TLS reverse proxy reproducible via `compose.external-caddy.yaml`; PromptMaster must not publish host ports 80/443 in that mode and uses unique internal DNS aliases.
- Reject sensitive source/configuration probe paths before the marketing SPA fallback so `/.env`, `/.git/*`, Dockerfiles and Compose files return 404 instead of a misleading marketing HTTP 200.

## Non-negotiable regression rules
- No downgrade of payment/security/concurrency hardening.
- Free/Pro Golden Master hashes remain unchanged unless explicitly versioned.
- Portal/admin routes remain server-authorized.
- No webcam/camera tracking code in the marketing runtime.
- If WebGL is unavailable or lost, render the head through the Canvas2D fallback without requiring browser configuration.
- Marketing browser smoke must test both WebGL success and non-WebGL fallback.