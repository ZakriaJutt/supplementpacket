# Verification, findings and fixes — SupplementPacket

This file separates what was checked on the documents from what can only be checked on an application that does not exist yet. It is the single home of the production risk register. The final remote commit identifier is kept in the lead's coordination ledger, not here.

## 1. Status summary

| Item | Status |
|---|---|
| Ten planning files written | Yes, 2026-11-10; revised in fix round 1 |
| Application | Build milestone B1 (foundation and deterministic core) implemented on 2026-11-11 on branch `feat/b1-foundation`, authorised by the owner before the Phase 0 gate G1. Tests that ran are recorded in [section 9](#9-build-milestone-b1-2026-11-11); every other application check is `Not run` |
| Customer evidence | None. No interview, no message sent, no pilot |
| Review | Independent review round 1: 16 findings (0 blocker, 10 major, 6 minor), all answered in [section 6](#6-findings-register). Retest on 2026-11-11 (`supplementpacket-round2.md`): 9 closed, 7 closed with a part open, 0 still open, no new findings. Residues named at that retest were edited afterwards and checked by the lead only. Verdicts transcribed into section 6 by the lead, unchanged |
| Highest-consequence failure | **An unapproved or unsupported line reaches an insurer** ([PRD section 9](PRD.md#9-highest-cost-user-mistake)) |
| Most important unproven assumption | That closed and live ROs carry enough supportable missed work for collected cash to exceed the shop's baseline ([Decision section 9](Decision.md#9-stop-rule)) |
| First paid-pilot milestone | [M0.3](execution-plan.md#milestone-m03--paid-pilots-delivered-by-hand-and-decided): signed agreement and USD 149 paid, delivered by hand |

## 2. Checks performed on the documents

| Check | Method | Result |
|---|---|---|
| Exactly ten required files, no others | Directory listing | Pass |
| Internal links and anchors resolve | Scratch script outside the repository | Pass (SC-01) |
| Every `MH`, `T`, `S`, `AD`, `DD`, `UT`, `IT`, `E2E`, `R`, `SRC`, `LQ` identifier referenced is defined | Scratch script | Pass (SC-02) |
| Every must-have in the traceability matrix | Scratch script | Pass, 12 of 12 (SC-03) |
| 22 risk rows, each with an existing task | Scratch script | Pass (SC-04) |
| Screens, endpoints, tables and tasks agree | Scratch script plus reading | Pass with the notes in SC-05 |
| Arithmetic re-run: unit economics, break-even, base, downside and fallback ramps, binomials, hours, phase totals | Scratch script using the rules printed in Decision 7.4 | Pass (SC-06, SC-08) |
| Competitor pages opened | Fetched 2026-11-10 | SupplementAI, Repairscope, VaraFix opened; CCC blocked; Audatex terms not found |
| Legal texts read | Fetched 2026-11-10 | Washington rules read only in archive captures (labelled `[S-arch]`; three sections are pre-amendment captures); 16 CFR 310.3 and 310.6, 47 CFR 64.1200 and the Canadian texts read at the live source |
| ASVS and WCAG text read before citing | Local copy of ASVS 5.0.0 chapter files; WCAG 2.2 Recommendation | Read; gaps stated as not met |
| Synthetic examples only; no credentials | Reading | Pass. Names, addresses and RO numbers in examples are invented |

## 3. Application checks planned

Definitions are in the [test catalogue](execution-plan.md#7-test-catalogue). Results of the tests that ran in B1 are in [section 9](#9-build-milestone-b1-2026-11-11).

| Area | Tests | Status |
|---|---|---|
| Rules and arithmetic | UT-01 to UT-19 | B1: Pass except UT-03 and UT-15, Not run |
| Tenancy, permissions, provisioning | IT-01, IT-02, IT-16, IT-20 | B1: IT-01, IT-02, IT-16 Pass; IT-20 Not run |
| Jobs, idempotency, bulk | IT-03, IT-04, IT-05 | B1: Pass (IT-03 adapted) |
| Approval integrity | IT-06, IT-18, UT-07, UT-08, UT-19 | B1: Pass |
| Ledger evidence | UT-10, UT-17, UT-18 | B1: Pass |
| Migrations and recovery | IT-07, IT-08, IT-09, IT-14, IT-17 | B1: IT-07 Pass (scripts, no CI); others Not run |
| Files, retention, links, logging, licensed-material controls | IT-10, IT-11, IT-12, IT-13, IT-15, IT-19 | B1: IT-11, IT-12, IT-13, IT-15, IT-19 Pass (IT-12, IT-13 adapted); IT-10 Not run |
| Workflows | E2E-01 to E2E-09 | B1: E2E-01, E2E-02, E2E-06 Pass at API level only; E2E-04 Pass at API level for the freeze double-submit only; E2E-09 Pass adapted; others Not run |
| Accessibility (manual, [design section 8](design.md#8-accessibility-map)) | T-6.1.3 | Not run |
| Security controls ([TRD 11.3](TRD.md#113-threat-model)) | T-6.1.4 | Not run |
| Load and restore targets ([TRD section 10](TRD.md#10-quality-requirements)) | T-6.1.5, T-7.1.1 | Not run |

## 4. Traceability matrix

| Must-have | Screen or API | Design or architecture decision | Schema or permission | Task | Planned test |
|---|---|---|---|---|---|
| MH-01 | S-04; `POST /ros/{id}/documents` | AD-09 | `repair_orders`, `documents` unique by hash | T-3.1.1 | IT-03, E2E-01 |
| MH-02 | S-05; `/documents/{id}/reconcile` | AD-04, AD-08 | `parse_runs`, `estimate_lines` | T-3.1.3, T-3.1.4 | UT-02, UT-03, E2E-02 |
| MH-03 | S-06; `POST /ros/{id}/diff` | AD-04, DD-03 | `diff_runs`, `supplement_lines.match_state` | T-4.1.1, T-4.1.3 | UT-04, UT-05, UT-06 |
| MH-04 | S-06; `GET /checklist` | AD-12, DD-03 | `checklist_versions`, `checklist_items` | T-4.1.2 | E2E-01 |
| MH-05 | S-07; `/lines/{id}/photos`, `/references` | AD-06, DD-04, DD-07 | `photos` attestation fields, `reference_citations.material_type` and URL check, `line_evidence` | T-4.2.1 | IT-05, IT-15 |
| MH-06 | S-06, S-08; `/lines/{id}/approve`, `GET /ros/{id}/packet-review`, `POST /ros/{id}/packets` | AD-07, DD-02 | `supplement_lines` approval reset rule and fingerprint; `packets.review_fingerprint`; approve and freeze permissions | T-4.2.2 | UT-07, UT-08, IT-02, IT-06, IT-18 |
| MH-07 | S-09; `/packets/{id}/mark-sent` | AD-05, DD-05 | `packets`, `packet_lines` snapshot | T-4.2.3, T-4.2.4 | UT-19, E2E-01, E2E-04, E2E-06 |
| MH-08 | S-10, S-11; `/packet-lines/{id}/response`, `/ros/{id}/payments`, `/packets/{id}/remittance-documents` | DD-01, AD-08 | `packet_lines` response checks and carry-forward, `payments` packet and remittance rules, ledger `ro_ledger` (computed in `sp_core.ledger` in B1, no SQL view) | T-5.1.1, T-5.1.2 | UT-09, UT-10, UT-17, UT-18, E2E-01 |
| MH-09 | S-12; `GET /pilots/{id}/report`, `PATCH /pilots/{id}/counts` | DD-01 | `baseline_ros`, `pilots` counts | T-5.1.3 | UT-11, UT-12, E2E-07 |
| MH-10 | S-01, S-02, S-13, S-14; `/auth/*`, `/users`, `/audit`, `/operator/tenants` | AD-02, AD-11 | `memberships`, `operator_grants`, `audit_events`; section 5 permissions | T-2.2.1, T-2.2.2, T-2.2.3, T-2.2.4 | IT-01, IT-02, IT-16, IT-20 |
| MH-11 | S-13, S-14; `/exports`, `/packets/{id}/takedown`, `/deletion-requests` | AD-06, AD-09 | Retention, takedown and deletion rules in schema section 8 | T-5.1.4, T-7.1.4 | IT-10, IT-14, IT-19 |
| MH-12 | S-03, S-04, S-07, S-09; `GET /jobs/{id}` | AD-03 | `jobs` with `state_version` | T-3.1.2, T-4.2.1 | UT-13, IT-03, IT-04, IT-05, E2E-03 |

## 5. Production risk register

The only home of the 22 risks. Other documents cite the ID. Tests are `Not run` unless a row says *B1: Pass*, with the run recorded in [section 9](#9-build-milestone-b1-2026-11-11).

| ID | Risk | Impact for this buyer and data | Prevention | Detection signal | Test and expected outcome | Task |
|---|---|---|---|---|---|---|
| R-01 | Out-of-order or duplicate events overwrite a newer job state | A late "running" event shows a finished estimate as still reading, or an old render replaces a packet PDF so the file no longer matches the frozen lines the estimator approved | Compare-and-set on `jobs.state_version`; render keyed by packet; PDF hash stored at first success | Log count of discarded stale transitions; hash mismatch alert | IT-04, UT-13: final state stays `succeeded`, one set of lines. *B1: Pass, IT-04 and UT-13 (unit and database)* | T-3.1.2 |
| R-02 | A caller timeout prevents reconciliation with a later completion | On a slow shop connection the upload appears to fail; the estimator uploads again and gets duplicate lines or thinks nothing happened | Idempotency key; uniqueness by file hash; state read from `GET /jobs/{id}` | Duplicate-key hits per day | IT-03: one document, one job, result visible after the aborted call. *B1: Pass, IT-03 (adapted: repeat with the same key; a mid-request abort was not simulated)* | T-3.1.2 |
| R-03 | New utilities duplicate shared behaviour | A second rounding or business-day helper makes the ledger total differ from the packet total by a cent, which an adjuster or owner will notice | Money, dates and state transitions exist once in `packages/core`; duplicate-name check | Boundary script output in CI | UT-01 and the boundary script: a duplicated helper fails the build. *B1: Pass, UT-01 and the boundary script with a seeded duplicate helper* | T-2.1.1 |
| R-04 | Applications import private code across boundaries | The web app or worker reaches into API internals and freezes a packet through a path that skips the approval check | Import rules: apps import only package public modules | Boundary script | Boundary script fails on a seeded illegal import. *B1: Pass, boundary script with a seeded app-to-app import* | T-2.1.1 |
| R-05 | Tenant enforcement scattered or bypassed | Shop A sees shop B's estimates, claim numbers and per-insurer approval history; the two may be competitors in the same town | Row-level security, composite keys, tenant-prefixed object keys, one tenant per job; no cache in the MVP | Failed-authorization log; daily query for rows whose parent tenant differs | IT-01: every endpoint and the worker return nothing for another tenant. *B1: Pass, IT-01 (37 routes with identifiers, body references, worker, zero rows without tenant)* | T-2.2.1 |
| R-06 | Workers copy configuration and utilities | The worker deletes files on a different retention period, or accepts sizes the API rejects | One typed settings module read by both processes | Start-up log prints a settings fingerprint; mismatch alert | IT-10 run with a changed setting: API and worker act on the same value | T-2.1.1 |
| R-07 | Worker logging imports web-only modules | The worker crashes at start; uploads stay queued and no packet can be built on a shop's busy day | `packages/obs` has no web-framework import; worker image built without web dependencies | Worker health check; queue-age alert | IT-13: worker starts healthy in its own image. *B1: Pass, IT-13 (adapted: subprocess without web modules, not a separate image)* | T-2.1.4 |
| R-08 | ORM omits indexes or constraints in migrations | The duplicate-file constraint exists in production but not in tests, or the reverse; duplicate documents double the requested total | Parity job compares a migrated database with ORM metadata | CI failure | IT-07: a model missing an index fails the build. *B1: Pass, IT-07 (injected model-only index reported)* | T-2.1.3 |
| R-09 | Interrupted migrations or backfills cannot resume | A half-finished backfill leaves some lines without `approved_row_version`; those ROs cannot be frozen | Batched backfills with a progress row; each batch one transaction | Backfill progress not `done` after deploy | IT-08: killed backfill resumes, no row twice | T-6.1.2 |
| R-10 | Merged branches introduce conflicting migration order | Deploy stops with two heads while shops wait for a fix | Linear history; head check in CI | CI failure | IT-07: second head fails the build. *B1: Pass, IT-07 (second head reported)* | T-2.1.3 |
| R-11 | Index creation locks busy tables | At month end, when estimators record responses, writes to `packet_lines` or `audit_events` block | Concurrent index builds with a lock timeout; constraints added not valid, then validated | Lock-wait metric during deploy | IT-09: writes continue while the index builds | T-6.1.2 |
| R-12 | Correlation IDs lost, or sensitive data in logs | A failed parse cannot be traced across retry; or VINs, claim numbers and owner names leak into logs kept longer than the source files | Correlation ID in job rows; redaction filter; logs carry identifiers and states only | Log scan for VIN and claim-number patterns | IT-11: one ID across request, job and retry; scan finds nothing. *B1: Pass, IT-11* | T-2.1.4 |
| R-13 | Upload keys collide or fail to isolate tenant, source and purpose | A photo from another vehicle or shop lands on a line and goes into a packet: part of the highest-consequence failure | Key scheme with tenant, RO, purpose, document and hash; evidence bound to the RO by composite key | Daily check that every key prefix matches its row | UT-14, IT-01. *B1: Pass, UT-14, IT-01* | T-2.2.5 |
| R-14 | Temporary uploads survive retention or failed cleanup | Abandoned estimate PDFs with vehicle-owner details remain after the shop was told they are deleted | 24-hour lifecycle rule on the temporary prefix; daily resumable sweep | Count of objects older than their expiry | IT-10: objects gone, second run idle | T-5.1.4 |
| R-15 | Missing persistent volumes cause data loss | Frozen packets and the ledger vanish after a service is recreated; the shop cannot show what it sent and the refund test cannot be computed | Production keeps no state on the VM; local and staging use named volumes | Row and object counts after deploy | IT-17: everything present after recreating containers | T-7.1.1 |
| R-16 | Generated links use internal hosts | The packet download or reset link points at `localhost`; the estimator cannot get the PDF to send | Links built only from `PUBLIC_BASE_URL`; start-up refuses without it | Link host check in smoke test | IT-12. *B1: Pass, IT-12 (adapted: internal Host header, no proxy)* | T-2.2.5 |
| R-17 | No reliable single start command and health checks | The developer tests the parser against a stack with no worker and ships a broken upload | `make dev` with health checks for every service | Health summary | E2E-09: healthy in 90 seconds from a clean clone. *B1: Pass, E2E-09 (adapted: no Docker; API, worker, database)* | T-2.1.2 |
| R-18 | Back, refresh or deep links lose state | The estimator loses a half-reviewed set of lines, or Back shows an editable review of a frozen packet | Server-held state; URL-held filters; saves on field change | Client error reports on navigation | E2E-03 | T-5.1.5 |
| R-19 | Bulk processing skips files, hides partial failure, or duplicates on retry | A photo the estimator believes is attached is missing from the packet, or a retried photo batch attaches a file twice | Per-item results; retry skips completed items; photo uniqueness by hash | Jobs in `partial` state per day | IT-05: 7 attached, 2 reported, retry adds none twice. *B1: Pass, IT-05* | T-4.2.1 |
| R-20 | Unclear labels, stale routes, broken links | "Approved" is read as the insurer's approval when it means the estimator's, and a shop reports cash it has not been granted | Fixed wording: "Approved by you" for lines, "Insurer approved" for amounts; link crawl | Crawl report; wording review with an estimator | E2E-08: no broken link or unlabelled control | T-5.1.5 |
| R-21 | Unrequested features consume effort | Time goes to approval-likelihood scores, a Mitchell parser or integrations before any shop has shown collected cash | Every merge names an MH or task; non-goals list; expansion evidence rules | Scope review | T-7.2.3 review: no feature without a requirement | T-7.2.3 |
| R-22 | Misnamed, duplicate or stale branches | A parser fix for a pilot shop sits on a forgotten branch, or unmerged work is deleted | Branch names carry the task ID; one open branch per task; weekly prune of merged branches only | Branch list older than 14 days | T-7.2.3 review: no stale or unlabelled branch | T-7.2.3 |

None of the 22 is judged not applicable. R-05 would widen if a cache or search index were added (keys must then include the tenant); R-15 would return in production if state were ever stored on the VM.

## 6. Findings register

Independent review round 1 (2026-11-10), 16 findings. The author made every fix below and is the owner of each. The author did not dispute any finding. Retest results are the reviewer's to give.

| ID | Severity | File (as reported) | Evidence | Impact | Owner | Fix made | Retest condition | Retest result |
|---|---|---|---|---|---|---|---|---|
| F-001 | major | schema 3; TRD 6.2, 8.1; PRD MH-06, MH-07; App-flow S-06 to S-08; execution-plan tests | Approval reset covered line fields only; evidence, diff re-run, source-line edits and the email draft were outside it | An unseen photo, reference or email text could be frozen under the estimator's approval | Author | Lead ruling applied. Any change to a line, its evidence, an attestation, a linked source line, or a changing diff re-run returns the line to draft (schema reset rule, one function plus triggers). Freeze must carry the review fingerprint the screen displayed (lines, evidence, email draft, recipient); mismatch gives 409 and a reload. Email draft is generated plus one paragraph and may contain no other amount. Batch approval removed. Hand-run kit: draft watermark, approval sheet listing evidence, new sheet after any change. Tests UT-07 widened, UT-19, IT-18 added. Round 2 residue: batch approval removed from T-4.1.3 and R-19. Residue edited after retest; checked by the lead, not re-reviewed | Requirement, schema, TRD, screen and tests state the same rule; evidence swap between approve and freeze is refused | Closed, part open: execution-plan T-4.1.3 acceptance check and R-19 impact still name batch approval, which was removed; SC-09 says none remain (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-002 | major | Decision 5.1, 9, 12.1; PRD PM-1, PM-4, MH-09 | Refund test and gate C were gross; 33.3 and the under-34 disqualifier mixed an incremental rate with a gross threshold; PM-1 shop total undefined; no false-stop figure; build committed before gate C | Threshold could pass with no incremental cash | Author | Lead ruling applied. Refund test = approved on qualifying packets minus baseline approved per insurer-paid RO times window RO count; gate C both limbs in incremental collected dollars per shop per window (PM-1 shop total). Derivation redone: 1,000 / (0.20 x 150) = 33.3 insurer-paid repairs; refund owed to 46.6%, 28.6%, 3.1% of 34-, 40-, 60-repair shops under the stated illustration. Cut-off rule for baseline rows stated with its bias. Gate C false stop given for limb 2 (7.3%, 26.4%), limb 1 stated not computable. G1 now releases Phases 1 to 3 only; G1b (interim gate C, week 21) releases the rest; FD-03 added. **Open:** limb 1 false-stop needs pilot variance data. Round 2 residue: incomplete baseline rows can no longer lower the baseline (declared supplemented count; scaled at 80% or more complete, otherwise highest complete row, shop's favour), in Decision 5.1, the agreement contents, PRD metrics, schema `pilots` and UT-11. Residue edited after retest; checked by the lead, not re-reviewed | Definitions are incremental and in one unit; arithmetic reproduces | Closed, part open: gate C limb-1 false stop needs pilot variance data; baseline rate is understated when supplemented baseline rows are incomplete or omitted (no completeness rule) (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-003 | major | schema payments and ledger; PRD MH-08; App-flow S-10 | Collected had no document, no packet attribution, no bound; approved could double count after supersede | The decisive number was the least evidenced | Author | Supplement payments must name a packet; `remittance` document purpose and `remittance_document_id`; only evidenced payments count in PM-1, PM-2, gate C and the report; unevidenced shown apart; collected above approved needs a reason; proposed split against the original-estimate balance; `supplement_repayment` kind. Approved defined on the same live packet set as requested, with carry-forward of responses and re-pointing of payments on supersede. Tests UT-17, UT-18. Round 2 residue: wording made consistent (users never edit payments; the system re-attributes on supersede with an audit event). Residue edited after retest; checked by the lead, not re-reviewed | Ledger definitions, screen and tests agree; supersede-after-response counted once | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-004 | major | Decision 1, 12.5 | Outreach copy stated the refund without its conditions; Decision 1 said recovered | A shop could be refused a refund it was offered unconditionally | Author | Decision 1 row matches 5.1. Email states the incremental test and all three conditions and points to the agreement. Phone script carries no price or refund | Both messages consistent with 5.1 | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-005 | major | Decision 3.1; PRD MH-05, MH-11; schema; TRD AD-06, 8.7, 11.3; App-flow S-07, S-14; IT-15 | Guard covered only a typed upload; screenshots, pasted text, deep links, allow-list ownership and purge were unaddressed | Licensed material could enter a packet with default settings | Author | Claim withdrawn: no automatic detection is asserted; residual risk stated in Decision 3.1 and TRD 11.3 as not prevented. Controls added: no procedure upload path (allow-list removed from the MVP), unticked attestation per photo batch, notices on free text, `material_type` with no URL for subscription-portal procedures or guides (Toyota linking clause recorded), AI-2 off until LQ-01 and LQ-02 close, Owner takedown that purges a frozen packet's files (IT-19). LQ-01 widened to the insurer's estimate; LQ-02 widened to whether a citation itself is disclosure. **Open:** LQ-01, LQ-02 need the licence texts and counsel | Withdrawn claim absent everywhere; residual risk and takedown present | Closed, part open: LQ-01 and LQ-02 need licence texts and counsel; detection is not claimed and the residual risk is stated (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-006 | major | Decision 12.4, 12.5, LQ-03; execution-plan T-0.1.1 | B2B exemption stated without the 310.3(a)(2) and (4) carve-out; out-of-state reach and penalties of RCW 19.158 missing; script stated price and refund | Exposure on the first call understated | Author | 16 CFR 310.3 and 310.6 reread at eCFR; RCW 19.158.050, .100, .110, .120, .140, .150, .160 reread in the 2026-01-19 archive capture (labelled). Decision 12.4 restates both, including the misdemeanor, civil penalty and criminal classes. Default is now registration before the first call; price and refund only in writing; fallback marked conditional on counsel and LQ-05. T-0.1.1 gates every call. **Open:** LQ-03 itself, and the registration fee, need the Department of Licensing or counsel | 12.4 accurate against the texts; script free of price and refund | Closed, part open: LQ-03 answer and the registration fee need the Department of Licensing or counsel (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-007 | major | Decision 7.4, 8, 12.3, 12.4 | Pool under the in-person fallback not shown | Plan's own constraint yields fewer pilots than the ramp | Author | Decision 8 tabulates three cases (639, 1,112, 357). Fallback: 11.4 demos, 2.9 pilots, 2.1 continuing, peak 2.34 accounts, cumulative -8,096 at month 12; gate B read at 11 demos (false stop 19.7%); four pilots for gate C not expected. The ramp states that it assumes the registered, remote case | Both cases shown with the one the ramp uses | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-008 | major | Decision 6, 7.2, 7.4, 12.6, 12.8; PRD CM-2 | Base ramp kept 96% of pilots against a 3-of-4 target | Base case optimistic against its own target | Author | One continuation rate, 75% [A], defined once in Decision 6 and used in 7.2, 7.4, 8, 12.6, 12.8 and CM-2. Base ramp recomputed: peak 6.12 paying accounts, trough -8,292 in month 10, never cumulatively positive to month 18. Break-even at that rate added (7 and 40) beside the chat's 6 and 37 | Reviewer's variant reproduces the table | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-009 | major | Decision 7.1, 7.4; execution-plan 5 | Build priced at 160 hours only | Cash required understated | Author | 7.1 shows the chat figure and the author's range (now 332 to 488 hours after the round 1 additions = USD 24,057.97 to 35,362.32); 7.4 gives the trough with the build bought (USD 32,350 to 43,654). Counsel, accountant and registration fee listed as missing inputs with their effect per USD 1,000. **Open:** those three costs need quotes | Both figures shown; range used in the cash statement | Closed, part open: counsel, accountant and registration costs are missing inputs, not in the ramp (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-010 | major | execution-plan 1, 2, M0.1; Decision 5, 11 | Only LQ-03 had a task; live data, visits and invoices could start with questions open | Phase 0 could handle real data and money ungated | Author | Every LQ has a task and an exit placed before the step it blocks: T-0.1.1 (LQ-03, first call), T-0.1.2 (LQ-01, LQ-02; a shop stays blocked while its row is not obtained), T-0.1.5 (LQ-04, first invoice), T-0.1.6 (LQ-05, first visit), T-0.1.7 (LQ-06 and the hand-run data handling rule, first real estimate). G0 lists them. **Open:** the answers | Each LQ maps to a task; G0 lists them; handling rule stated | Closed, part open: answers to LQ-01 to LQ-06 pending; each now blocks its step (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-011 | minor | Decision 7.4, 12.8 | Downside figures not reproducible; two acquisition-timing bases | Figures could not be rebuilt from the text | Author | Exact recurrences printed for base and downside; downside is now -13,660 / -17,730 and -65,834 / -95,991. Acquisition booked at USD 600 when a pilot is paid, everywhere; 12.8 shows 1,040, 2,800, 4,800 and reconciles to the ramp at months 1, 2 and 3; earlier cash timing noted | Reviewer's script reproduces both | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-012 | minor | Decision 0, 2, 12.4, 13; PRD 2, 9 | Archive captures carried the label for sources read live | Quoted text may not be the text in force | Author | New label `[S-arch]` on every claim resting on a capture; per-section capture dates in SRC-04 to SRC-06; -390, -320 and -380 marked pre-amendment, current text unverified. **Open:** the live official text could not be reached | Labels and dates present | Closed, part open: live official Washington text unreachable (also for the reviewer on 2026-11-11); -390, -320, -380 are pre-amendment captures (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-013 | minor | design 4 | One token for two meanings of approved | Works against R-20 | Author | Tokens split: `insurer-approved` and `estimator-approved`; the line chip reads Approved by you | Two tokens | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-014 | minor | TRD 8.1; App-flow 1, S-12, S-13; schema | No path to create a tenant, location, insurer or pilot; missing fields for refund conditions | Refund conditions not evaluable from stored data | Author | Vendor provisioning endpoints and permission row; Owner manages locations and insurers; `baseline_ros.created_at` and dates; `pilots` baseline and window counts; `preapproved` response status; amounts defined as excluding tax; S-12 roles aligned with schema; IT-20 | Paths and fields named | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-015 | minor | PRD 2, 9; Decision 2, 4 | Launch year, funding and RCW 46.71.045 slightly overstated | Small overstatements | Author | Reworded: launch reported for one vendor by a teaser; no funding claim; 46.71.045 described as about the customer, with the law on insurer requests marked unverified | Wording matches sources | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |
| F-016 | minor | App-flow 4; design 8; TRD 8.2, 11.3 | Session-storage restore; no focus rule after the two critical refusals; 7.2.4, 5.2.6 and PDF rendering unaddressed | Text left in a shared browser; keyboard users lose place | Author | Drafts are saved server-side and nothing typed is kept in browser storage (14.3.1 row); focus rules for the S-06 conflict and the S-08 refusal; threat rows for 7.2.4, 5.2.6 and template rendering; TOTP now mandatory for Estimators, leaving 6.3.3 not met for Office only | Rows and rules present | Closed (independent reviewer retest, 2026-11-11, `supplementpacket-round2.md`; verdict transcribed by the lead) |

Also changed in the same round, from the reviewer's notes outside the numbered findings: M0.3 now runs weeks 4 to 26; refund condition (b) counts packets the vendor drafted late; Repairscope's beta programme is listed; the brief's dropped items are recorded as departures.

### Author self-check log

Author checks are not review findings and do not use `F-` identifiers.

| ID | Check | Result | Action |
|---|---|---|---|
| SC-01 | Links and anchors across the ten files | All relative links and anchors resolve (rerun after fix round 1) | None |
| SC-02 | Identifier definitions | Every referenced `MH`, `T`, `S`, `AD`, `DD`, `UT`, `IT`, `E2E`, `R`, `SRC`, `LQ` identifier is defined | None |
| SC-03 | Must-haves in the matrix | MH-01 to MH-12 each have a row with a screen or API, decision, schema, task and test | None |
| SC-04 | Risk rows | 22 rows, R-01 to R-22, each naming an existing task | None |
| SC-05 | Cross-document agreement | 14 screens in App-flow, design and matrix; every endpoint in TRD 8.1 maps to a must-have; every table used by an endpoint exists in schema.md. Note: `backfill_progress` is described in schema section 9 only, as an operational table | None |
| SC-06 | Arithmetic, original | Unit economics, break-even, binomials, cohort hours and phase totals recomputed by script | First run found the Phase 0 high total written as 321; corrected to 322 (now 337 after round 1) |
| SC-07 | Brief fidelity | Chat figures quoted exactly: 149 / 299 / 599, margin 82%, break-even 6 (37), 250 → 20 → 8 → 2, 20 days, refund under USD 1,000, stop under USD 100 over 10 shops | Departures listed in section 7 |
| SC-08 | Arithmetic, fix round 1 | Base ramp at 75% continuation, downside ramp, 357-shop fallback, break-even 7 and 40, build cost range, refund and gate C illustrations, 12.8 reconciliation, phase totals 275 to 337 and 332 to 488 recomputed by script from the rules printed in Decision 7.4 | Equal to the text |
| SC-09 | Withdrawn claims | Searched the ten files for the allow-list, batch approval, browser session storage and the gross refund wording | Round 1 result was wrong: batch approval remained in T-4.1.3 and R-19, found by the reviewer. Removed on 2026-11-11 and the search rerun: the terms now appear only in prohibitions and in records of their removal |
| SC-10 | Round 2 residues | Links, identifiers and arithmetic rerun after the edits; UT-11 variants recomputed by hand (450000 / 150 = 3000; 700000 / 150 = 4667) | Pass; T-0.2.3 wording aligned with video demos |

## 7. Open items that documents cannot close

| Item | Why it stays open | What closes it |
|---|---|---|
| Whether shops collect incremental cash | No pilot has run | Gate C ([Decision section 9](Decision.md#9-stop-rule)) |
| Whether any shop will pay USD 149 | No conversation has happened | Gate B |
| Supportable missed dollars per closed RO | The only stated rate implies USD 30 per repair | Gate A |
| False-stop probability of gate C, first limb | No variance of shop totals or baselines exists | Pilot data |
| Estimate-data licence position (LQ-01) | CCC pages blocked, Audatex not found, Mitchell product licence not public | Licence text from each shop; counsel |
| OEM citation, link and page rights (LQ-02) | One OEM read; whether a citation is itself disclosure is a legal judgement | Each publisher's terms; counsel |
| Telephone solicitor registration and its fee (LQ-03) | Statute read in an archive capture; the registration itself is an act, not a document | Department of Licensing; counsel |
| Sales tax and nexus (LQ-04), entry for sales visits (LQ-05), privacy law (LQ-06) | Not verified at source | Accountant, counsel |
| Current text of WAC 284-30-390, -320, -380 and all Washington statutes cited | Official host unreachable; some captures predate the 2026 amendment | Reading the live official pages |
| Law on a request to an insurer for work not performed | No source consulted | Counsel |
| Licensed content inside photos or pasted text | Cannot be detected by the planned product | Residual risk; shop's responsibility; takedown |
| Qualified prospect count | Only an industry-code upper bound exists | T-0.1.3 |
| Parser accuracy | No parser exists | WQ-1 on the fixture set |

**Departures from the brief, in one place:** SupplementAI's scope and VaraFix's public price ([Decision section 3](Decision.md#3-competitor-overlap-what-was-read-today)); procedure upload and procedure-based AI drafting not in the MVP (Decision 3.1); email sign-in replaced by password plus TOTP and Google sign-in deferred (TRD AD-11); founder hours 115.3 per cohort instead of 80 per 30 days (Decision 12.4); build 332 to 488 hours instead of 160 (execution plan section 5); stop rule revised and labelled as a change, and the research roadmap's week-1 and week-2 gates kept only as measures (Decision section 9); refund measured on incremental approved dollars at day 60 with collected reported at day 90 (Decision 5.1); a 75% continuation rate added to the model (Decision 6); one closed RO for the free test (chat) rather than two (research); CCC-only parser first; the 14-day trial, 15% annual discount and "launch price 199" not adopted (Decision section 6); the backup channel of estimator Facebook groups and the referral and distributor-partner programme not used (Decision 12.3); phone script without price (Decision 12.5).

## 8. Outstanding items

| Item | Owner | Blocks | Status |
|---|---|---|---|
| FD-01 accept revised gates | Founder | Week 1 | Open |
| FD-02 hosting choice | Founder | Phase 2 | Open |
| FD-03 commit Phases 1 to 3 before a cash reading | Founder | Week 13 | Open |
| LQ-01 estimate sharing and AI under shop licences (T-0.1.2) | Founder, Counsel | Any real estimate; AI-1, AI-2 | Open, unverified |
| LQ-02 OEM citation, link and page rights (T-0.1.2) | Counsel | Citations per publisher | Open, unverified beyond Toyota |
| LQ-03 solicitor registration (T-0.1.1) | Founder, Counsel | First call | Open; default is to register |
| LQ-04 tax (T-0.1.5); LQ-05 border entry (T-0.1.6); LQ-06 privacy (T-0.1.7) | Accountant, Counsel | First invoice; first visit; first real estimate | Open, unverified |
| Counsel, accountant and registration costs | Founder | Cash plan | Missing input, not in the ramp |
| Live official Washington texts | Author or reviewer with access | Confidence in section 2 of Decision | Open; archive captures only |
| F-002 part: gate C first-limb false stop | Founder | Reading gate C | Open until pilot variance data exists |
| F-005 part: LQ-01, LQ-02 licence texts and counsel | Founder, Counsel | Real estimates; citations | Open |
| F-006 part: LQ-03 answer and registration fee | Founder, Counsel | First call | Open |
| F-009 part: counsel, accountant and registration costs | Founder | Cash plan | Missing inputs |
| F-010 part: answers to LQ-01 to LQ-06 | Counsel, Accountant | The steps each task gates | Open |
| F-012 part: live official Washington text | Anyone with access | Section 2 of Decision | Open; host refused again on 2026-11-11 |
| Round 2 residue edits | Lead | Release | Checked by the lead, not re-reviewed |

## 9. Build milestone B1 (2026-11-11)

**Authorisation.** On 2026-11-11 the owner authorised implementation in this repository before the Phase 0 sales gate (G1) passed. The decision text in [Decision.md](Decision.md) is unchanged; the gates in [execution-plan section 1](execution-plan.md#1-sequence-and-gates) still apply to real data, calls, visits and invoices. Everything below uses synthetic data only. Branch `feat/b1-foundation`; not pushed by the developer.

**Tasks implemented (fully or in part).** T-2.1.1 layout, settings, boundary check; T-2.1.2 `make dev` (adapted, no Docker); T-2.1.3 in part (migration-head and parity scripts; no CI workflow); T-2.1.4 logging, correlation, redaction; T-2.2.1 schema with row-level security; T-2.2.4 append-only audit; T-2.2.5 key builder and signed links (no temporary-upload lifecycle rule); T-3.1.1 upload with versions and idempotency; T-3.1.2 job table, worker, sweeper, retry; T-3.1.4 in part (manual entry and totals confirmation through the API; no screens); T-4.1.1 diff engine; T-4.2.1 in part (attestation, reference URL rule, per-file bulk results, RO binding, reset; no re-encoding or metadata removal); T-4.2.2 approval, reset, fingerprints, freeze with snapshot; T-4.2.3 in part (email draft and its amount rule; deterministic stand-in renderer, not the PDF template); T-4.2.4 mark sent, undo, supersede; T-5.1.1 responses, carry-forward, payments, reversal, duplicate warning (no proposed split of an insurer payment); T-5.1.3 baseline, counts, refund test, PM-1, PM-2 (no screens); T-5.1.4 in part (takedown only).

**Blocked or not done, and why.** T-3.1.3 CCC ONE parser and UT-03: needs the hand-transcribed fixture set of T-1.1.2, which waits on G1 and real estimate pairs. T-3.1.5 and UT-15 (AI-1, AI-2): LQ-01 and LQ-02 open, and AI provider access is out of B1 scope. T-2.2.2 password, TOTP, sessions and invites: not done in B1; sessions are created by the seed script and test fixtures, so no login endpoint exists. T-2.2.3 in part: permission table enforced and IT-02 passes, but vendor provisioning endpoints and IT-20 are not built. T-4.1.2 checklist import: the checklist v0 comes from T-0.1.4 (Phase 0); the seed holds a three-item synthetic list. T-5.1.2 tracker, T-5.1.5 shell and every screen, `apps/web`: frontend out of B1 scope. Retention sweep, export and deletion (IT-10, IT-14), backfills and index rehearsal (IT-08, IT-09), restore and recreation (IT-17): not built. Deployment, CI workflow, S3 and MinIO: out of B1 scope.

**Environment.** Python 3.12.16 in `.venv`; PostgreSQL 16.15 local; databases `supplementpacket_dev` and `supplementpacket_test`; application role `supplementpacket_app` (NOSUPERUSER, NOBYPASSRLS, owns no tables); every tenant table FORCE ROW LEVEL SECURITY. Redis database index 2 was assigned but is not used: the TRD's queue is the `jobs` table (AD-03). API port 8103; no frontend, so port 3103 is unused.

**Commands and results (final run, 2026-11-11, test database dropped and re-migrated first).**

| Command | Result |
|---|---|
| `make test` (`scripts/reset_db.sh supplementpacket_test`, then pytest) | 64 passed, 0 failed (24 unit, 40 integration) in 5.9 s |
| `make lint` (ruff check and ruff format --check) | Pass, 0 findings, 57 files formatted |
| `make typecheck` (mypy strict, 46 source files) | Pass, 0 issues |
| `make boundaries` | Pass, 0 violations |
| `make heads` | Pass, 1 head (`20261111_0001`) |
| `make parity` | Pass, 0 differences; row-level security, FORCE and the tenant policy present on all 22 tenant tables; 10 integrity triggers present |
| `make dev` then `make stop` | database, api and worker healthy; ready 0.6 s after start (2 s including migrate and seed). Not measured from a clean clone: the virtual environment already existed |

**Per test ID** (all run by `make test`; files under `tests/`).

| Test | Result | Test file and note |
|---|---|---|
| UT-01 | Pass | `unit/test_core_rules.py`; includes a property round-trip |
| UT-02 | Pass | `unit/test_core_rules.py` |
| UT-03 | Not run | Parser blocked (T-1.1.2) |
| UT-04 | Pass | `unit/test_core_rules.py`: 1.2 h x 5400 = 6480 |
| UT-05 | Pass | `unit/test_core_rules.py`: 60 generated pairs, each diffed 100 times and once shuffled |
| UT-06 | Pass | `unit/test_core_rules.py`: 1 of 30 `needs_review`, 29 compared, totals exclude it; also two candidates are ambiguous |
| UT-07 | Pass | `integration/test_approval_integrity.py`: amount, add photo, delete photo, edit reference, change attestation, correct the shop estimate line, re-run the comparison; each returns the line to draft with `row_version` increased and an audit event; the unrelated approved line is untouched; an unchanged re-run changes nothing |
| UT-08 | Pass | Unit and integration: freeze refused listing both lines |
| UT-09 | Pass | Unit and API |
| UT-10 | Pass | Unit and API (partial reversal of 5000 on a 40000 payment; collected 35000; requested from the live packet only) |
| UT-11 | Pass | `unit/test_ledger_pilot.py`: base case (rate 3000, expected 120000, incremental 60000, (c) 67% not met, no refund); 8 documents (89%) refund due; 24 of 30 complete gives the same result; 20 of 30 complete gives 700000, rate 4667, expected 186667, negative increment flagged in the shop's favour; rows entered after day 7 fail (a) |
| UT-12 | Pass | Not computable naming the missing item; PM-2 still computed; undated row sets the uncensored flag; 60-day cut-off applied |
| UT-13 | Pass | Unit and database |
| UT-14 | Pass | |
| UT-15 | Not run | AI blocked (LQ-01) |
| UT-16 | Pass | Friday to Wednesday = 3 |
| UT-17 | Pass | Unit and API: approved 15000 counted once, carried to packet 2; payment re-attributed with an audit event; a response on the superseded packet is refused |
| UT-18 | Pass | Unit and API |
| UT-19 | Pass | Unit and API: "USD 1,500" refused by name; wording-only edit accepted and changes the fingerprint |
| IT-01 | Pass | `integration/test_tenancy_permissions.py`: all 37 identifier routes of the inventory return 404 for another tenant's IDs; body references return 404; the worker fails A's job naming B's file with `not_found` and writes nothing; the application role reads zero rows from every tenant table with the tenant unset; a cross-tenant insert is refused |
| IT-02 | Pass | Office and Operator: approve, exclude, freeze, mark sent, unmark sent all 403; 10 `permission.denied` audit events; no state change. The database also refuses approval or freezing from the worker, Operator or Office actor role |
| IT-03 | Pass, adapted | One document and one job for repeated uploads; the client abort itself was not simulated (the test client cannot abort mid-request) |
| IT-04 | Pass | Late "running" and duplicate "succeeded" discarded; one set of lines |
| IT-05 | Pass | 7 attached, 2 reported; retry attaches none twice |
| IT-06 | Pass | Sequential and concurrent: the freeze waits on the row lock, then returns 409 naming the line; no packet |
| IT-07 | Pass | Scripts only (no CI workflow): a model-only index and a second head both fail |
| IT-08, IT-09, IT-10 | Not run | Not built |
| IT-11 | Pass | One correlation ID across request, job, crash and retry; no VIN, claim number, adjuster name, file name or amount in the log output |
| IT-12 | Pass, adapted | Link host equals `PUBLIC_BASE_URL` with an internal Host header; no real proxy |
| IT-13 | Pass, adapted | Worker process starts without importing FastAPI, Starlette, uvicorn or the API; not a separate image |
| IT-14, IT-17, IT-20 | Not run | Not built |
| IT-15 | Pass | URL refused for subscription-portal procedures and estimating guides, citation accepted without it; photo batch without the tick refused; a PDF posing as a photo rejected; no procedure, send, transmit or email route in the inventory. Tests the stated controls only |
| IT-16 | Pass | Update, delete and truncate of audit rows refused |
| IT-18 | Pass | Photo replaced by the Operator: 409 listing the line, line back to draft; email paragraph edited: 409 listing `email_draft`; fresh review then freeze succeeds |
| IT-19 | Pass | With the stand-in renderer: PDF and photo objects deleted, snapshot text redacted, amounts, PDF hash and audit rows intact, ledger unchanged; Estimator refused (Owner only) |
| E2E-01 | Pass, API level | Upload, manual lines, diff, manual line with photo, exclusion, approval, freeze, render, mark sent, responses, payment; three totals correct; the stand-in PDF holds only approved lines. No browser |
| E2E-02 | Pass, API level | Unreadable file fails with `unreadable_manual_entry_offered`; manual entry completes the parse |
| E2E-04 | Pass, API level, freeze only | Same key twice gives one packet; a new key with nothing changed gives 409. Mark sent and payment double-submit not tested |
| E2E-06 | Pass, API level | Superseding packet with a withdrawn line; old packet readable; withdrawal shown separately |
| E2E-03, E2E-05, E2E-07, E2E-08 | Not run | No frontend; no imported hand-run ledger |
| E2E-09 | Pass, adapted | See the `make dev` row above |

**Document changes made in B1 (implementation showed a gap).**

- schema.md: fields added and marked *(B1)*: `repair_orders.email_free_paragraph` (the email draft's one free paragraph needed a home before freeze), `documents.content_type`, `supplement_lines.diff_key` (a diff line needs a stable key across document versions so a re-run can tell "changed" from "new"), `photos.content_type` and `row_version`, `reference_citations.created_by` and `created_at`, `line_evidence.ro_id` (the composite key binding evidence to the RO needs the column), `packet_lines.approved_fingerprint` (decides "unchanged" for carry-forward and the duplicate-freeze check), `jobs.max_attempts`, `pilots.row_version`, `operator_grants.created_at`, table `idempotency_records`. The response-document key on `packet_lines` was relaxed to (`tenant_id`, id) with a service check, because a carried-forward response keeps the superseded packet's document. Partial payment reversal and one reversal per payment are stated. The ledger is computed in one Python function, not the proposed SQL view. One application role is used locally instead of the four proposed roles; two SECURITY DEFINER functions claim and sweep jobs.
- TRD.md: endpoints added (`POST /documents/{id}/manual-lines`, `PATCH /photos/{id}`, `GET /packets/{id}/pdf/download`, `GET /ros/{id}/ledger`), pilot routes renamed to `/pilots/{id}/counts` and `/pilots/{id}/report` (a tenant can have one pilot per location), the freeze request carries the review components, job `takedown_purge` added, local start command as built. The traceability row for MH-09 in section 4 was updated to the new routes.
- AGENTS.md: state line, section 4 note, Git hygiene note, utilities and command index (section 11). CLAUDE.md: `make dev` no longer proposed. execution-plan.md: commands that now exist are marked; section 7 now points here for results.

**Rules the documents did not fix, decided in B1 (author proposals, not re-reviewed).**

- Rounding in the refund test: every derived amount is computed as an exact fraction and rounded half away from zero to the cent once, when reported; the expected amount is computed from the exact rate, not the rounded one (UT-11 variant: 186667, not 4667 x 40 = 186680).
- The 60-day and 90-day cut-off for dated baseline rows: a row whose approval (or collection) date is more than 60 (or 90) days after its first request contributes 0 to that measure; the row still counts as complete.
- Day 7 for condition (a) ends at 23:59:59 in the tenant's time zone on the start date plus 6 days. The pilot record has no timestamp for when the two counts were supplied, so (a) checks only that they are present; a field is needed.
- No field records a vendor-late draft for condition (b); the report counts sent packets only. The core function supports the late flag (UT-11) once a field exists.
- Pilot approved dollars count lines whose response date is on or before day 60, and lines with an approval but no response date. Review whether undated responses should count.
- The packet PDF should show the approver's name (MH-07), but `users` has no name column; the stand-in shows the user ID.
- Diff pairing: a shop line pairs with an insurer line of the same operation and the same normalised description or part number; no candidate on a free-text (`other`, no part number) line, or two or more candidates, gives `needs_review`. Insurer-only lines produce nothing. A part-type change produces a `part_type_difference` line even when the price gap is 0.

**Risk register.** Rows R-01, R-02, R-03, R-04, R-05, R-07, R-08, R-10, R-12, R-13, R-16, R-17 and R-19 now cite the B1 test that covers them. No other row changed.

### 9.1 Fix round 1 (2026-11-11)

Independent code review round 1 (`_coordination/review/supplementpacket-b1-round1.md`): 0 blockers, 6 majors, 5 minors. The lead's rulings (2026-11-11) were applied; they are lead rulings, not owner decisions, and the B1-004 baseline rule is pending owner confirmation. Fixes are by the developer; **none is re-reviewed yet**. Each defect has a permanent regression test. Migration `20261111_0002` adds the fields (expand only).

| Finding | Status | Fix | Regression test |
|---|---|---|---|
| B1-001 major | Fixed | The pilot report groups each RO's supersede chain. The chain qualifies when any packet in it was sent in days 1 to 30, and it counts once, under its first in-window packet. Amounts come from the live packet (carried responses, re-pointed payments), limited to lines that were requested in a packet sent in the window | `integration/test_fix_round1.py::test_b1_001_*`: v2 frozen but not sent, and v2 sent on day 41. A stays 20000 and the chain counts once |
| B1-002 major | Fixed | An approval counts in A only with a response date inside days 1 to 60 and a response document uploaded by day 60. Excluded approvals are listed with a reason. A response date in the future is refused, and `response_recorded_at` is stored | `test_b1_002_*` |
| B1-003 major | Fixed | Added `pilots.baseline_counts_supplied_at` (set when both baseline counts are first present), `pilots.vendor_late_draft_count` with recorded time and recorder (Operator only, `PATCH /pilots/{id}/vendor-late-drafts`), and `users.display_name`, which the PDF now shows. A condition with missing inputs is `undetermined`, and so is the refund result, unless another input already makes it definitely not due | `unit/test_ledger_pilot.py::test_b1_003_*`; `integration/test_fix_round1.py::test_b1_003_*` (includes the UT-11 late-draft variant through the API, and the approver name in the PDF) |
| B1-004 major | Fixed; Decision 5.1 and PRD 11 corrected (lead ruling, pending owner confirmation; it removes the effect of the 80% threshold) | Baseline = max(complete rows scaled to S, the highest-row valuation). In the second candidate, each incomplete or missing row is valued at the highest complete row, or at its own supplied amount if that is higher. Both candidates are shown in the flags | `unit/test_ledger_pilot.py::test_b1_004_*` (reviewer cases a02 = 110000 and a03 = 420000). UT-11 and its variants unchanged |
| B1-005 major | Fixed; E2E-06 rewritten | A line in the live packet that the new version no longer requests is copied into the new version as `request_state='withdrawn'`, with its amount, outside the requested total, line count and request. The email says how many lines were withdrawn, and the PDF lists them separately. The ledger shows the withdrawn amount. An insurer response on a withdrawn line is refused | `test_e2e06_b1_005_*` |
| B1-006 major | Fixed | A membership trigger resets every line a user approved when that user's Owner or Estimator role is changed or removed. Freeze also rechecks, under its lock, that each approver is an active Owner or Estimator. If not, it returns 409 and resets those lines in a committed transaction | `test_b1_006_*` (demoted, disabled, removed) |
| B1-007 minor | Fixed | The rate and the expected amount are rounded up. The increment shown is A minus the expected amount shown, which is the exact increment rounded down. A half cent can no longer deny a refund, and the report is consistent | `unit/test_ledger_pilot.py::test_b1_007_*` |
| B1-008 minor | Fixed, with a stated limit | The guard now catches a trailing `$`/`USD` and spelled-out amounts ("fifteen hundred dollars"). **Limit:** a bare number with no symbol and no currency word ("storage 1500") is not detected | `unit/test_core_rules.py::test_b1_008_*` |
| B1-009 minor | Fixed | Money fields accept only a JSON integer or a string of digits. Floats, bools and decimal strings get 422. Hours must be finite with at most 2 decimals. A missing or ill-typed field gets 422, not 500 | `test_b1_009_*` |
| B1-010 minor | Fixed | `sent_on` after today or before the freeze date (tenant time zone) is refused. Payment dates in the future are refused | `test_b1_010_*` |
| B1-011 minor | Fixed in part | Free text is length-capped (for example explanation 2000, email paragraph 1000, description 300). Responses that carry user free text, and the packet review, return the notice not to paste procedure or guide text. **Still open:** photo re-encoding and location-metadata removal (MH-05, T-4.2.1) are not implemented | `test_b1_011_*` |
| IT-03 note | Fixed | The advisory lock is now taken before the existence check. Concurrent uploads of one file under four keys all get the same document | `test_it03_concurrent_uploads_return_one_document` |

**Rules in section 9 superseded by these fixes:**
- Rounding is now shop-favour (B1-007).
- Condition (a) uses the recorded counts time.
- Condition (b) uses the vendor-late record.
- Undated approvals are excluded.
- The approver name is now stored.

**Reviewer scripts re-run after the fixes** (`_coordination/review/supplementpacket-b1-*.py`, unchanged):
- **Now as required:** a02 (110000), a03, a04 (all refused), a05 (sound), a06 (409), a09 (withdrawn 5000), a10 (422), a13 (sound), every input case (422), it03 (one document for both key patterns), worker no-web (passes).
- **Fail in the script, as the rulings require:**
  - a01: the script supplies no counts time, so the result is undetermined. With the inputs recorded it is due; see `test_b1_007`.
  - a07, a08, a12: the script hard-codes September sent dates before the freeze, which B1-010 refuses. a07 and a08 are covered by date-relative regression tests.
  - a11: the 15 kB paste is now refused with 422.

**Final run (2026-11-11, test database dropped and re-migrated first):**

| Check | Result |
|---|---|
| `make test` | 77 passed, 0 failed (28 unit, 49 integration) |
| `make lint` | 0 findings |
| `make typecheck` (mypy strict) | 0 issues in 48 files |
| `make boundaries` | 0 violations |
| `make heads` | 1 head (`20261111_0002`) |
| `make parity` | 0 differences; 11 integrity triggers present |

**Documents changed in this round:**
- Decision 5.1: baseline formula with worked arithmetic, rounding rule, undetermined results, A rule, chain rule.
- PRD section 11.
- execution-plan: UT-11 text, E2E-06.
- App-flow S-09: sent date not before the freeze.
- schema.md: new fields and the trigger.
- TRD 8.1: vendor-late endpoint, freeze recheck.
- AGENTS section 11.
- This section.

### 9.2 Independent retest (round 2, 2026-11-11) and fixes after retest

Reviewer verdicts, copied unchanged from `_coordination/review/supplementpacket-b1-verdicts.json` (review note `supplementpacket-b1-round2.md`; reviewer: 77 passed; 21 of 21 adversarial cases pass after moving a07, a08 and a12 to dates relative to today; no new finding at blocker, major or regression level):

| Finding | Reviewer verdict (round 2) |
|---|---|
| B1-001 | Closed |
| B1-002 | Closed |
| B1-003 | Closed, part open: baseline_counts_supplied_at records only the first time both counts are present; a later change to the counts (S 12 -> 30 after day 7, or S cleared) keeps the early time, so condition (a) reads changed counts as supplied by day 7, and a larger S raises the shop-favour baseline. The vendor-late count is a bare integer only the Operator (vendor) can set, with no per-draft dates the shop can see |
| B1-004 | Closed |
| B1-005 | Closed |
| B1-006 | Closed |
| B1-007 | Closed |
| B1-008 | Closed, part open: a bare number with no symbol or currency word ('storage 1500') is not detected; the limit is stated in verification section 9.1 |
| B1-009 | Closed |
| B1-010 | Closed |
| B1-011 | Closed, part open: photo re-encoding and location-metadata removal (MH-05, T-4.2.1) not implemented; stated in section 9.1 |

**Fixed after retest (lead instructions of 2026-11-11; not re-reviewed):**

| Item | Change |
|---|---|
| B1-003 part, counts | Every change to a pilot count is an append-only row in `pilot_count_events` (migration `20261111_0003`). Condition (a) and the refund baseline use the values in force at the end of day 7. A count supplied or raised after day 7 does not count as supplied by day 7, and clearing a count after day 7 leaves the day-7 value in force. The report shows the full history and flags a later change. A failed participation condition is now a definite "not due" even when the increment is not computable. Regression tests: `unit/test_ledger_pilot.py::test_b1_003_round2_counts_changed_after_day7_use_deadline_value` and `integration/test_fix_round1.py::test_b1_003_round2_counts_raised_after_day7_api` (the reviewer's S 12 → 30 case, plus clearing S) |
| B1-003 part, vendor-late drafts | The bare count is removed. Each late draft is an append-only `vendor_late_drafts` row: draft reference, requested and returned times, note, recorder and recorded time. Only the vendor Operator can create one, and only when the return took more than 1 business day. Every shop role can read them (`GET /pilots/{id}/vendor-late-drafts`, and in the report). Condition (b) stays undetermined until the Operator confirms the record is complete. Regression test: `test_b1_003_refund_undetermined_until_inputs_recorded` (rewritten) |
| B1-004 label | The baseline rule is relabelled in Decision 5.1, PRD 11, execution-plan UT-11 and this section as "lead ruling, pending owner confirmation". The text states that it removes the effect of the 80% threshold. The other rulings, B1-001, B1-002, B1-003 and B1-007, are relabelled from "owner ruling" to "lead ruling" |
| Dates | Every document date of 2026-11-12 is corrected to 2026-11-11. The fix-round-1 migration is renamed `20261111_0002` (revision ID as well; it was never merged or deployed) |

B1-008 (bare numbers) and B1-011 (photo re-encoding and metadata removal) remain part open, as the reviewer recorded.

**Final run (2026-11-11, test database dropped and re-migrated first):**

| Check | Result |
|---|---|
| `make test` | 79 passed, 0 failed (29 unit, 50 integration) |
| `make lint` | 0 findings, 61 files formatted |
| `make typecheck` (mypy strict) | 0 issues in 49 files |
| `make boundaries` | 0 violations |
| `make heads` | 1 head (`20261111_0003`) |
| `make parity` | 0 differences; 13 integrity triggers present; row-level security on all 24 tenant tables |


### 9.3 Independent retest (round 3, 2026-11-11) and fix after retest

Reviewer verdicts, copied unchanged from `_coordination/review/supplementpacket-b1-verdicts.json` (review note `supplementpacket-b1-round3.md`; reviewer: 79 passed; 24 of 24 reviewer scripts pass; no new finding at blocker, major or regression level):

| Finding | Reviewer verdict (round 3) |
|---|---|
| B1-001 | Closed |
| B1-002 | Closed |
| B1-003 | Closed, part open: a vendor-late draft row is free text, not tied to a repair order or packet, so two rows for one repair order (or a row for a repair order whose packet was also sent) count as separate qualifying packets; each raises condition (b) and joins condition (c)'s denominator without a document (8 sent with 7 documents is 87.5% and met; two late rows added by the vendor, even after the record was confirmed complete, make it 70% and not met). PM-1 still uses the current counts, not the day-7 values the refund test uses |
| B1-004 | Closed, part open: the baseline rule is a lead ruling pending owner confirmation, labelled so in Decision 5.1, PRD 11, execution-plan UT-11 and verification 9.1/9.2; the owner has not confirmed it |
| B1-005 | Closed |
| B1-006 | Closed |
| B1-007 | Closed |
| B1-008 | Closed, part open: a bare number with no symbol or currency word ('storage 1500') is not detected; the limit is stated in verification section 9.1 |
| B1-009 | Closed |
| B1-010 | Closed |
| B1-011 | Closed, part open: photo re-encoding and location-metadata removal (MH-05, T-4.2.1) not implemented; stated in section 9.1 |

**Fixed after round-3 retest, lead-checked (lead instructions of 2026-11-11; not re-reviewed):**

| Item | Change |
|---|---|
| B1-003 part, vendor-late drafts tied to a repair order | Each `vendor_late_drafts` row now names its repair order (`ro_id`, required, same location as the pilot) and optionally the packet frozen from the draft (`packet_id`, composite foreign key so it must be on that repair order); unique (`tenant_id`,`pilot_id`,`ro_id`), so a second row for one repair order, in any wording, is refused with 409 (migration `20261111_0004`). Qualifying units are one per repair order (`sp_core.pilot.qualifying_units`): a late draft for a repair order whose packet was sent in the window is listed but not counted again, and is flagged. Condition (b) and condition (c)'s denominator therefore count distinct late repair orders. Another tenant's repair order gives 404; a packet from another repair order gives 422. Regression tests: `unit/test_ledger_pilot.py::test_b1_003_round3_late_drafts_count_once_per_repair_order` and `integration/test_fix_round1.py::test_b1_003_round3_late_draft_counts_once_per_repair_order` (the reviewer's r3 and r5: 8 sent with 7 documents stays 7 of 8, 87.5%, met, after late rows for a sent repair order; reworded repeats give 409; one late repair order with no sent packet joins once, 7 of 9, per UT-11) |
| B1-003 part, PM-1 counts | PM-1 reads R, S and N in force at the end of pilot day 90, its own reading time (gate C is read at day 90), from the count history, as condition (a) reads them at day 7. A change after day 90 (raised, lowered or cleared) does not move PM-1 and is flagged in `pm1_flags`; counts first supplied after day 90 make PM-1 not computable; a correction before day 90 counts. Two count events at the identical instant now resolve in recording order (reviewer note r2). Regression tests: `unit/test_ledger_pilot.py::test_b1_003_round3_pm1_uses_counts_in_force_at_day90`, `::test_b1_003_round3_same_instant_events_resolve_in_recording_order`, and `integration/test_fix_round1.py::test_b1_003_round3_pm1_uses_counts_in_force_at_day90_api` (the reviewer's r4) |

Not changed: a late-draft row added after the vendor confirmed the record complete is still accepted and the confirmation stays (r5); B1-004 (owner confirmation), B1-008 (bare numbers) remain part open as recorded; B1-011 is addressed in B2 (section 10).

**Final run (2026-11-11, test database dropped and re-migrated first):**

| Check | Result |
|---|---|
| `make test` | 84 passed, 0 failed (32 unit, 52 integration) |
| `make lint` | 0 findings, 62 files formatted |
| `make typecheck` (mypy strict) | 0 issues in 50 files |
| `make boundaries` | 0 violations |
| `make heads` | 1 head (`20261111_0004`) |
| `make parity` | 0 differences |

## 10. Build milestone B2 (2026-11-11)

Owner request of 2026-11-11: build what needs no external account. Branch `feat/b2-local-auth`, created from the `feat/b1-foundation` commit that closes the round-3 item (section 9.3). Synthetic data only; no provider account, no deployment.

**Tasks implemented.** T-2.2.2 (password plus TOTP, server sessions, invitations, password reset, lockout) in full for the API; T-2.2.3 in part (Owner invitations and the member list, `GET, POST /users`; vendor provisioning, Operator grants through the API and role changes are not built); T-2.2.5 in part (objects through the S3 API to MinIO, private bucket, authorised download endpoints); T-4.2.1 in part (location metadata removed from JPEG and PNG photos, B1-011). The B1 fake authentication is gone from the application: there is no bearer-token path, and the seed script writes sign-in credentials instead of sessions; only the test fixtures still insert sessions directly.

**What was built** (details in TRD 8.2, 8.4 and 8.6; tables in schema section 3; migration `20261111_0005`):
- Sign-in: `POST /auth/login` (password step) then `POST /auth/totp`; TOTP mandatory for Owner, Estimator and Operator, optional for Office; a new session token on every authentication; `__Host-sp_session` cookie (Secure, HttpOnly, SameSite=Lax, Path=/); 12-hour absolute and 60-minute idle timeout; logout, logout everywhere, `Clear-Site-Data`; disabled users stop at the next request; anti-forgery header on every state-changing request plus an Origin check; roles from the permission table, with `manage_users` added for the Owner.
- Rate limits and lockout as in TRD 8.2 (429 with `Retry-After`); the lockout behaves the same for unknown emails.
- Invitations (72 hours, once) and password reset (30 minutes, once, TOTP still required, every session ended, no sign-in) emailed through SMTP to Mailpit (`sp_api.mailer.SmtpMailer`; a provider later by settings only).
- Files through the S3 API to MinIO (`sp_files.S3ObjectStore`, bucket `supplementpacket-dev`, region `us-east-1`) for the API and the worker; keys keep tenant, repair order and purpose (R-13); no public URL; downloads only through `GET /documents/{id}/content`, `GET /photos/{id}/content` (session, tenant-scoped) or the existing 5-minute signed packet link. Local credentials are in the untracked `.env`; `config/dev.env.example` holds the variable names only.
- Photo metadata: Exif, XMP, IPTC and comments removed from JPEG, and text and Exif chunks from PNG, before hashing and storage (standard library, no re-encoding). HEIC is refused for now.
- B1-011 (minor, author's status, not re-reviewed): location-metadata removal is now done for JPEG and PNG; photo re-encoding and HEIC cleaning remain open.
- `make dev` also reports storage and mail healthy; seeded users sign in through the real path (checked by hand: login, TOTP, session, logout, then 401).

**OWASP ASVS 5.0.0 requirements implemented** (IDs as the TRD cites them from SRC-21 and as read for this milestone; a reviewer should check each against the standard's text): 3.3.1, 3.3.2, 3.3.4 (cookie attributes and prefix); 3.5.1 (anti-forgery); 5.2.1, 5.2.2, 5.3.2 (size caps, type by content, generated keys; from B1, now on S3); 6.2.1, 6.2.5, 6.2.8, 6.2.9 (password length and handling); 6.3.1 (brute force and stuffing); 6.3.3 (MFA, except Office); 6.3.6 (email is not a factor); 6.3.8 (sign-in, lockout and reset answers do not reveal accounts); 6.4.1, 6.4.3 (invitation and reset secrets; reset keeps MFA); 6.5.1, 6.5.5 (TOTP once, defined lifetime); 7.2.1, 7.2.3, 7.2.4 (server-side random session tokens, new on authentication); 7.3.1, 7.3.2 (idle and absolute timeout); 7.4.1, 7.4.2, 7.4.3 (logout, disabled users, all sessions end after a reset); 11.4.2 (scrypt); 14.2.8 (photo metadata, JPEG and PNG); 14.3.1 (server part); 16.3.1 (authentication events logged, identifiers only).

**Not implemented:** 6.2.2 (change password while signed in); 6.2.4 and 6.2.12 (only a short local list of common passwords; the breached-password service needs an outside call); 6.3.3 for the Office role (TOTP optional, as documented); 6.3.5 (notify the user of suspicious sign-ins); recovery when an authenticator is lost (no backup codes; the Owner re-invites); 7.4.5 and 7.5.2 (no endpoint to list or end another user's or one's own other sessions, apart from logout everywhere); 7.5.1 (no re-authentication step, as there is no sensitive-settings endpoint yet); 5.2.6 and photo re-encoding (need an image library); HEIC metadata removal; 5.4.3 (malware scan, accepted gap); 3.4 response headers beyond `nosniff` and `no-store` (no web client and no TLS yet); 12.x (TLS, deployment); 16.3.x authentication events in the tenant audit table (they go to the application log). OIDC and Google sign-in stay deferred (TRD 8.2, AD-11).

**Tests added** (all ran):

| Test | What it shows | Result |
|---|---|---|
| `integration/test_b2_auth.py::test_b2_invite_sign_in_logout_end_to_end` | Owner invites (Estimator cannot, 403); the link is read from Mailpit; TOTP set up and invitation accepted without signing in; password step alone reaches nothing (401); TOTP without the anti-forgery header refused (403); a new token after TOTP; cookie attributes; state change refused without the header and from a foreign Origin (403), accepted with it; logout ends the session server-side, the old cookie gets 401 | Pass |
| `::test_b2_expired_and_reused_invite_and_code_refused` | Used invitation 410; expired invitation 410 with the S-02 message; unknown token 404; the TOTP step used at acceptance refused at sign-in; a code works once across two browsers | Pass |
| `::test_b2_office_without_totp_and_weak_password_refused` | Common and short passwords 422; Office signs in without TOTP; an Estimator invitation without TOTP is refused | Pass |
| `::test_b2_password_reset_needs_totp_ends_sessions_and_link_works_once` | Same answer for unknown and known emails; reset without the code 401; with it, password changed, every session ended, no cookie; link reused 410; old password 401; expired link 410 | Pass |
| `::test_b2_cross_tenant_session_refused` | Signed in to A: B's repair order 404 and the list holds A only; sign-in naming tenant B 401; a session row pointed at B finds no membership (404) | Pass |
| `::test_b2_rate_limit_and_lockout` | 5 failures lock the account (429, "Wait 15 minutes", `Retry-After: 900`) even for the right password; an unknown email locks the same way; sign-in requests per email limited | Pass |
| `::test_b2_idle_and_absolute_expiry_and_disabled_user` | 61 idle minutes, a passed absolute expiry and a disabled user each give 401 | Pass |
| `integration/test_b2_storage.py::test_b2_upload_download_one_tenant_refused_for_another` | Against MinIO: the PDF is in the bucket under `t/{tenant}/ro/{ro}/shop_estimate/{id}/`; downloaded by its tenant, 404 for the other, 403 for an anonymous request to the bucket; a JPEG with a GPS Exif segment is stored and served without it; objects deleted afterwards and the prefix checked empty | Pass |
| `::test_b2_heic_refused_until_metadata_can_be_removed` | HEIC and an unreadable JPEG are refused per file with reasons | Pass |
| `unit/test_b2_credentials_metadata.py` (5 tests) | scrypt hashing and policy; RFC 6238 appendix B vectors, drift, replay; AES-GCM round trip and key separation; JPEG and PNG metadata removal keeping image data byte for byte | Pass |

Existing tests were moved from bearer tokens to the cookie plus anti-forgery header, and the synthetic JPEG fixture is now a structurally valid JPEG; IT-01 covers every new route with an identifier (unknown invitation tokens give 404). Mailpit messages read by the tests are deleted by ID afterwards; MinIO objects under the test tenants' prefixes are deleted and checked.

**Final run (2026-11-11, test database dropped and re-migrated first; Mailpit and MinIO running):**

| Check | Result |
|---|---|
| `make test` | 98 passed, 0 failed, 0 skipped (37 unit, 61 integration) |
| `make lint` | 0 findings, 72 files formatted |
| `make typecheck` (mypy strict) | 0 issues in 56 files |
| `make boundaries` | 0 violations |
| `make heads` | 1 head (`20261111_0005`) |
| `make parity` | 0 differences |
| `make dev`, then `make stop` | database, storage, mail, API and worker healthy; a seeded Estimator signed in with password and TOTP and signed out |

### 10.1 Security fixes after B2 review, awaiting recheck (2026-11-11)

Review note `_coordination/review/supplementpacket-b2-sec-round1.md` (independent reviewer; 25 attack cases in `supplementpacket-b2-sec_attack.py`: 13 passed, 12 failed against `f5a3b45`). Fixed per the lead's rulings; not yet re-reviewed. Each failing case is kept as a permanent regression test in `tests/integration/test_b2_security.py` (and unit tests in `tests/unit/test_b2_credentials_photos.py`).

| Finding | Fix | Regression tests |
|---|---|---|
| B2-S01 major, photo metadata bypass | The segment stripper (`sp_files.metadata`) is removed. Each JPEG or PNG is decoded to pixels with Pillow and re-encoded (`sp_files.photos.reencode_photo`): full decode or refusal; 40-megapixel limit from the header; primary image only (Multi-Picture secondary images dropped); orientation applied first; long edge at most 2,000 pixels; new baseline JPEG or plain PNG with no Exif, XMP, ICC, comment, text or private chunk; output re-read and checked. Only the re-encoded file is stored. The upload result reports `metadata: "none: re-encoded from pixels"`; `metadata_blocks_removed` is gone | `test_b2_s01_crafted_photo_never_stored_with_gps` (the reviewer's six files verbatim, plus two real photos with Exif, trailer and MPF; asserts no GPS bytes in any stored object); unit `test_b2_s01_reencode_removes_every_metadata_shape` (11 shapes on real images: Exif, APP1 between progressive scans, a real MPO whose second image has GPS, hand-made MPF trailer, trailer after EOI, XMP and comment, ICC with GPS, PNG `exIf`, `zxIf`, `caBX`, `tEXt` and `eXIf`), `test_b2_s01_orientation_applied_and_size_limits`, `test_b2_s01_anything_that_does_not_decode_is_refused` |
| B2-S02 major, reset confirm ignored the lock | Reset confirm reserves a failure slot on the account's lock before checking the code, under the same advisory lock as sign-in; refused with 429 while locked even with the correct code; a wrong code counts toward the lock | `test_b2_s02_reset_confirm_refused_while_locked_even_with_the_right_code` (reviewer A06), `test_b2_s02_reset_confirm_failures_count_toward_the_lock` |
| B2-S03 major, invitation token in the access log | Invitation and reset tokens travel only in JSON bodies (`POST /invites/lookup`, `/invites/totp-setup`, `/invites/accept`, `/auth/password-reset/confirm`); emailed links carry the token in the URL fragment (`/invite#token=…`, `/reset#token=…`), which browsers never send. `sp_obs.AccessLogFilter` on `uvicorn.access` drops query strings (signed-link signatures) and redacts token-like path segments | `test_b2_s03_tokens_never_reach_the_access_log` (real uvicorn with its access log on; invitation, acceptance, reset request and confirm, a token-shaped path and a `sig` query string; greps the captured log), `test_b2_s03_no_route_takes_a_token_in_its_path` |
| B2-S04 minor, reset-request timing | The reset email is sent in the background and every reset request is padded to a 250 ms floor | `test_b2_s04_reset_request_takes_the_same_time_known_or_unknown` |
| B2-S05 minor, lock race | Every count-and-record (rate limits and failure slots) runs under `pg_advisory_xact_lock` per bucket and key; a failure slot is reserved before the check and released only on success | `test_b2_s05_parallel_password_guesses_evaluate_at_most_five` (40 parallel, reviewer A05), `test_b2_s05_parallel_code_guesses_evaluate_at_most_five` (30 parallel, A05b) |
| B2-S06 minor, claimed IDs without tests | Tests added for each: 5.2.1 caps, 6.2.8 exact verification, 6.2.9 64 to 256 characters, 7.2.3 token entropy, 7.2.4 revocation of a session already in the browser, 7.4.3 logout everywhere, 16.3.1 authentication events logged without email or secret. No claim withdrawn | `test_b2_s06_upload_size_caps`, unit `test_b2_s06_password_length_and_exactness`, unit `test_b2_s06_token_entropy`, `test_b2_s06_login_revokes_a_session_already_in_the_browser`, `test_b2_s06_logout_all_ends_every_session`, `test_b2_s06_authentication_events_are_logged_without_secrets` |
| B2-S07 minor, shop list before TOTP | The password step returns only `next` and the anti-forgery token; a person with several shops chooses one through `POST /auth/tenant` with a 5-minute `choose_tenant` session after every factor (migration `20261111_0006`) | `test_b2_s07_shop_choice_only_after_every_factor` (reviewer A17) |

ASVS IDs now also implemented: 5.2.6 (40-megapixel limit) and 14.2.1 and 16.2.5 for sign-in tokens and the access log. HEIC stays refused. Pillow 13.0.0 is added to `tools/requirements.txt`. A test that compared TOTP steps by wall-clock offset was made robust to the 30-second boundary (it now reads the step consumed at acceptance).

**Attack script after the fixes** (fresh test database): 24 passed, 1 failed. The failure is A07: the script reads the token from an emailed `/invite/<token>` link and calls `GET /invites/<token>`. Both changed under the B2-S03 ruling (fragment link, token in the body), so the script needs updating; the repository's A07 equivalent passes.

**Final run (2026-11-11, test database dropped and re-migrated first; Mailpit and MinIO running):**

| Check | Result |
|---|---|
| `make test` | 131 passed, 0 failed, 0 skipped (50 unit, 81 integration) |
| `make lint` | 0 findings, 74 files formatted |
| `make typecheck` (mypy strict) | 0 issues in 57 files |
| `make boundaries` | 0 violations |
| `make heads` | 1 head (`20261111_0006`) |
| `make parity` | 0 differences |
