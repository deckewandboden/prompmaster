# Forensische Analyse der zusätzlich gelieferten Quellarchive

Die beiden vom Benutzer nachgereichten Archive wurden rekursiv geöffnet. Jede Textdatei wurde vollständig dekodiert und zeilenweise eingelesen; Binärdateien und verschachtelte Archive wurden vollständig gelesen und SHA-256-gehasht.

- gelesene Archive/verschachtelte Archive: 2 Hauptarchive + 1 verschachtelte ZIPs
- gelesene Datei-Einträge: 167
- Text-/Code-Dateien vollständig gelesen: 146
- gelesene Textzeilen: 35839
- verarbeitete Nutzdaten: 21,640,900 Byte

## Wesentliche Erkenntnisse

1. Die Sicherung vom 06.09.2026 enthält einen vollständigen Marketing-Frontend-Quellbaum (`frontend/`) einschließlich Source, Tests, Vite-Konfiguration, lokalem Three.js-Kopfmodell, Nachtlandschaft, Brand-Referenz und gebautem `dist/`. Dieser Quellbaum ist in RC14 als aktives `marketing/` integriert.
2. Der Chat-Transfer vom 12.09.2026 enthält keine spätere vollständige Django-RC8-Codebasis, sondern die Master-Spezifikation, eine kleine Phase-2-Baseline, UI-Prototypen und 10 große Design-/UI-Referenzen. Diese Dateien sind in RC14 vollständig unter `archive/chat-transfer-2026-09-12/` erhalten.
3. Die Marketing-Sicherung dokumentiert noch den historischen Stand mit 6 Free- und 10 zusätzlichen Pro-Anwendungen. RC14 synchronisiert diesen sichtbaren Stand zur Laufzeit mit dem aktuellen zentralen 34-App-PM20-Katalog (28 zusätzliche Anwendungen gegenüber Free), ohne die wiedergefundenen Designassets auszutauschen.
4. Die Marketing-Sicherung enthält bereits die wesentlichen Vertriebsbereiche: Hero, Funktionen, Ablauf, Free-vs-Pro, Preise, Lizenzlogik, Unternehmensportal, Datenschutz/Sicherheit und FAQ sowie vorbereitete Routen für Checkout/Login/Portal/Pro/Rechtliches.
5. Das Chat-Transfer-Paket bestätigt die verbindlichen 365-Tage-, Verlängerungs-, Geräte-, Reminder-, Mollie-, Rollen-, DataGrid-, Operations- und Deployment-Regeln, enthält aber keinen neueren Code, der RC13/RC14 ersetzen müsste.

## Keyword-Treffer über alle vollständig gelesenen Textdateien

| Begriff | Treffer |
|---|---:|
| `PromptDefinition` | 0 |
| `PromptVersion` | 0 |
| `Prompt Studio` | 0 |
| `MCP` | 3 |
| `PM20` | 0 |
| `PM11` | 0 |
| `v13` | 1 |
| `v14` | 1 |
| `v15` | 1 |
| `marketing` | 41 |
| `checkout` | 55 |
| `Mollie` | 194 |
| `365` | 104 |
| `T-60` | 3 |
| `T-30` | 12 |
| `T-7` | 6 |
| `2FA` | 50 |
| `device` | 95 |
| `license` | 850 |
| `free` | 416 |
| `pro` | 4922 |
| `Caddy` | 46 |
| `Django` | 76 |
| `PostgreSQL` | 55 |
| `Redis` | 38 |
| `Celery` | 29 |
| `GitHub` | 139 |

## Duplikatgruppen nach SHA-256

18 Hash-Gruppen kommen mehrfach vor. Das ist vor allem durch wiederholte SPEC-/README-/Prototyp-Dateien und verschachtelte Sicherungen erklärbar.

## Vollständiges Datei-Inventar der beiden Archive

