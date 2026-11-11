# AGENTS.md — SupplementPacket

Canonical instructions for any agent or developer working in this repository. [CLAUDE.md](CLAUDE.md) adds product-specific guidance and defers to this file.

**State of the repository:** build milestone B1 (foundation and deterministic core) on branch `feat/b1-foundation` and B2 (sign-in, SMTP email, S3 storage, all local) on branch `feat/b2-local-auth`, neither merged. The owner authorised implementation on 2026-11-11, before the Phase 0 sales gate G1 passed ([verification-report-fixing.md section 9](verification-report-fixing.md#9-build-milestone-b1-2026-11-11)). Python packages under `apps/` and `packages/`, five Alembic migrations, scripts and tests exist. Sign-in is password plus TOTP with server sessions; email goes through SMTP to the local Mailpit and files through the S3 API to the local MinIO ([verification section 10](verification-report-fixing.md#10-build-milestone-b2-2026-11-11)). There is no web frontend, no real provider account and no deployment. Commands marked **exists** in [section 11](#11-utilities-index-b1) are implemented; every other command named in these documents is still **proposed**.

## 1. Reading order

1. [Decision.md](Decision.md): the question, the offer, the economics, the stop rule, rights to repair material, go-to-market.
2. [PRD.md](PRD.md): roles, must-haves `MH-01` to `MH-12`, metrics, the highest-cost mistake.
3. [App-flow.md](App-flow.md) and [design.md](design.md): screens `S-01` to `S-14`, states, wording, accessibility checks.
4. [TRD.md](TRD.md) and [schema.md](schema.md): architecture decisions `AD-nn`, API, jobs, tenancy, data.
5. [execution-plan.md](execution-plan.md): gates, tasks `T-p.m.t`, tests.
6. [verification-report-fixing.md](verification-report-fixing.md): what is checked, the risk register `R-01` to `R-22`, findings `F-nnn`, outstanding items.

## 2. Sources of truth

| Topic | File |
|---|---|
| Prices, pilot terms, refund test, gates, funnel, sources, legal questions | Decision.md |
| What the product must do and must not do | PRD.md |
| Routes, screen behaviour, states | App-flow.md |
| Wording, components, accessibility checks | design.md |
| Stack, API, jobs, AI boundaries, threat model | TRD.md |
| Tables, permissions, retention, migrations | schema.md |
| Task order, estimates, tests | execution-plan.md |
| Risks, traceability, findings, check status | verification-report-fixing.md |

A fact is stated once and cited elsewhere by section or ID. If two files disagree, the file in this table wins and the other is corrected in the same change.

## 3. Product boundaries

- No build task starts before gate G1, and no Phase 4 to 7 task before G1b ([execution-plan section 1](execution-plan.md#1-sequence-and-gates)). No call, real estimate, visit or invoice before the Phase 0 legal task that gates it is closed.
- The product never transmits anything to an insurer. Do not add email, portal, fax or API delivery to any party outside the shop.
- Only an Estimator or Owner of the tenant approves lines, freezes packets and marks them sent. No service, job, Operator or model does. Nothing is frozen that the freezing user has not seen in its final form: any change to a line, its evidence, its source or the email draft resets approval or the review.
- Licensed repair material is reference-only by default ([Decision 3.1](Decision.md#31-rights-to-supporting-repair-material)). No table or log stores procedure or estimating-guide text; there is no procedure upload and no automatic detection is claimed. No estimate line data is combined across tenants.
- Anything on the non-goals list in [PRD section 8](PRD.md#8-non-goals) needs the expansion evidence in PRD section 12 and a new must-have before work begins (R-21).

## 4. Architecture conventions

- Layout: `apps/web`, `apps/api`, `apps/worker`, `packages/core`, `packages/db`, `packages/files`, `packages/parsers`, `packages/obs`, `packages/ai` ([TRD section 5](TRD.md#5-building-block-view)). B1 implements all of these except `apps/web` and `packages/ai` (AI is blocked on LQ-01). `scripts/check_boundaries.py` enforces the import rules below.
- Apps import only public modules of packages. Apps never import each other. Packages never import apps.
- **Reuse before writing.** Money, dates, state transitions, key building, settings and logging each exist once. Search `packages/` before adding a helper; extend the existing one (R-03, R-06).
- Deterministic code for money, totals, differences, permissions, retention, the refund test and metrics. Models only inside the two functions in [TRD 8.7](TRD.md#87-ai-functions), behind consent, with fixtures.
- Every mutation takes an idempotency key; every edit checks `row_version`; job transitions compare `state_version`.

## 5. Tenant safety

- Every tenant-owned table has `tenant_id`, a row-level security policy and composite foreign keys ([schema section 1](schema.md#1-conventions)).
- Set the tenant at the start of each transaction from the session or the job row. Never accept a tenant identifier from request input.
- Object keys come from the key builder only. Never build a key from a user file name.
- A cache, search index, export or background job added later must carry the tenant in its key and be added to IT-01.
- Cross-tenant access returns 404.

## 6. Migrations

- One linear history. Expand first, contract one release later. Concurrent index builds. Batched resumable backfills ([schema section 9](schema.md#9-migrations)).
- Change the ORM model and the migration together; the parity check must pass.
- Never edit a merged migration. Never run DDL as the application role.

## 7. Tests

- A change is complete only with the tests named for its task in [execution-plan section 7](execution-plan.md#7-test-catalogue), using synthetic fixtures.
- Any new endpoint is added to IT-01 and IT-02. Any change to approval, evidence, freezing or sending reruns UT-07, UT-08, IT-06, IT-18 and E2E-01. Any change to responses, payments or the pilot report reruns UT-10, UT-11, UT-17 and UT-18.
- Real estimate PDFs, photos, names, VINs and claim numbers never enter the repository, tests, logs or prompts.

## 8. Which documents to update

| When this changes | Update |
|---|---|
| A requirement | PRD (must-have and metric), the traceability matrix, affected screen in App-flow, tasks and tests in execution-plan |
| A screen or route | App-flow, design (screen description and accessibility map), the traceability matrix, E2E tests |
| A permission or role | PRD section 5, schema section 5, TRD 8.2 and 8.3, IT-02 |
| A table, field, index or constraint | schema (dictionary, index table, migration notes), TRD API if exposed, parity test |
| An operating assumption (price, rate, hours, hosting cost, retention) | Decision (and rerun its arithmetic), then every file that cites the section |
| A source or legal answer | Decision section 13 and section 11; the outstanding items table |
| A risk or its control | The risk register only; other files cite the ID |

## 9. Git hygiene

- Branch names: `T-<phase>.<milestone>.<task>-short-slug`. One open branch per task. Delete a branch only after it is merged (R-22).
- Commits name the task and, where relevant, the must-have.
- No credentials, tokens, customer files or real data in any commit. No generated framework files, virtual environments, caches or local runtime data (`.gitignore` excludes `.venv`, `node_modules`, `.env*`, caches, build output and `.run/`).
- The final remote commit identifier is recorded in the lead's coordination ledger, not in this repository.

## 10. Reporting completion accurately

- Say "planned", "implemented" or "verified" and nothing vaguer. "Verified" needs the test ID and its result.
- Application checks stay `Not run` in the verification file until they have been run against real code.
- State what was not done. Never report a control as present because a document describes it. Never upgrade an unverified source.
- Review findings use `F-nnn` and belong to the reviewer; author checks use `SC-nn`.

## 11. Utilities index (B1)

Search here before adding a helper (R-03). Each lives once; `scripts/check_boundaries.py` fails the build on a second definition of the names it tracks.

| Need | Module | Notes |
|---|---|---|
| Parse, format and round money; accept money input | `packages/core/src/sp_core/money.py` | Integer cents; exact half-up rounding, and `round_up`/`round_down` for shop-favour rounding in the refund test; `cents_from_input` refuses floats; never floats |
| Request input checks, free-text caps and notice | `apps/api/src/sp_api/services/inputs.py` | 422 on any untyped, missing or oversized field |
| Business days, pilot day boundaries | `packages/core/src/sp_core/dates.py` | Weekends only; no holiday calendar in B1 |
| Settings (both processes) | `packages/core/src/sp_core/settings.py` | Refuses to start without `PUBLIC_BASE_URL`, `DATABASE_URL`, `STORAGE_BUCKET`, `SESSION_KEY` |
| Totals reconciliation | `packages/core/src/sp_core/reconcile.py` | Tolerance USD 0.01 |
| Estimate diff | `packages/core/src/sp_core/diff.py` | `ENGINE_VERSION`; `needs_review` rule |
| Approval checks and fingerprints | `packages/core/src/sp_core/approval.py` | Line fingerprint, review components and fingerprint, freeze blockers |
| Email draft and its amount rule | `packages/core/src/sp_core/email_draft.py` | UT-19 |
| Three-amount ledger, response and payment rules | `packages/core/src/sp_core/ledger.py` | UT-09, UT-10, UT-17, UT-18 |
| Baseline, refund test, PM-1, PM-2, qualifying units, counts in force | `packages/core/src/sp_core/pilot.py` | Decision 5.1; UT-11, UT-12; `qualifying_units` (one per repair order), `counts_in_force` (count history) |
| Permission table | `packages/core/src/sp_core/permissions.py` | Schema section 5 |
| Job state machine | `packages/core/src/sp_core/jobs.py` | Compare-and-set on `state_version` |
| Reference URL rule, photo attestation | `packages/core/src/sp_core/evidence.py` | AD-06 |
| Logging, correlation, redaction | `packages/obs/src/sp_obs/__init__.py` | No web-framework import |
| Object keys, stores, signed URLs, content sniffing | `packages/files/src/sp_files/__init__.py` | Key builder is the only way to make a key; `S3ObjectStore` (S3 API, MinIO locally) and `store_from_settings` choose the store for API and worker (B2) |
| Photo metadata removal | `packages/files/src/sp_files/metadata.py` | `strip_metadata`: JPEG and PNG, standard library only; HEIC not supported (B2) |
| Password hashing and policy, TOTP, tokens, secret encryption | `packages/core/src/sp_core/auth.py` | scrypt; RFC 6238; `hash_token`; AES-GCM under a key derived from `SESSION_KEY` (B2) |
| Sign-in, sessions, invitations, password reset, throttle | `apps/api/src/sp_api/services/auth.py`, routes in `apps/api/src/sp_api/auth_routes.py` | Limits in the module docstring and TRD 8.2 (B2) |
| Session cookie, anti-forgery token, origin check | `apps/api/src/sp_api/context.py` | `SESSION_COOKIE`, `csrf_token`, `check_csrf` (B2) |
| Email (SMTP) | `apps/api/src/sp_api/mailer.py` | `SmtpMailer`; Mailpit locally, a provider by settings (B2) |
| Packet renderer interface | `packages/files/src/sp_files/render.py` | Deterministic stand-in only in B1 |
| Parser interface and registry | `packages/parsers/src/sp_parsers/__init__.py` | No real parser yet (T-3.1.3 blocked) |
| ORM models, tenant transaction | `packages/db/src/sp_db/models.py`, `session.py` | `tenant_transaction` sets tenant, user, role and correlation ID |
| Approval reset, immutability, append-only audit | Migrations `20261111_0001` to `20261111_0005` (SQL functions and triggers) | `sp_reset_line` is the one reset function; approver demotion resets approvals |

| Command | State | What it does |
|---|---|---|
| `make venv` | exists | Creates `.venv` with `tools/requirements.txt` and puts the source directories on its path |
| `make dev` | exists | Bootstraps the role, migrates and seeds `supplementpacket_dev`, starts API (port 8103) and worker, waits for readiness; exits non-zero naming the unhealthy service. B2: also checks that MinIO storage (through `/readyz`) and the Mailpit SMTP port answer. No Docker or web |
| `make stop` | exists | Stops the API and worker started by `make dev` |
| `make test` | exists | Drops and re-migrates `supplementpacket_test`, runs every test. B2 tests use the local Mailpit and MinIO (credentials from `.env`) and skip, saying why, when either is not running |
| `make lint`, `make typecheck` | exist | ruff (check and format) and mypy strict |
| `scripts/check_boundaries.py` (`make boundaries`) | exists | Import rules and single-home helpers |
| `scripts/check_migration_heads.py` (`make heads`) | exists | One linear history |
| `scripts/orm_parity.py` (`make parity`) | exists | Migrated test database against ORM metadata, plus row-level security and trigger catalog check |
| `scripts/seed_synthetic.py` | exists | Two synthetic tenants; B2: fresh random passwords and authenticator secrets for the synthetic users in `.run/dev-credentials.json` (untracked, mode 600); no sessions are created |
| `scripts/reset_db.sh` | exists | Resets one of this product's two databases only |
| `scripts/run_backfill.py`, `restore_drill.sh`, `replay_deletions.py`, `load_parse.py`, `link_crawl.py` | proposed | Not in B1 |