| Archiv | Pfad | Bytes | SHA256 | Typ | Zeilen | relevante Treffer |
|---|---|---:|---|---|---:|---|
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `docs/content-freeze-reference.md` | 21028 | `b98b8b68ef2acdb8754e20ae195c718526c4b65d3866fed7925cf64310a53058` | text | 932 | marketing:6, Mollie:1, 365:2, free:29, pro:191 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `docs/free-live-reference.html` | 71799 | `a7586690d84ad4a549ac7e1498fdd0333b36c9c024ab5b7a98044a2b689b7f52` | text | 1205 | 365:24, device:1, license:33, free:38, pro:322 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `docs/pflichtenheft-reference.md` | 21194 | `8a5e4efcd698eba9f49ea70c76da09765dc5ac30420e7d82e653c7e5ae5a4b5e` | text | 1203 | marketing:3, checkout:12, Mollie:15, license:2, free:15, pro:112, Caddy:3, Django:8, PostgreSQL:5, Redis:2 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/.gitignore` | 384 | `14c2d4b7781dcd266e563c4f08880637ae620c7e8a182246a23b138e5f791e8e` | text | 38 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/.oxfmtrc.json` | 260 | `0962fdddb1840a06b5afb918ff3f2ff56bce346082651ec5c3567c01dd809f17` | text | 13 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/.oxlintrc.json` | 1370 | `1a7aa1c7d83b05939e4e697eed9316224caea8958c4ad12837f8be740c13a47d` | text | 56 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components.json` | 516 | `9928283696d86836422959a2c520df83a718d31ffbcab533a14ca8dca2c8d475` | text | 25 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/index.html` | 4110 | `47f4a1ccafee10e3924303a7a43ebe515c220505d0c2c29df900653c047b2818` | text | 10 | checkout:1, device:1, free:9, pro:31 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/next.config.ts` | 104 | `d063bebef3a4878ae82f9f9547c2c9675b8b6945ab23702932dcb63a011a9fc9` | text | 5 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/package-lock.json` | 347285 | `e742e43c1184fdbd3566241ac582c54f899cfddbbd0cc29db09e7f89e1521887` | text | 9899 | MCP:3, v14:1, marketing:2, T-7:5, 2FA:1, license:698, free:41, pro:57, GitHub:129 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/package.json` | 1668 | `53f28ed51b220ae668f5b06fc14cfbcfe121e5a7973d6a990b3a48daf67db3b2` | text | 57 | marketing:4, pro:1 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/README.md` | 4310 | `42c11ae422f35b9bcd4acbca2b2841cf8e61d054aeac71b6f9f1e9ff6e8de455` | text | 55 | marketing:6, checkout:1, Mollie:3, free:6, pro:10, Django:6, PostgreSQL:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/tsconfig.json` | 671 | `81aca06cd76be09d9b65c7dff6a031c38664263b506ea792a28f36b17be25f2a` | text | 30 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/vite.config.ts` | 1807 | `3c028e727dde6c92022197ba7241a424ccd1e3d335f1f46cc9bbf91a8a3a968c` | text | 61 | pro:5 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/vite.marketing.config.js` | 147 | `a22333fbc3ff592a131ef4e2d9028cec3699059f4d185b38e657d3be58b4d04e` | text | 2 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/tests/content.test.mjs` | 2108 | `736ad916eed9b003aa8c80934415d10e440785b59890c9bfdf468b86eb0ac23a` | text | 34 | pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/tests/pricing.test.mjs` | 1751 | `4116dfe61d2d27a6199392a4d11368e1b5cffdbdedfd98c33ac602c3b537ec59` | text | 28 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/content.js` | 13248 | `0fae9e6eaece157ceba86971af22329c44f2161df683de8c04eddb0e0572503a` | text | 17 | marketing:1, checkout:3, Mollie:1, 365:1, license:2, free:16, pro:104 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/faq.json` | 4883 | `3e0b3cd9431cb78039ad2e0c831f1e2814ad04a71b102c570af3b5b4f117e66e` | text | 82 | 365:1, free:3, pro:47 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/head.js` | 10732 | `e8d0828c440925b530237840c1ca5b25e6cf14cb1554582caa1ffc2b053536f5` | text | 116 | device:1, free:2, pro:10 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/immersive.css` | 11719 | `a8ae454f459e60cd49caf0d63fbef27fff2d1c3caa8acab0f282840c390d83df` | text | 77 | marketing:1, free:1, pro:60 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/main.js` | 7135 | `4e7384af847fe93c63adbb80b8127984093a3dc64c2631b2aefe49df0d33e0de` | text | 99 | marketing:1, checkout:4, license:2, free:9, pro:23 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/pricing.js` | 1282 | `9fc3a5c2d5b3cf3c77a6d9134a9f793c4a4e2cb335525ef9143ae79a79f1a595` | text | 16 | pro:14 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/src/style.css` | 12405 | `3d988513866d314d8dbe2f3ea7bd36a2bf2da343cf2eaf32517c1b7c4621b3bc` | text | 4 | license:4, pro:16 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/scripts/finalize.mjs` | 1634 | `145249076356484d516e998abe59aeea6e1eb7f6c3313160d44982fdc03c8024` | text | 18 | marketing:1, checkout:1, free:1, pro:5 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/scripts/redesign.mjs` | 5273 | `51a9424cf1ad8255166fc6702a7255a938a9aa65cc1ce5c94c0852b3dfa48ded` | text | 21 | checkout:1, device:1, free:11, pro:45 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/scripts/verify-golden-master.mjs` | 539 | `6032f8feb0a6a841d2b9ecd051bf0f75c43ccbb06ccfca05e93716ccd26d4409` | text | 10 | pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/catalog.json` | 297 | `7b8ccc92bc3b74efd64fec82c9b6669908cc83cd8f3a6f8972ce8e9a59badcb3` | text | 1 | checkout:1, free:2, pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/favicon.svg` | 276 | `ac387f455ca1a1724da9e92a8dd71c20cec454c80fa9476f65da4a08667ad0a8` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/robots.txt` | 26 | `331ea9090db0c9f6f597bd9840fd5b171830f6e0b3ba1cb24dfa91f0c95aedc1` | text | 2 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/_headers` | 185 | `b3e7ff8ece08e3d772948ba64d60c939858d94e3ea087dacec48193b5cab4756` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/models/ATTRIBUTION.txt` | 536 | `c7703919fd81cc92c73c6f947cadb242e66e54e50f68e8f921b09139f083e864` | text | 7 | license:3, pro:1 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/models/head.glb` | 404976 | `402b8a8ac9f03232e6d64b5962929703a069daf99d3c49ac8eb0e48bedc9c576` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/models/night-landscape.png` | 1823026 | `8f05bcac2709089321e59d57dac4dbbe0d6295a6ed5b550c930ea9d530bb274a` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/public/brand/design-reference.jpeg` | 238669 | `2bfb44f2d888e463e7f9e9b581b02d775d59506146aa1d6b5b027e8bef889340` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/lib/utils.ts` | 169 | `9304a861c8673bee09e0f12de31773abbde503b02e59dfd74763ddec2e37cf05` | text | 6 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/hooks/use-mobile.ts` | 585 | `82bff42ff087bd5dc90a5d17609cc428b8688de92d1333073a839af5ad3c9cbd` | text | 21 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/docs/design-corrections.md` | 2339 | `a510a474cb54738bc2b53018382c37abd5dbb4ebcf80e036e676d087b12868bd` | text | 25 | marketing:1, free:2, pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/docs/validation.md` | 1720 | `a0d0ea74a2a95594726168f1629b3c3c420db666fae4562180ca5c8627fba496` | text | 23 | marketing:2, free:1, pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/404.html` | 2935 | `d8b6e1da5d52573562afa3dbc5ba0a1237fada44dac2ff8a31826c3d9cae1838` | text | 8 | device:1, free:5, pro:19 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/catalog.json` | 297 | `7b8ccc92bc3b74efd64fec82c9b6669908cc83cd8f3a6f8972ce8e9a59badcb3` | text | 1 | checkout:1, free:2, pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/favicon.svg` | 276 | `ac387f455ca1a1724da9e92a8dd71c20cec454c80fa9476f65da4a08667ad0a8` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/index.html` | 24422 | `64a609de7527a5372610b1568dfa89a2ad4b08cf51cda7afae75d871e82f4583` | text | 41 | marketing:1, checkout:4, Mollie:1, 365:2, device:1, license:2, free:25, pro:180 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/robots.txt` | 26 | `331ea9090db0c9f6f597bd9840fd5b171830f6e0b3ba1cb24dfa91f0c95aedc1` | text | 2 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/_headers` | 185 | `b3e7ff8ece08e3d772948ba64d60c939858d94e3ea087dacec48193b5cab4756` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/vergleich/index.html` | 24422 | `64a609de7527a5372610b1568dfa89a2ad4b08cf51cda7afae75d871e82f4583` | text | 41 | marketing:1, checkout:4, Mollie:1, 365:2, device:1, license:2, free:25, pro:180 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/unternehmen/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/pro/index.html` | 24422 | `64a609de7527a5372610b1568dfa89a2ad4b08cf51cda7afae75d871e82f4583` | text | 41 | marketing:1, checkout:4, Mollie:1, 365:2, device:1, license:2, free:25, pro:180 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/preise/index.html` | 24422 | `64a609de7527a5372610b1568dfa89a2ad4b08cf51cda7afae75d871e82f4583` | text | 41 | marketing:1, checkout:4, Mollie:1, 365:2, device:1, license:2, free:25, pro:180 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/portal/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/models/ATTRIBUTION.txt` | 536 | `c7703919fd81cc92c73c6f947cadb242e66e54e50f68e8f921b09139f083e864` | text | 7 | license:3, pro:1 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/models/head.glb` | 404976 | `402b8a8ac9f03232e6d64b5962929703a069daf99d3c49ac8eb0e48bedc9c576` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/models/night-landscape.png` | 1823026 | `8f05bcac2709089321e59d57dac4dbbe0d6295a6ed5b550c930ea9d530bb274a` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/login/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/lizenzbedingungen/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/kontakt/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/impressum/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/free/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/datenschutz/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/checkout/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/brand/design-reference.jpeg` | 238669 | `2bfb44f2d888e463e7f9e9b581b02d775d59506146aa1d6b5b027e8bef889340` | binary | 0 | – |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/assets/head-ClEywaux.js` | 609404 | `f3299795fc13f9464cad583f2358838ad1d4e50f53b4dceab8289dcc798acc9d` | text | 4108 | 365:3, device:3, free:2, pro:493 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/assets/index-B5VcnuTb.js` | 25986 | `6a1582c5ab2eab975ba912ab873e80aa2ff9fe3c9bdc6055be7613b046d9c689` | text | 30 | marketing:2, checkout:7, Mollie:1, 365:2, license:4, free:25, pro:179 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/assets/index-CTlQCzBS.css` | 22734 | `973994132165e3d8813105149b3e7804704325171330fdf6b79aafbe818a7079` | text | 1 | license:4, free:1, pro:76 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/app/pro/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/dist/agb/index.html` | 3069 | `d89373f3b7962e24952a7d1ad142693c22f8e732fac36fe33fbde8a641a54566` | text | 8 | device:1, free:5, pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/accordion.tsx` | 2664 | `33e1c60ba503f4eb36f9a8b1f68b236174b11656d8efea6bac65abddda2f9019` | text | 78 | pro:12 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/alert-dialog.tsx` | 5301 | `ed0f1fc432bca4c72f9dd8741ae2268a00d2d3429ff1149bf463c4271b13d8e9` | text | 187 | pro:37 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/alert.tsx` | 2060 | `e760c470414c9e617d7292094146d906352fee3b1526b790a611d4a118e79196` | text | 76 | pro:14 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/aspect-ratio.tsx` | 406 | `b7fb499905e441a0602392ce118828425ad059079060109694d01f9fac00ad20` | text | 22 | pro:4 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/attachment.tsx` | 6132 | `dcb9e899f1322158f016d75c400fa8cce9b797ea49bec65528bac686cee2ec5c` | text | 207 | pro:36 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/avatar.tsx` | 3056 | `342f32b683937b826cdff2999d5e3057836d459aa43eadb0c3538b818d195b9a` | text | 109 | pro:18 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/badge.tsx` | 1934 | `5706189b86e8670499fb33f37147dd6f65c39d59eef5211e34157f2952c35e32` | text | 52 | pro:9 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/breadcrumb.tsx` | 2602 | `b28b76d6f8d0feafbbeff2220cf83f9a6b03d8c81f0145b3af4c7d19933ab2c0` | text | 122 | pro:25 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/bubble.tsx` | 4828 | `dfb9f52ae3b89e4a419b336c3893ab6fb658fc324fb402759d878d54e3b2db5a` | text | 128 | pro:18 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/button-group.tsx` | 2494 | `79ad8fb6644a775cc49131c1aa737ca26cae6a563beec0fa52ef6e8d85202fab` | text | 87 | pro:15 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/button.tsx` | 3247 | `081d2a1cb4f3aec636a6894d9eff4e90d476d5db85b82d0399c1f4d18517112e` | text | 58 | pro:5 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/calendar.tsx` | 8503 | `e7bc682eff8f2215e6b0aab40d1afb7ee927c5f5bef348ccff207631b9261658` | text | 231 | pro:18 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/card.tsx` | 2645 | `625fce5e16577a45108a86d7afcd70b8931cb2032abe0d6a3faf1010f666d672` | text | 103 | pro:21 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/carousel.tsx` | 5727 | `7444126492d4e0b85b1270f0d83a0955350fa95b3d3fb7b88edc2a5c2b4e5d14` | text | 242 | pro:22 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/chart.tsx` | 10581 | `56ab0e0b41f0cc7902414e046ea4f710bdbf0b756028672ea8c7e5137a278f2b` | text | 373 | pro:14 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/checkbox.tsx` | 1538 | `56b2869e5478f38238e6a3d8aefabfbe8af565b38b2ffad06466487b3eacf154` | text | 28 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/collapsible.tsx` | 664 | `3fdf7ef1ca89c4d85de5ecbb25813d0f572003a53b021baf43c5f3523e48ec97` | text | 21 | pro:9 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/combobox.tsx` | 9135 | `282041e2e8c52cc12e7bbc717bbd3f8c9c5ba18e7fa75b97053bc79687e1181e` | text | 300 | pro:47 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/command.tsx` | 5029 | `9c1eae65aa105935a34c6b736f673b71a2ef939dde53dce29d986221edbf1f9f` | text | 193 | pro:27 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/context-menu.tsx` | 8166 | `05c3646b452f5e3b9eb952eeba3d90657606d2b0875cb77652cdb5eadba0eb5c` | text | 272 | pro:46 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/dialog.tsx` | 4087 | `8bc85def62538b4e62e8530c6b0ba167a192c38519c05f104bf6e10de73b811f` | text | 159 | pro:30 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/direction.tsx` | 105 | `2dea8a95accb1723db2454ccc858697d5b1f1454568cf4da5e8fcbd0cf7cc1ee` | text | 6 | pro:2 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/drawer.tsx` | 11396 | `b7ac53d0e5d1fed25fc3f2ac5f5a36e247ca684c677ac376829fa8a7c039b79e` | text | 228 | pro:44 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/dropdown-menu.tsx` | 8809 | `efc088f3d79f64cf96e222701ae23dcf385b53947b3cd57ffb7be6f5dadcbfe2` | text | 272 | pro:46 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/empty.tsx` | 2415 | `bf54bac4881b79f6a53f55e70c18640f58a058add88aed763c71be35c4f64f59` | text | 104 | pro:20 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/field.tsx` | 6303 | `79023ca89aae39f9cffa83a9483c9c672099b4547cc821486283db61c6ae9327` | text | 238 | pro:32 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/hover-card.tsx` | 1863 | `d8cb7270c5893213fc00b5f270f9bc461e2d7ce5b81f77b8778253a1aeda6a2c` | text | 51 | pro:10 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/input-group.tsx` | 5289 | `2e65ddecb4401220be374cc6cfc42344538266cafeb2e590b3c760c7ed6b490a` | text | 158 | pro:21 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/input-otp.tsx` | 2558 | `867f568259caac95f682d128d72e681b3fe7c31701a396eacc9284401d917a6a` | text | 86 | pro:12 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/input.tsx` | 1046 | `6763c86c34c1c07826386d376f5da8fe2e41585bff3615716d5da88915e088d8` | text | 20 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/item.tsx` | 4888 | `9c5e45e6c4aae5b9c4c1304e1f1208d32681ab616a6e0de9de6e0d6b22690592` | text | 201 | pro:37 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/kbd.tsx` | 842 | `bdfb38a4f7b9b604e196b5cee0d86f12311dae72946f0dbf5928c8ad0638178f` | text | 26 | pro:6 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/label.tsx` | 524 | `e4a6fb662c44a44c468d16d79d02b3a3e5bf7b77bd50aef1e586c4d9613df0f6` | text | 20 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/marker.tsx` | 1962 | `cd1e872384cf5001e48b4dc3cc2bb011eba9700561d41c83a89e872b60baf175` | text | 71 | pro:15 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/menubar.tsx` | 8315 | `a3715f8e8b78261f5784929c532e100759c58e831c91e842438730797bc9a124` | text | 284 | pro:48 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/message-scroller.tsx` | 4070 | `9512c586d1b0885cf3ae4f1c3dd4281cbdfec7428fe98ff48a66b4ba2a7319f4` | text | 130 | pro:23 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/message.tsx` | 2246 | `2fedcc64ed8563a44f6697615e77574d96f819fe6e5e2fa8a555e30f8ed6bbd7` | text | 92 | pro:18 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/native-select.tsx` | 2133 | `3aafb74b98c039dae4eb2c64c47ec6f5d61fdc888c057de47550346f702f434b` | text | 65 | pro:11 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/navigation-menu.tsx` | 7436 | `c8e64bf5241145b512ae18f1062da8275691edf927736496a3860bec76ad6fa1` | text | 171 | pro:25 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/pagination.tsx` | 2928 | `1f3c1713e8824cca7c3c0edacf9da7b0114bfda58640771b8fe0bc6179b370ce` | text | 133 | pro:24 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/popover.tsx` | 2586 | `7376624438588e2d64b6e0c5cdf82cbc5fd4530bbcf1f0235c5f3ee08d12e877` | text | 90 | pro:19 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/progress.tsx` | 1751 | `0d8ddec9731940e104b851cf3ac67d2fa8589b289824317a9e8f326e090ba65a` | text | 83 | pro:47 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/radio-group.tsx` | 1843 | `43f2d6c2f5bdd4a26c57d93e6f141be20472f9bb8777d9a0d61cd8a5e281a999` | text | 38 | pro:6 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/resizable.tsx` | 1681 | `ea7b85817d4dc70866e0bcf15264e7e1bd7e1893eb4404261fbc23a4d6ff9029` | text | 50 | pro:9 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/scroll-area.tsx` | 1632 | `730c4cc49f8f1b705eb1389cd32c774056a0a2a7a48a9b092cbe44c608be3a0b` | text | 55 | pro:6 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/select.tsx` | 6700 | `45489c502a21fdd5271481d64ad8f762181c9653d8d26bdc6f75450b78c3c852` | text | 202 | pro:28 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/separator.tsx` | 551 | `92ad5065f03d7edc98f367e729f3ec84ece1d99ee8cd0d3a8137f266d4ab3d8a` | text | 25 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/sheet.tsx` | 4446 | `adb432b6f9d7a4733caa45ba8bf510a8a7ff0f6d0dd3aa1f013959fb61268234` | text | 137 | pro:30 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/sidebar.tsx` | 21779 | `aa3322ca63f098aa1d2abf750f9d097da07362fce25939357f2cefc9b6a03988` | text | 723 | pro:110 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/skeleton.tsx` | 278 | `4c342102b2bbf5bd8c04fa151fe5c13c42faee2f9587a3586c27322020ca35d1` | text | 13 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/slider.tsx` | 1879 | `af657e73d672f4dd205f19abf151d21a172cf36abfdca49fd7014a20e12367a9` | text | 52 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/spinner.tsx` | 360 | `8ddbb330e5564a1f53026da36c2322ed4b027687e91a88f63348ab10f26ae0cb` | text | 16 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/switch.tsx` | 1818 | `04b085443a1c6a72d408e6eb7dd45df881ca27814415b81b39f614806b52c8fc` | text | 32 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/table.tsx` | 2418 | `88f2ba7877eea7f34a5da18b7fa096eb2c7bed602677ce54f5494b494c5afc2e` | text | 116 | pro:24 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/tabs.tsx` | 3510 | `dd914d769bc223b5d5ea56839a7752e534eb475f8d2897d5675606c368bbca1f` | text | 82 | pro:14 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/textarea.tsx` | 847 | `7ae7f0f5d907be24658652c771fee1685193102bf3200aafbf578d144d379fbf` | text | 18 | pro:3 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/toast.tsx` | 7353 | `9126b09f47f0b117bf748cf19aaa4987a1f72d0813d10bfc4b4b0128e6439e48` | text | 229 | pro:37 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/toggle-group.tsx` | 3201 | `9b006523be0fe3230cd75f7adf78a501829d594fd3506c56c55bb38211ff1850` | text | 89 | pro:13 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/toggle.tsx` | 1770 | `6bf41d6f6ffe602c3e28274a82ac029e6ee1331ba3c670a6d814048e1823cc28` | text | 45 | pro:5 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/components/ui/tooltip.tsx` | 2855 | `b86e51969931c3d62e88d0bdacd1cd8219105dc6d6b6a588a80011bf92e987cd` | text | 66 | pro:18 |
| `PromptMaster-Commercial-Sicherung-2026-09-06.zip` | `frontend/.openai/hosting.json` | 128 | `f0edf586980b4bf42be68c4d7f4d8da814e74fdcbd08ca034113d989b247f57d` | text | 6 | pro:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/00_START_HERE.md` | 5905 | `88a9eab348c83438fc1ef9fcb05f403d2d1077d9e1c7c2625dd2c77f795083e3` | text | 173 | v13:1, v15:1, marketing:1, Mollie:4, 365:3, T-60:1, T-30:1, T-7:1, 2FA:2, free:1, pro:23, Caddy:2, Django:4, PostgreSQL:3, Redis:1, Celery:2, GitHub:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/01_MASTER_SPEC/PromptMaster_MASTER_SPEC_V1.0.md` | 46369 | `e5e6491322fc8d75c5086cc737743cbb55d0e7dcf806e515e5d62a8791d248fc` | text | 2577 | marketing:2, checkout:1, Mollie:34, 365:8, 2FA:7, device:13, license:15, free:10, pro:145, Caddy:7, Django:13, PostgreSQL:9, Redis:7, Celery:8, GitHub:3 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/02_LATEST_RC8_DOCUMENTATION/AGENTS.md` | 1011 | `144753b64981cac6fb351dfe33cd967a934b2fc6a6ee1b08fa3aecab88a07421` | text | 22 | Mollie:1, device:1, license:1, pro:4, Django:1, PostgreSQL:1, Redis:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/02_LATEST_RC8_DOCUMENTATION/README.md` | 1145 | `bfb965c00257cb0b5127f9cc10c233fc5dbeea2c2d88b968b7eb89fcbae82336` | text | 28 | Mollie:3, pro:5 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/02_LATEST_RC8_DOCUMENTATION/SPEC.md` | 46369 | `e5e6491322fc8d75c5086cc737743cbb55d0e7dcf806e515e5d62a8791d248fc` | text | 2577 | marketing:2, checkout:1, Mollie:34, 365:8, 2FA:7, device:13, license:15, free:10, pro:145, Caddy:7, Django:13, PostgreSQL:9, Redis:7, Celery:8, GitHub:3 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/AGENTS.md` | 1011 | `144753b64981cac6fb351dfe33cd967a934b2fc6a6ee1b08fa3aecab88a07421` | text | 22 | Mollie:1, device:1, license:1, pro:4, Django:1, PostgreSQL:1, Redis:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/Dockerfile` | 481 | `cd5af0352839ad99545a628d5a10cc91ad072fd16ed34f65878f8b579f9948f7` | text | 9 | PostgreSQL:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/README.md` | 3009 | `8f48b1e20e46d013b2455fa0115ac2d026afcead8baf4c820281ec5f0a12be5d` | text | 78 | checkout:1, Mollie:4, 365:1, 2FA:2, device:1, license:1, pro:10, Caddy:2, Django:4, PostgreSQL:2, Redis:2, Celery:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/SPEC.md` | 46369 | `e5e6491322fc8d75c5086cc737743cbb55d0e7dcf806e515e5d62a8791d248fc` | text | 2577 | marketing:2, checkout:1, Mollie:34, 365:8, 2FA:7, device:13, license:15, free:10, pro:145, Caddy:7, Django:13, PostgreSQL:9, Redis:7, Celery:8, GitHub:3 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/compose.staging.yaml` | 430 | `5e80346f0e3e5cd261a1da73b582278fbb84bbe3f085ab0763a074037748c0ab` | text | 20 | pro:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/compose.yaml` | 3907 | `291f894c3a805963999662d99d6a50ea92e3e5f1a0ed3675dbd164aa5cfa06b0` | text | 144 | pro:16, Caddy:9, PostgreSQL:3, Redis:9, Celery:2 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/03_PHASE2_ACTUAL_CODE_BASELINE/PromptMaster_V1_Phase2/scripts/bootstrap.sh` | 2677 | `904dcb6ee5a859558ee8eea06fdfff1532bf2c3e7f42c30b0aa4b010437f7f34` | text | 41 | pro:1, Caddy:2, Django:4, Redis:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_Kundenportal.html` | 42660 | `8472907d76febc0698b82db2fef3b6a8ef73163941152ff98ed415a7f80404be` | text | 229 | checkout:1, Mollie:11, 365:7, T-30:3, 2FA:5, device:9, license:13, free:1, pro:76, Caddy:2, Django:2, PostgreSQL:2 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip` | 16023 | `40fed976399b97a7c7d058aa028a257f285407d198acc15f31d9a61490122caa` | nested-zip | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/netstyle-admin.html` | 202 | `105251479d81fd8937acd680668e28dcd0da2a29d297c603c0fd82dc4a247d66` | text | 1 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/kundenportal.html` | 188 | `fa8c1a28bf28f022ce17510ee5d56979ad3e6b46cf0e5fd7c5935a7c5256684e` | text | 1 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/index.html` | 3088 | `58284c1532110e78a61e76d780b8ebfa04d8e3d0d48fff170145c228bf8ee3d4` | text | 3 | Mollie:2, device:1, pro:6 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/app.html` | 42956 | `5092fd0ae3ee0c2a97a41df90587282db6bbfced9cbea4c7803d2e71ea4c1b82` | text | 230 | checkout:1, Mollie:11, 365:7, T-30:3, 2FA:5, device:9, license:13, free:1, pro:76, Caddy:2, Django:2, PostgreSQL:2 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/README.md` | 1164 | `de2ba8b9407d9b1cebf37b87982a3f12f67e3575f63492fed738d4a4b147bf25` | text | 48 | Mollie:2, 2FA:2, pro:7, Django:1, PostgreSQL:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_UI_Prototype_V1_1_FIXED.zip::promptmaster-prototype-v1/SPEC.md` | 1371 | `831bc744acfe383312227ccd072fc6b11f75eacd434a9480efc0f8a0b9e40c3d` | text | 39 | Mollie:3, 365:4, T-60:1, T-30:1, 2FA:1, free:2, pro:7 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/PromptMaster_netstyle_Admin_V2.html` | 21426 | `75b547934f2166560acc3cd4687cba10b1f061e050e743121ff72584aea6dd42` | text | 289 | Mollie:7, 365:4, 2FA:3, device:1, free:2, pro:45, Caddy:1, Django:1, PostgreSQL:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/README.md` | 1164 | `de2ba8b9407d9b1cebf37b87982a3f12f67e3575f63492fed738d4a4b147bf25` | text | 48 | Mollie:2, 2FA:2, pro:7, Django:1, PostgreSQL:1 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/SPEC.md` | 1371 | `831bc744acfe383312227ccd072fc6b11f75eacd434a9480efc0f8a0b9e40c3d` | text | 39 | Mollie:3, 365:4, T-60:1, T-30:1, 2FA:1, free:2, pro:7 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/app.html` | 42956 | `5092fd0ae3ee0c2a97a41df90587282db6bbfced9cbea4c7803d2e71ea4c1b82` | text | 230 | checkout:1, Mollie:11, 365:7, T-30:3, 2FA:5, device:9, license:13, free:1, pro:76, Caddy:2, Django:2, PostgreSQL:2 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/index.html` | 3088 | `58284c1532110e78a61e76d780b8ebfa04d8e3d0d48fff170145c228bf8ee3d4` | text | 3 | Mollie:2, device:1, pro:6 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/kundenportal.html` | 188 | `fa8c1a28bf28f022ce17510ee5d56979ad3e6b46cf0e5fd7c5935a7c5256684e` | text | 1 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/04_UI_PROTOTYPES/promptmaster-prototype-v1/netstyle-admin.html` | 202 | `105251479d81fd8937acd680668e28dcd0da2a29d297c603c0fd82dc4a247d66` | text | 1 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/1000279014.png` | 440658 | `afeba547d12ae353dfdb84111473100aa4b680139eaa2eb7fc3689616d849714` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_detailed_infographic_style_project_plan_and_ui_u.png` | 1905661 | `07589b65f55ff6386edaa6f075c92c41626bbb3e719f8e4438952f3e58ba652d` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_detailed_ui_design_mockup_image_showing_a_saas_a.png` | 1519230 | `4fd621f222148dc242a0f74bcba251ce2c983a3a5a5ceddee3b0c18b756a12df` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_large_clean_modern_ui_ux_design_presentation_b.png` | 1888314 | `d3694fe7ecc82688d036ec0065782a0fe91aaef7c87ff1835a36519df34adc49` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_large_high_resolution_ui_ux_presentation_board.png` | 1989353 | `324d1925c1f28e1081322f2c0b56a83d0d842138e771dee01b00b5362757815a` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_large_multi_panel_ui_ux_design_presentation_post.png` | 1871105 | `44435260466d04ab52a194ecd6bfa6c48a5d87bc25317276bd11fca6ebcf34a0` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/a_wide_high_resolution_infographic_dashboard_ui_u.png` | 1963359 | `87847e3255c3b934cce0a67508851a5a515dcac5e16bfdd74a58ddac904641d7` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/logo_crop_final.png` | 27864 | `2224b72940ec799322fe635c9604034e98ad90022c21d79da9f820e4ab40ed0e` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/promptmaster_admin_dashboard_auf_desktop_und_mobil.png` | 1528049 | `5b6e3b36d5e56b530965094a8b78b7d7f26c55395b3b33e8539ccb5e34bf00be` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/05_DESIGN_REFERENCES/wide_clean_high_tech_ui_dashboard_mockup_collage.png` | 1639712 | `353153fac0b7c6961789988751f374572d20e8c6f0c44982364a5fa233271389` | binary | 0 | – |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/FILE_INVENTORY.md` | 2491 | `08545951cfbd0a1ad6a51451a52fbd63125aa1f5bf3290a3796d928a9fb5831a` | text | 35 | pro:35 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/MANIFEST.json` | 6452 | `95a4c7b9edb6e28df25cf068c45d58b3f3335e92ae5779c0e9814368f656567f` | text | 164 | 365:1, pro:36 |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12.zip` | `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12/SHA256SUMS.txt` | 3946 | `6b320c6ace63dc1d724b6fcd69e589230e5b8dffa0bdafb636243b03a40cbeef` | text | 32 | 365:1, pro:35 |
