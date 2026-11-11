# Decision — SupplementPacket

**Question this repository exists to answer:** does a Washington collision shop collect incremental cash after estimator review? Requested, insurer-approved and collected amounts are tracked separately per repair order (RO), against a baseline of what the shop already recovers on its own supplements. Competitor overlap and rights to supporting repair material are addressed, not assumed away.

Status: planning only. No customer has been interviewed, no message has been sent, no application exists. Willingness to pay is unproven.

## 0. How numbers are labelled

| Label | Meaning |
|---|---|
| **[C]** | Stated in the earlier chat or its research record (the decision brief). Model inputs in the brief are assumptions even when labelled [C]; the label records where the number came from. |
| **[S: SRC-nn]** | Read by the author on 2026-11-10 at the live source listed in [section 13](#13-sources-and-assumptions). |
| **[S-arch: SRC-nn]** | Read on 2026-11-10 in an Internet Archive capture of the official page because the official host refused connections. The capture date is in section 13. The text in force today is not confirmed. |
| **[A]** | Assumption. Never a finding. |
| **[P]** | Proposal by the author for something the chat did not decide. |

Results computed from assumptions are assumptions. Currency is USD unless a line says CAD. Conversions are CAD to USD at the scenario rate 1 USD = 1.38 CAD **[C]** (a scenario assumption, not a sourced rate). For comparison the Bank of Canada daily rate on 2026-11-09 was 1.4123 **[S: SRC-18]**. Money is rounded to cents in unit figures and to whole dollars in the ramp.

## 1. Proposed decision

**Sell and hand-run before building. Build only through the gates in [section 9](#9-stop-rule).** **[P]**

The product compares the shop's repair plan with the insurer's estimate, lets the estimator confirm an omitted-operations checklist, attaches the shop's photos and reference citations, and produces a supplement request packet (PDF plus an email draft). The estimator approves every line and sees the packet in its final form before it is frozen. The product never sends anything to an insurer; the shop sends from its own mailbox or portal and records that it did. It then tracks three amounts per RO: requested, insurer-approved, collected.

| Item | Decision | Label |
|---|---|---|
| Launch market | Independent collision shops in Washington State, sold remotely from Vancouver with drive-in visits; Oregon second | [C] |
| Daily user | Lead estimator | [C] |
| Buyer, budget owner, signer | Shop owner or general manager | [C] |
| Current workaround | Estimator compares the two estimates line by line, looks up procedures, emails photos and notes to the adjuster; some shops pay outside supplement services a percentage | [C] |
| Offer | Free test on one closed RO, then a 30-day paid pilot | [C] |
| Pilot price | USD 149. Refunded if insurer-approved dollars above the shop's own baseline are under USD 1,000 at day 60 and the shop met three participation conditions ([5.1](#51-refund-criterion)) | [C] price and threshold; [P] definition |
| Tier prices | USD 149 / 299 / 599 per month | [C] |
| Channel | Phone and in-person visits; association meetings as backup | [C] |
| Prospect source | SCRS affiliate associations, I-CAR Gold Class locator, Google Maps listings | [C] |
| Sample inputs | Insurer estimate PDF and shop repair-plan PDF for the same RO (CCC ONE first), the shop's own photos | [C], CCC-first is [P] |
| Sales cycle | 21 days from first touch to paid pilot | [C] |
| Stop rule | Quoted and tested in [section 9](#9-stop-rule) | [C] then [P] |

## 2. Market, people and current practice

- **Why Washington, not BC** [C]: ICBC's policy requires justification for an estimate review request and says excessive requests can lower quality scores (research record, 2025-05, not reopened today). Washington has competing private insurers and is the nearest US market.
- **Rule context.** WAC 284-30-330(4), as amended effective 2026-10-18 (WSR 26-17-089), says a reasonable investigation "may not rely solely on the use of a database", including estimating software; WAC 284-30-360(3) requires a reply to a claimant's pertinent communication within 10 business days; WAC 284-30-370 requires investigation within 30 calendar days [S-arch: SRC-04; all three captures show the amended text]. WAC 284-30-390 makes it an unfair practice for an insurer to fail "to consider any additional loss related damage the repair facility discovers during the repairs" (subsection 6) and requires it to disclose its reasons when it pays less than the chosen facility's estimate (2)(b), (4)(b); WAC 284-30-320(2) defines "claimant" as a first-party or third-party claimant or designated representative [S-arch: SRC-04; **pre-amendment captures, current text unverified**: the available captures of -390 and -320 predate the 2026-08-18 filing of WSR 26-17-089].
- **Edge that binds the product:** these duties are owed to the claimant. A repair shop is not named as a claimant in the text read. The product therefore never tells a shop it holds these rights, never labels insurer conduct a violation, and treats the 10 business days as a follow-up reminder default, not a legal deadline.
- **Shop-side rule** [S-arch: SRC-05]: under RCW 46.71.025(2) a shop may not charge the customer more than 110% of the written estimate without authorization, so a denied supplement cannot simply be billed to the vehicle owner. RCW 46.71.045(3) and (7) make it unlawful to retain a customer's payment for work not performed or to charge a customer for unnecessary repairs. Those provisions speak of the customer; what law applies to a request made to an insurer for work not performed was **not read (unverified, no source consulted)**. It is treated as the product's worst outcome regardless ([PRD section 9](PRD.md#9-highest-cost-user-mistake)).
- **Industry size signal** [S-arch: SRC-17]: preliminary 2025 average total cost of repair USD 4,818; direct repair programs 46.7% of appraisals. A second figure in the brief (56.5% of DRP calibrations on a supplement) was not opened and stays secondary.

## 3. Competitor overlap: what was read today

All prices are list prices in USD, per month, per shop location, billed monthly, read on each vendor's own page on 2026-11-10.

| Vendor | Price | Input | What it advertises | Tracking advertised | Refund or guarantee | Source |
|---|---|---|---|---|---|---|
| SupplementAI | Starter 99; Pro 199; 14-day trial | Starter: typed disputed items. Pro: uploads CCC, Mitchell, Audatex PDFs and extracts the disputed line items automatically | Supplement letter with generated citations in 30 seconds | Pro: a supplement history and tracking feature (scope not stated) | First month refunded if dissatisfied within 14 days | SRC-01 |
| VaraFix | 349; free trial of 3 reviews | The shop's own CCC ONE estimate PDF; Mitchell listed as planned | Finds left-off operations and supplies a source, an explanation and a line note for each | Dashboards of money found and money added back to the estimate (not approved or collected) | Terms disclaim any guarantee of payment; all fees non-refundable | SRC-03 |
| Repairscope | 399 founding, 599 at public launch; 7-day trial; a one-month-free beta programme | Insurer estimate only (PDF or photo); no photos needed | 50+ commonly missed operations in 15 categories with approval-likelihood bands | None stated | None stated | SRC-02 |
| SupplementPacket | 149 / 299 / 599 [C] | Both estimates plus shop photos | Line diff, checklist, evidence per line, estimator-approved packet | Requested, approved, collected per RO | Pilot refund under USD 1,000 above baseline | this document |
| CCC ONE, Mitchell, Audatex | Not public | Systems of record | Adding AI; serve insurers and shops | n/a | n/a | not opened (CCC pages returned HTTP 403) |

**Honest overlap.** Finding missed operations is offered by Repairscope and VaraFix. Reading estimate PDFs and writing the request is offered by SupplementAI Pro. Some form of tracking is offered by SupplementAI Pro and VaraFix. What none of the three pages advertises: a line-by-line comparison of the shop plan against the insurer estimate with a per-line photo, a record of insurer-approved and collected dollars backed by the insurer's documents, or a refund tied to dollars above baseline. That gap is narrow, is inferred from marketing pages (absence from a page is not absence from a product), and can be copied in weeks.

**Departures from the brief, recorded.**
1. The brief calls SupplementAI a letter generator where the "user enters disputed items". True for Starter only; Pro uploads PDFs, extracts line items and has tracking. The gap is narrower than the brief states.
2. The brief lists VaraFix pricing as not public and seen only in search results. Its site was opened today: USD 349 per month, CCC ONE only.
3. Repairscope matches the brief. Its page is also served at `repairscope.co`.
4. SupplementAI's contact address uses `supplementai.com`; that domain showed a domain-for-sale listing today [S: SRC-01]. Traction is unknown; the page says its testimonial names were changed for privacy.

**Vendor claims are not outcomes.** An average of USD 680 recovered per supplement (SupplementAI), USD 300 to 600 per repair (Repairscope), USD 274 found per RO after halving its own six-estimate result and about 83% of findings that interviewed adjusters said they would approve (VaraFix) are advertised, unsourced, and measure dollars found or predicted. None reports collected cash against a baseline. No measured customer outcome was found for any vendor.

**Price position.** Starter 149 sits between SupplementAI's 99 and 199; Pro 299 sits below VaraFix 349 and Repairscope 399; Business 599 equals Repairscope's announced launch price. The brief's rationale ("between a letter writer and a full estimate reviewer") holds for Starter and Pro only.

### 3.1 Rights to supporting repair material

Not legal advice. Each row says what the product may do by default. "Unverified" means the governing licence text was not read.

| Material | Default treatment in the product | Basis and status |
|---|---|---|
| OEM repair procedures from subscription portals | **Reference only, without a link**: publisher, document title, document or section identifier, date accessed. No page upload path exists in the MVP. No stored text, no quotation, no URL, no text sent to an AI provider | Toyota TIS Terms of Use read today: the terms treat site content as confidential, bar disclosing it to any person or entity without Toyota's written approval, bar data mining, and bar linking or deep-linking to, or otherwise reproducing, any part of the site without prior written consent [S: SRC-10, paraphrased]. **Whether even a title-and-section citation counts as disclosing that content is unverified (LQ-02).** Applicability to an independent shop's subscription tier and all other OEMs' terms: unverified |
| OEM position statements published openly | **Link and reference**: title, publisher, date, URL of the publisher's own public page. No stored copy | OEM1Stop's terms forbid reproducing, transferring, distributing or storing its content without prior written permission [S: SRC-11, paraphrased]. Each OEM's own terms for its statements: unverified |
| Estimating-system data: labour times, part prices, P-pages, CCC, Mitchell and Audatex guides; this includes **both** the shop's exported estimate and the insurer's estimate PDF | The product reads the two estimate PDFs to compute differences **for that shop only**. It never pools line data across shops, never builds a labour-time or price database, never reproduces guide text. Guide sections are referenced by name | CCC licence and Secure Share permitted-use pages returned HTTP 403; a search snippet reports a ban on constructing a collision estimating database by compilation (secondary) [SRC-13]. Enlyte's site terms forbid scraping and AI training on its sites but are not the Mitchell product licence [S: SRC-12]. Audatex terms not found [SRC-14]. Whether a shop may give either PDF to a third-party tool: **unverified for all three**; legal question LQ-01, which blocks receipt of any real estimate |
| Photos | Only photos the shop took of the vehicle in its care. Location metadata is stripped. Every upload batch needs a positive attestation (no default) that the files are the shop's own photos of this vehicle and not screenshots or copies of procedures, guides or other licensed documents | Ownership by the shop is [A]; no licence read |
| I-CAR, SCRS and DEG material | Link and reference only | Terms not read: unverified |
| Omitted-operations checklist | Written by the founder from pilot shops' own denial lists. Operation names only; no labour times, no guide text | [P] |

**Residual risk, stated plainly.** The product cannot detect a screenshot of a procedure uploaded as a photo, or procedure text pasted into an explanation or the email draft. The controls are the attestation above, a notice on every free-text field, the estimator's approval of the final packet, audit of who uploaded what, and a takedown procedure that purges a frozen packet's file and evidence ([schema section 8](schema.md#8-sensitivity-and-retention)). None of these prevents a determined or careless user; the shop's subscription is what is at risk. The earlier wording that a licensed-content guard refuses such uploads is withdrawn.

**Departure from the brief.** The brief's MVP lets the estimator "paste or upload the relevant OEM procedure page" and has a model draft wording "from the supplied procedure text". The Toyota terms read today forbid disclosure on their face, so neither is in the MVP. The packet still tells the adjuster which document and section to open.

## 4. Strongest evidence and strongest counterargument

- **Strongest evidence:** three vendors publicly charge USD 99 to 399 per month for part of this job [S: SRC-01, SRC-02, SRC-03], and Washington rules as captured oblige insurers to consider damage found during repairs and to explain underpayment [S-arch: SRC-04]. This shows shops are being asked to pay. It does not show they pay or that cash arrives.
- **Strongest counterargument:** approval and payment are the insurer's decisions. The only recovery figure in the brief is a model (one extra approved USD 150 operation on 20% of repairs [C], which is USD 30 per repair). Under that figure the chat's own stop rule fires almost certainly, and a 34-repair shop earns its refund almost half the time ([section 9](#9-stop-rule), [5.1](#51-refund-criterion)). Three entrants are already in market (two of them on development-host pages, funding unknown), and the estimating-system vendors can add this. The rights position on estimate data is unverified.

## 5. Offer, channel and pilot

| Step | What happens | Who | Software needed |
|---|---|---|---|
| Free test | Shop supplies one closed RO: insurer's final estimate PDF and the shop's final repair plan or invoice PDF. Founder returns a difference list and a sample packet within 2 business days | Estimator supplies; founder hand-runs | None (spreadsheet and document template) |
| Pilot agreement | One page: price, window, data supplied, refund test and its conditions including the treatment of incomplete baseline rows, cancellation right, confidentiality, data handling, no contact with insurers by the founder | Owner signs | None |
| Payment | USD 149 before day 1, by card payment link, bank transfer or cheque at the shop's choice | Shop pays | Payment provider only |
| Baseline | Shop supplies, for the three calendar months before the pilot: the count of insurer-paid ROs closed, the count of those that had a supplement, and for each supplemented RO the supplement requested, approved and collected (at least 10 complete rows) | Estimator or office manager | Spreadsheet |
| Pilot delivery, days 1 to 30 | For each live RO the estimator supplies the two PDFs and photos; the founder returns a draft packet, watermarked as a draft, within 1 business day; the estimator approves or strikes every line on an approval sheet that lists each line's evidence files, and sends the packet personally. Any change after the sheet is signed needs a new sheet | Estimator; founder | Hand-run until release, then the application |
| Measurement | Approved dollars at day 60, collected at day 90, from insurer response documents and remittances | Estimator and office supply documents; founder computes | Spreadsheet ledger, later [MH-08](PRD.md#6-must-haves) |

**How a paid pilot is delivered before software exists:** entirely by hand as above. Hand-run capacity is 4 shops at once [A] (15 founder hours per shop per 30 days: 12 packets at 1 hour plus 3 hours of calls and ledger). The founder works from Vancouver; no pilot work is performed inside the United States. **Hand-run data handling [P]:** files move only through a per-shop access-controlled folder in a US storage region, never as email attachments; only the founder has access; vehicle-owner names, addresses and policy numbers are not copied into any sheet; files are deleted 90 days after the pilot ends. No real estimate is received before [T-0.1.2](execution-plan.md#milestone-m01--legal-gate-list-and-hand-test-kit) and T-0.1.7 are closed for that shop.

### 5.1 Refund criterion

Chat term: refund if under USD 1,000 is recovered [C]. Research wording: "refunded if approved supplement dollars attributed to the tool are under USD 1,000" [C]. Dollars a shop would have been approved anyway are not attributable to the tool, so the test is **incremental over the shop's baseline**, not gross. Definition proposed **[P]**:

- **Qualifying packet:** produced through SupplementPacket, every line approved by the shop's estimator, marked sent by the shop within the 30-day window. The agreement requires every supplement request the shop sends in the window to go through the service.
- **Pilot approved dollars, A:** for qualifying packets, the sum of line amounts the insurer approved in writing above the insurer estimate version in force when the packet was sent, as shown on the insurer's revised estimate, supplement of record or written approval; an approval counts only with a response date inside days 1 to 60 and the insurer's response document, and undated or undocumented approvals are excluded and listed (lead ruling B1-002, 2026-11-11). A packet sent in the window keeps counting after a correction supersedes it: its approved and collected amounts follow the supersede chain exactly once (lead ruling B1-001, 2026-11-11). Amounts exclude sales tax; lines the insurer had already approved before sending are flagged and excluded; a superseded packet's lines are not counted twice. Measured at 23:59 Pacific on day 60.
- **Baseline rate, b:** approved supplement dollars on ROs closed in the three calendar months before the pilot, divided by the number of insurer-paid ROs closed in those months (all of them, including ROs with no supplement). **Lead ruling (B1-004, 2026-11-11), pending owner confirmation:** incomplete rows never lower the baseline, and every treatment of them resolves in the shop's favour. This rule removes the effect of the 80% threshold the earlier text used: the result no longer depends on whether C is at least 80% of S, because candidate (ii) below is never lower than candidate (i). With S the declared number of supplemented ROs among them, C the complete rows (all three amounts present) and H the highest complete row, the baseline total is the higher of two candidates: (i) S × the mean of the complete rows; (ii) the highest-row valuation, the sum of the complete rows plus each incomplete row valued at H or at its own supplied amount for that measure if higher, plus each declared row not entered valued at H. Because H is never below the mean, (ii) is never below (i), and it is never below the sum of the amounts supplied. The report shows both candidates and says the result favours the shop. *Arithmetic:* 30 declared, 24 complete at 15,000, 6 incomplete with nothing supplied: (i) 30 × 15,000 = 450,000; (ii) 360,000 + 6 × 15,000 = 450,000; baseline 450,000. 12 declared, 10 complete at 1,000, 2 rows with approved 50,000 and collected unknown: (i) 12 × 1,000 = 12,000; (ii) 10,000 + 2 × 50,000 = 110,000; baseline 110,000 (the earlier 80% rule gave 12,000, which let incomplete rows lower the baseline). 30 declared, 20 complete totalling 300,000 with H = 40,000, 10 with nothing supplied: (i) 450,000; (ii) 300,000 + 10 × 40,000 = 700,000; baseline 700,000.
- **Rounding:** derived amounts resolve in the shop's favour: b and b × N are rounded up to the cent, and the increment shown is A minus the rounded b × N (the exact increment rounded down), so a half cent never decides against the shop (lead ruling B1-007, 2026-11-11).
- **Undetermined:** when an input a condition needs is not recorded (when the baseline counts were supplied; the drafts the vendor returned late), that condition and the refund result are "undetermined", never a definite answer; a count supplied or raised after day 7 does not count as supplied by day 7, and condition (a) and the refund baseline use the counts in force at the end of day 7 (the full history of changes is kept; vendor-late drafts are recorded one by one with their reference, request and return times and recorder, and the shop can see them) (lead ruling B1-003, 2026-11-11).
- **Incremental approved dollars = A − b × N**, where N is the number of insurer-paid ROs the shop closed in the 30-day window (a throughput proxy, from the shop's management system).
- **Cut-off rule:** baseline rows that carry dates are cut at the same 60 days (approved) and 90 days (collected) from first request; rows without dates count in full and the report says so. That bias runs against the vendor.
- **Refund is paid** within 10 business days, by the method the shop paid with, when incremental approved dollars are under USD 1,000.00 **and** the shop met three participation conditions: (a) the two baseline counts and at least 10 complete supplemented baseline rows supplied by day 7; (b) at least 8 qualifying packets, counting any packet whose draft the vendor returned later than 1 business day; (c) the insurer's response document supplied for at least 80% of qualifying packets by day 60.
- **Why the buyer cannot void it unilaterally:** not using the service fails (b); withholding approvals fails (c); the amounts come from insurer documents and a system count. Known limit: a shop can lower A by sending supplements outside the service; the vendor's exposure is the USD 149 fee.
- A shop that fails a condition keeps the right to cancel but not the refund. Collected cash at day 90 is reported to the shop and drives the founder's decision ([section 9](#9-stop-rule)); it does not change the refund.

**What the threshold implies.** The brief's modelled incremental rate is one extra approved USD 150 operation on 20% of repairs [C], USD 30 per insurer-paid repair. Reaching USD 1,000 therefore needs 1,000 / (0.20 × 150) = **33.3 insurer-paid repairs in the window**. A 40-repair shop is modelled at 40 × 0.20 × 150 = USD 1,200 and a 60-repair shop at USD 1,800. Illustration [A], treating each repair as USD 150 with probability 0.20 and ignoring baseline noise: the shop reaches USD 1,000 when at least 7 repairs succeed, which happens 53.4% of the time at 34 repairs, 71.4% at 40 and 96.9% at 60. Even if the modelled rate is true, a refund is owed to 46.6%, 28.6% and 3.1% of such shops.

## 6. One paying account, one billable unit

- **One paying account:** one shop location (one physical repair facility) with a paid invoice covering the current month. The USD 149 pilot month counts.
- **One billable unit:** one location-month of subscription. Packets are not billed in the MVP [C]; tier caps are fair-use limits.
- A **packet** is one supplement request version for one RO.
- **Continuation rate:** the share of paid pilots that continue into month 2 by the written opt-in in [12.6](#126-pilot-offer-and-the-step-to-a-recurring-account). Base case **75% [A]**: it is the product's own target of 3 of 4 ([PRD CM-2](PRD.md#11-success-metrics)); no evidence supports it. This one rate is used in sections 7, 8 and 12.

| Tier | Price per location-month [C] | Scope [P] | Assumed packets per month [A] | Assumed share of accounts |
|---|---|---|---|---|
| Starter | 149 | 2 users, up to 60 packets | 40 | 2/3 |
| Pro | 299 | 5 users, up to 150 packets, insurer tracker export | 100 | 1/3 |
| Business | 599 | Up to 3 locations, 450 packets pooled | not modelled | 0 |

**Reconciliation.** The model's revenue per account is USD 199 [C]; no tier costs 199. The mix that yields it: (2/3 × 149) + (1/3 × 299) = 99.33 + 99.67 = **199.00**. Packets: (2/3 × 40) + (1/3 × 100) = **60 per month**, the brief's cost-note volume [C]. The pilot price equals the Starter price, so the pilot is the first Starter month with a refund test. The brief's "launch price 199", "14-day free trial on live repair orders" and 15% annual discount are not adopted: the chat's offer is the free closed-RO test then the USD 149 pilot, and billing is monthly only [P].

## 7. Unit economics

One currency (USD), one period (month), one unit (paying account).

### 7.1 Cost categories

| Category | Amount | Label |
|---|---|---|
| Startup cost: build, chat figure | 160 hours at CAD 100 per hour = CAD 16,000 = 16,000 / 1.38 = USD 11,594.20 | [C] |
| Startup cost: build, author's task sum | 332 to 488 hours ([execution-plan section 5](execution-plan.md#5-estimate-summary)) at the same CAD 100 = CAD 33,200 to 48,800 = **USD 24,057.97 to 35,362.32**; midpoint 410 hours = USD 29,710.14 | [P] hours, [C] rate |
| Startup cost: counsel, accountant, Washington telephone-solicitor registration fee | **Missing inputs.** Not in any figure below; each USD 1,000 lowers every cumulative figure by 1,000 | none |
| Monthly fixed cost excluding founder | 800 | [C] |
| Founder compensation | CAD 6,000 / 1.38 = USD 4,347.83 per month (at 1.4123: 4,248.39) | [C] with stated rate |
| Variable cost per account-month | 35.57 (below) | [C] |
| Initial acquisition cost (CAC) | 600 per converted paying account | [C]; bottom-up in [7.3](#73-cac-one-definition) |
| Churn-replacement cost | 0.04 × 600 = 24.00 per account-month (chat formula); 0.04 × 800 = 32.00 when a replacement must also survive the pilot month | derived |

Variable cost: AI 8.00 (60 packets × USD 0.12 = 7.20, rounded up in the model) + hosting 3.00 + storage 3.00 + messaging 0.50 + support 15.00 (20 minutes at USD 45 per hour) + payment (2.9% × 199) + 0.30 = 6.07 [S: SRC-19 for the rate] = **35.57**.

### 7.2 Base and downside cases

| Line | Base | Downside | Arithmetic (base; downside) |
|---|---|---|---|
| Revenue per account-month | 199.00 [C] | 149.00 [A] all Starter | |
| Variable cost | 35.57 | 41.62 | downside: support 30 minutes = 22.50; payment 0.029 × 149 + 0.30 = 4.62 |
| Gross profit | 163.43 | 107.38 | 199 − 35.57; 149 − 41.62 |
| Gross margin | 82.1% | 72.1% | |
| Close rate, demo to paid pilot | 25% [C] | 12.5% [A] | |
| Paid pilots per 250 shops | 2 | 1 | 250 × 0.08 × 0.40 × rate |
| CAC per converted paying account | 600 | 1,200 | 1,200 cohort cash / pilots |
| Continuation into month 2 | 75% [A] | 50% [A], and those pilots are refunded in full | section 6 |
| Continuing accounts per 250 shops | 1.5 | 0.5 | pilots × continuation |
| Acquisition cash per continuing account | 800 | 2,400 | CAC / continuation |
| Monthly churn after month 2 | 4% [C] | 8% [A] | |
| Payback on CAC | 3.67 months | 11.18 months | CAC / gross profit |
| Payback per continuing account | 4.90 months | 22.35 months | 800 / 163.43; 2,400 / 107.38 |
| Lifetime value of a continuing account | 4,085.75 | 1,342.25 | gross profit / churn |
| Break-even accounts, no acquisition, without founder | 5 | 8 | ceil(800 / gross profit) |
| Same, with founder | 32 | 48 | ceil(5,147.83 / gross profit) |
| Break-even with churn replacement, chat formula, without founder | **6** | 71 | ceil(800 / (163.43 − 24.00) = 5.74); ceil(800 / (107.38 − 96.00) = 70.30) |
| Same, with founder | **37** | 453 | ceil(5,147.83 / 139.43 = 36.92); ceil(5,147.83 / 11.38 = 452.36) |
| Break-even with churn replacement at the continuation rate, without founder | 7 | none | ceil(800 / (163.43 − 32.00) = 6.09); downside margin 107.38 − 0.08 × 2,400 = −84.62 is negative |
| Same, with founder | 40 | none | ceil(5,147.83 / 131.43 = 39.17) |

The rows marked "chat formula" reproduce the chat: margin 82%, break-even 6 (37) [C]. The chat's formula does not model pilots that stop after one month; the two rows below it do, and are the ones the ramp uses.

### 7.3 CAC: one definition

CAC is **cash acquisition spend per converted paying account**, where conversion is the first paid pilot invoice. Founder time is excluded from CAC and reported in hours; its cost sits in the with-founder lines. Bottom-up per 250-shop cohort: list 250 (USD 100 per 100 prospects [C]) + travel 400 [C] + phone and data 150 [C] + association meeting 200 [C] + contingency 200 [A] = **1,200**; divided by 2 paid pilots = **600**, the model figure [C]. The brief's hosting and AI line (150) is inside the 800 fixed cost, not CAC. Everywhere in this repository acquisition spend is booked at USD 600 in the month a pilot is paid. Cash actually leaves earlier (the list and travel come first): by up to USD 720 in month 1, nothing by the end of month 3.

### 7.4 Cash required during the acquisition ramp

**Rules, exactly.** Month 1 is the first month of outreach; months are 4, 4 and 5 week blocks. Outreach is 50 new shops per week ([12.4](#124-channel-sequence-and-weekly-volume)) in weeks 1 to 10 (500 shops), pauses in weeks 11 to 26 while pilots are hand-run and the application is built, and resumes in week 27 until the Washington and Oregon pool of 1,112 ([section 8](#8-funnel-from-distinct-reachable-prospects)) is used in week 39. This assumes the registered, remote-selling case in [12.4](#124-channel-sequence-and-weekly-volume). New paid pilots in a week = 0.008 × shops contacted three weeks earlier (0.08 × 0.40 × 0.25; 21 days [C]). Continuing(t) = continuing(t−1) × 0.96 + 0.75 × new pilots(t−1). Paying accounts(t) = continuing(t) + new pilots(t). Revenue = 149 × new pilots + 199 × continuing. Variable cost = 35.57 × paying accounts. Acquisition = 600 × new pilots. No refunds are modelled in the base case [A]; at the reference 60-repair shop the illustration in 5.1 puts them at 3.1%.

| Month | Weeks | Shops contacted | New paid pilots | Continuing accounts | Paying accounts | Revenue | Variable cost | Fixed | Acquisition | Net | Cumulative without founder | Cumulative with founder |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1-4 | 200 | 0.4 | 0.00 | 0.40 | 60 | 14 | 800 | 240 | −995 | −995 | −5,342 |
| 2 | 5-8 | 200 | 1.6 | 0.30 | 1.90 | 298 | 68 | 800 | 960 | −1,529 | −2,524 | −11,220 |
| 3 | 9-13 | 100 | 2.0 | 1.49 | 3.49 | 594 | 124 | 800 | 1,200 | −1,530 | −4,054 | −17,098 |
| 4 | 14-17 | 0 | 0.0 | 2.93 | 2.93 | 583 | 104 | 800 | 0 | −321 | −4,375 | −21,767 |
| 5 | 18-21 | 0 | 0.0 | 2.81 | 2.81 | 559 | 100 | 800 | 0 | −341 | −4,716 | −26,455 |
| 6 | 22-26 | 0 | 0.0 | 2.70 | 2.70 | 537 | 96 | 800 | 0 | −359 | −5,075 | −31,162 |
| 7 | 27-30 | 200 | 0.4 | 2.59 | 2.99 | 575 | 106 | 800 | 240 | −571 | −5,646 | −36,081 |
| 8 | 31-34 | 200 | 1.6 | 2.79 | 4.39 | 793 | 156 | 800 | 960 | −1,123 | −6,769 | −41,552 |
| 9 | 35-39 | 212 | 2.0 | 3.88 | 5.88 | 1,069 | 209 | 800 | 1,200 | −1,140 | −7,909 | −47,039 |
| 10 | 40-43 | 0 | 0.9 | 5.22 | 6.12 | 1,172 | 218 | 800 | 538 | −383 | **−8,292** | −51,770 |
| 11 | 44-47 | 0 | 0.0 | 5.68 | 5.68 | 1,131 | 202 | 800 | 0 | 129 | −8,163 | −55,989 |
| 12 | 48-52 | 0 | 0.0 | 5.46 | 5.46 | 1,086 | 194 | 800 | 0 | 92 | −8,071 | −60,245 |

- **Cash trough without founder compensation and with the founder building: USD 8,292 in month 10.** Total paid pilots 1,112 × 0.008 = 8.9, of which 6.7 continue. Paying accounts peak at 6.12 and decline 4% a month because no distinct prospects remain; by month 18 they are 4.27, monthly net is negative again (−102) and the cumulative position is −8,221. The plan is never cumulatively cash-positive through month 18.
- **With the build bought at the author's hours** (USD 24,058 to 35,362, spent in months 4 to 7): trough **USD 32,350 to 43,654** in month 10. With the chat's 160 hours it would be 19,886.
- **With founder compensation** (the founder builds; no separate build cash): −60,245 at month 12, −86,482 at month 18, still falling.
- **Plain statement:** the Washington and Oregon pool cannot reach break-even. Seven accounts (without founder) need 7 / (0.008 × 0.75) = 1,167 distinct shops, more than the 1,112 upper bound, and holding seven needs 0.28 replacements, or 47 new distinct shops, every month. Forty accounts (with founder) need 6,667 shops. The plan only works with a wider geography sold by phone, referrals, or better rates. None of those is evidenced.
- **Downside ramp, exact rules:** same outreach schedule; new pilots = 0.004 × shops contacted three weeks earlier; continuing(t) = continuing(t−1) × 0.92 + 0.5 × new pilots(t−1); revenue = 149 × 0.5 × new pilots (half refunded in full) + 149 × continuing; variable cost = 41.62 × (new pilots + continuing); acquisition = 1,200 × new pilots. Result: 4.4 pilots in total, at most 1.63 continuing accounts, cumulative **−13,660 at month 12 and −17,730 at month 18** without founder; −65,834 and −95,991 with founder.
- **In-person fallback case** ([12.4](#124-channel-sequence-and-weekly-volume)): only the 357 drive-range establishments can be presented to, all contacted by week 8, no second phase. 357 × 0.008 = 2.9 pilots, 2.1 continuing, 11.4 demos; paying accounts peak at 2.34; cumulative −8,096 at month 12 and −11,624 at month 18 without founder. Four pilots for gate C are not expected in this case.

### 7.5 What the buyer gets, as modelled

A 60-repair shop recovering one extra approved USD 150 operation on 20% of repairs gains 60 × 0.20 × 150 = USD 1,800 per month against a USD 299 plan, plus about 10 estimator hours [C]. Every input is an assumption; "no sourced figure was found" [C].

## 8. Funnel from distinct reachable prospects

- **Count** [S: SRC-15]: BLS QCEW, 2025 Q1, private establishments in NAICS 811121 (automotive body, paint and interior repair): Washington 639, Oregon 473, United States 35,122. Drive range from Vancouver: Whatcom 17, Skagit 14, Snohomish 70, King 184, Pierce 72, total 357.
- **What this is not:** the code includes paint and interior shops, dealer body shops and multi-shop operators. The number of shops meeting the profile in [12.1](#121-ideal-customer-profile) is **unknown**; 357, 639 and 1,112 are upper bounds.
- **Funnel** [C]: 250 contacted → 8% → 20 conversations → 40% → 8 free tests with demo → 25% → 2 paid pilots, in 21 days. Per shop contacted: 0.008 pilots, 0.006 continuing accounts.

| Case | Distinct shops (upper bound) | Demos | Paid pilots | Continuing accounts | Outreach weeks at 50 a week |
|---|---|---|---|---|---|
| Registered, remote selling, Washington | 639 | 20.4 | 5.1 | 3.8 | 12.8 |
| Registered, remote selling, Washington and Oregon (the ramp's assumption) | 1,112 | 35.6 | 8.9 | 6.7 | 22.2 |
| In-person presentation fallback, drive range only | 357 | 11.4 | 2.9 | 2.1 | 7.1 |

## 9. Stop rule

**Chat, translated** [C]: Offer: a free test on one old repair, then a USD 149 pilot (refund if less than USD 1,000 is recovered). When to stop: stop if tests at 10 shops yield under USD 100 on average.

**Research record** [C]: "Stop if closed repair order tests on 10 shops find under USD 100 of supportable missed items per repair on average, or if fewer than 2 shops pay after 10 demos." The research roadmap also had a week-1 gate (at least 6 of 10 owners say supplements cost 5 or more hours a week) and a week-2 gate (3 paid pilots from 6 hand-made packets); these are **not adopted as gates** and are kept as discovery measures in T-0.2.2.

**Does it fire when the assumed rates are true?**

1. *Fewer than 2 pay after 10 demos, close rate 25%.* P(X ≤ 1) = 0.75^10 + 10 × 0.25 × 0.75^9 = 0.0563 + 0.1877 = **24.4%**. One time in four the rule stops a plan whose assumptions hold. The funnel also yields 8 demos per cohort, not 10; with 8, P(X ≤ 1) = 36.7%. Ten demos need 313 shops.
2. *Average under USD 100 over 10 shops, one closed RO each* [C]. The chat gives no distribution. Illustration [A]: each RO either has one supportable USD 150 operation (probability q) or none. The average is 15 × K with K ~ Binomial(10, q); the rule fires when K ≤ 6.

| q | 0.20 (the brief's modelled rate) | 0.50 | 0.67 | 0.80 | 0.90 |
|---|---|---|---|---|---|
| P(rule fires) | 99.9% | 82.8% | 43.2% | 12.1% | 1.3% |

The brief's 0.20 is a rate of incremental approved operations, while the rule measures supportable found operations, a larger quantity; the first column is therefore a lower bound on q, not a forecast. The rule passes more often than not only if about two closed ROs in three carry a supportable missed operation, or if misses are several per RO as vendors advertise. This is the most important unproven number in the repository. The rule also measures dollars found, not cash collected, so passing it does not answer the decisive question.

**Proposed revision [P]** (this changes the chat's rule; it is not the same rule):

| Gate | When | Stop or continue |
|---|---|---|
| A, found dollars (the chat's test, unchanged) | After 10 free tests, about week 7 | Stop if the average supportable missed amount is under USD 100 per RO |
| B, payment (changed from 10 demos to 16) | After 16 demos (two cohorts, 500 shops), week 13 | Stop if fewer than 2 shops have paid. False stop at a true 25% close rate: 6.3%. If the true rate is 10%, the gate still passes 48.5% of the time, so it is weak evidence of the rate. In the in-person fallback case only 11 demos are expected; the gate is then read at 11, where the false stop is 19.7% |
| C, incremental collected cash (new) | Day 90 of each pilot; interim reading at week 21 on the pilots paid by week 8 (2.0 expected); full reading on the first 4 pilots, week 26 | Both limbs use one unit: **incremental collected dollars per shop for its 30-day window** ([PRD PM-1](PRD.md#11-success-metrics)). Stop if the median is below USD 149, the price. Reprice or reposition if fewer than half of the shops read reach USD 1,000 |

- **False stop of gate C.** Second limb, illustration [A] as in 5.1 with collected taken as equal to approved: with four 40-repair shops, fewer than 2 reach USD 1,000 in 7.3% of cases; with four 34-repair shops, 26.4%; with 60-repair shops, under 0.1%. First limb: **not computable**; it needs the variance of shop totals and of baselines, which nothing in the brief supplies.
- **G1, week 13** = A passed and B passed. It releases Phases 1 to 3 only (152 to 224 hours).
- **G1b, week 21** = interim gate C not failed. It releases Phases 4 to 7. Up to 224 build hours are therefore committed before any collected-cash result exists; this is a risk the founder accepts or declines (FD-03).
- **G2, week 26** = full gate C passed and release checks done, before outreach resumes in week 27.

Sample sizes are small; a pass is a reason to continue, not proof.

## 10. What buyer evidence would change the decision

- Incremental collected (not approved, not gross) dollars per shop in the first pilots, against each shop's baseline: decides everything.
- The share of approved dollars on checklist-originated lines. If near zero, the product only reformats what estimators already request.
- Owners saying they already use VaraFix, Repairscope or SupplementAI and are satisfied: drop or reposition.
- A shop's estimating-system licence forbidding it to give its estimates to a third party (LQ-01): stop until the vendor's sanctioned sharing route is available.
- Estimators or offices refusing to supply insurer responses and remittances: the metric cannot be computed and the refund term cannot be run.

## 11. Open decisions for the founder

Every legal question has a Phase 0 task with an exit criterion placed before the step it blocks ([execution-plan M0.1](execution-plan.md#milestone-m01--legal-gate-list-and-hand-test-kit)). None can be closed by this document.

| ID | Question | Blocks | Task |
|---|---|---|---|
| LQ-01 | Do CCC, Mitchell and Audatex licences allow a shop to give its exported estimate PDFs, and the insurer's estimate PDF, to a third-party tool, and may that tool send extracted lines to an AI provider? | Receipt of any real estimate, including the free test | T-0.1.2 |
| LQ-02 | For each OEM portal: may a subscriber cite a procedure by title and section to an insurer or a software vendor, link to it, or share a page? | Reference citations for that publisher; any future page upload | T-0.1.2 |
| LQ-03 | Telephone outreach into Washington: registration under RCW 19.158, and the federal rule's residual duties ([12.4](#124-channel-sequence-and-weekly-volume)) | The first call | T-0.1.1 |
| LQ-04 | Do sales visits create physical-presence nexus for Washington sales tax and B&O tax, and is the service taxable? The remote-seller threshold is USD 100,000 of Washington receipts [S: SRC-20]; software taxability was not confirmed today | The first invoice | T-0.1.5 |
| LQ-05 | Is entering the US for sales visits permitted business-visitor activity for the founder? The State Department page returned HTTP 403: unverified | The first visit, and the in-person fallback of LQ-03 | T-0.1.6 |
| LQ-06 | Which privacy law governs vehicle-owner data in estimates held by a Canadian company (PIPEDA, Washington law)? Unverified, no source consulted | Receipt of any real estimate | T-0.1.7 |
| FD-01 | Accept the revised gates in [section 9](#9-stop-rule)? | Week 1 | |
| FD-02 | Hosting in AWS us-west-2 instead of the founder's existing VPS ([TRD AD-10](TRD.md#9-architecture-decisions)) | Phase 2 | |
| FD-03 | Accept committing Phases 1 to 3 (152 to 224 hours) before any collected-cash reading? The alternative is to wait for G1b at week 21 and restart outreach about 8 weeks later than the ramp assumes | Week 13 | |

## 12. Go-to-market plan

One cohort is 250 shops [C]. One weekly volume is 50 new shops [P]. Every figure below uses those two numbers, the funnel in [section 8](#8-funnel-from-distinct-reachable-prospects) and the 75% continuation rate.

### 12.1 Ideal customer profile

Independent collision shop, 1 to 3 locations, 40 to 150 ROs a month, 1 to 3 estimators, 8 to 40 employees, mostly outside or alongside direct repair programs [C], in Washington. **Triggers** [C]: an estimator leaves, cycle time grows while waiting on approvals, the owner reviews unpaid operations at month end, the shop leaves a direct repair program. **Disqualifiers:** multi-shop operator or dealer-owned; fewer than 34 insurer-paid repairs a month (at the modelled USD 30 of incremental approved dollars per repair the USD 1,000 threshold needs 33.3; see [5.1](#51-refund-criterion)); mostly DRP work where the shop writes the insurer's estimate itself; estimating system not CCC ONE during the hand-run phase [P]; unwilling to supply insurer response documents, remittances and the baseline.

### 12.2 Named roles

| Role | Part |
|---|---|
| Lead estimator | Feels the pain, uses the product, supplies both PDFs, photos and insurer responses, approves every line |
| Owner or general manager | Signs, pays, decides at day 30 |
| Office manager or bookkeeper | Supplies remittance documents for collected amounts and the baseline counts |
| Can block | The estimator (no time, distrust of a second opinion); the estimating-system licence (LQ-01) |

### 12.3 Prospect list

Built by the founder from the SCRS affiliate list, which names the Washington Independent Collision Repair's Association and the Northwest Automotive Trades Association [S: SRC-16], the I-CAR Gold Class locator and Google Maps listings [C]. One row per location: shop name, published business phone, city, county, website, source, estimating system if stated, DRP status if stated. Checks: remove duplicates by phone and address; remove multi-shop operators and dealers; confirm the number is the published business line. Count available: at most 639 in Washington, 357 of them in drive range [S: SRC-15]; the qualified count is unknown until the list is built ([T-0.1.3](execution-plan.md#milestone-m01--legal-gate-list-and-hand-test-kit)). The brief's backup channel of estimator Facebook groups and its referral and distributor-partner programme are not used in this plan [P]; they are departures.

### 12.4 Channel, sequence and weekly volume

Phone first [C]. A Vancouver founder sells remotely; visits are batched into two day-trips per cohort to shops that have already taken a free test.

| Touch | Day | Content |
|---|---|---|
| 1 | 0 | Manual call to the published business line, 2 to 4 pm Pacific [C]; ask for the owner or lead estimator; offer the free closed-RO test. No price or refund statement by phone |
| 2 | 2 | Email with the price, refund conditions and what the shop supplies, only to an address the shop gave on the call or publishes for business contact |
| 3 | 7 | Second call |
| Demo | After the test | Result presented by video, or in person on a trip day |

**Volume:** 50 new shops a week, 250 in 5 weeks, up to 150 touches a week. **Founder hours per cohort [A]:** list 8.3 (2 minutes a shop) + first calls 12.5 + second calls 12.5 (3 minutes each) + emails 5 + 20 conversations 5 + 8 hand-run tests 16 + 8 demos 8 + 2 day-trips 16 + 2 hand-run pilots 30 + agreements and invoices 2 = **115.3 hours, 23.1 a week**. The brief's 80 hours for 30 days [C] did not count hand-run pilot delivery; this is a departure.

**Telephone position (LQ-03), not legal advice.**

- *Federal.* The Telemarketing Sales Rule exempts calls "between a telemarketer and any business", but the exemption "does not apply to" the requirements of 16 CFR 310.3(a)(2) and (4) [S: SRC-08]. Those two still bind every call: no misrepresentation of total cost, of any material restriction or condition, of performance or efficacy, or of any material aspect of a refund policy (310.3(a)(2)(i) to (iv)), and no false or misleading statement to induce payment (310.3(a)(4)). A refund mentioned without its conditions, or any recovery figure, would risk both.
- *Washington.* RCW 19.158 requires a "commercial telephone solicitor" to register with the Department of Licensing before doing business, and "doing business in this state" expressly includes "solicitation of purchasers located in Washington" (19.158.050(1)), so calling from Vancouver is covered. The business-to-business exclusion covers only resale and manufacturing inputs ((2)(b)(xix)); exclusion (2)(b)(iv) applies only when the caller does not intend to complete the sale on the call, does not make the major sales presentation on it, and makes that presentation "at a later face-to-face meeting". Penalties: a salesperson soliciting for an unregistered solicitor is guilty of a misdemeanor (19.158.150); a civil penalty of USD 500 to 2,000 per violation (19.158.140); knowing violations are criminal, rising to a gross misdemeanor and a class C felony with transaction value (19.158.160); a violation is also an unfair practice under the consumer protection act. A registered solicitor must state its registration number and street address and tell the purchaser of cancellation rights when a sale is made (19.158.110(6)), send a written confirmation, allow cancellation within three business days of it (19.158.120(1)), and may not require payment by credit card for unfair or deceptive reasons (19.158.100) [all S-arch: SRC-06].
- **Default adopted [P]: register before the first call** (fee not read: a missing input), state price and refund terms only in writing, send the written confirmation and cancellation notice with every agreement, and offer three payment methods. **Fallback, only if counsel confirms exclusion (iv) applies and LQ-05 is answered yes:** no registration, the major presentation made in person on trip days. The fallback limits the pool to 357 shops ([section 8](#8-funnel-from-distinct-reachable-prospects)). No call is made until T-0.1.1 records which case applies.

| Other rule | Effect on the plan | Source |
|---|---|---|
| 47 CFR 64.1200(a)(1)(iii): no autodialed or prerecorded calls to cellular numbers without consent; the do-not-call registry covers residential subscribers | Manual dialling only; no voicemail drops; no personal mobile numbers | S: SRC-08 |
| RCW 80.36.390(1)(b)(v): "telephone solicitation" in that section excludes business-to-business contacts | That section's do-not-call provisions do not apply; RCW 19.158 still does | S-arch: SRC-06 |
| RCW 19.158.110: identify caller, company and purpose within 30 seconds; end the call within 10 seconds on request; no calls before 8 am or after 8 pm recipient time; remove on request for at least a year | Built into the script and the suppression list | S-arch: SRC-06 |
| RCW 9.73.030: recording a private call needs the consent of all parties | No call or video demo is recorded | S-arch: SRC-06 |
| RCW 19.190.060: no commercial text messages to Washington residents without clear advance consent | No SMS outreach | S-arch: SRC-06 |
| CAN-SPAM applies to business-to-business email: accurate headers, honest subject, identified as an advertisement, valid postal address, opt-out honoured within 10 business days | Every email and follow-up carries sender name, company, postal address and an unsubscribe line | S: SRC-07 |
| RCW 19.190.020: no misleading subject line or obscured origin in email to a Washington resident | Plain subject lines; own domain | S-arch: SRC-06 |
| CASL section 6 applies because the sending computer is in Canada (s. 12(1)); the regulations exempt a message reasonably believed to be accessed in a listed foreign state, which includes the United States, if it conforms to that state's comparable law | CAN-SPAM compliance is also the condition for the CASL exemption; no email to Canadian recipients in this plan | S: SRC-09 |

### 12.5 Messages (synthetic; never sent)

**First touch, phone opening:** "This is Sam Reyes from SupplementPacket in Vancouver, registration number [number]. I am calling to offer your shop a free check of one closed repair order, and to ask whether a paid 30-day pilot might interest you afterwards. If your estimator gives me the insurer's final sheet and your final plan for one closed job, I will show you within two business days what was requested, what was paid, and what was never asked for. I will put the pilot price and terms in writing rather than quote them by phone. Who writes your supplements?"

**Follow-up email (only to an address the shop gave):**

> Subject: Free supplement check on one closed repair order — Example Collision
>
> Hi Dana, this is the advertisement I mentioned on Tuesday's call. Send one closed repair order (the insurer's final estimate PDF and your final repair plan PDF) through the secure folder link I will give you, and I will return a line-by-line difference list and a sample supplement packet in two business days, free.
>
> If you continue: a 30-day pilot costs USD 149, paid by card, bank transfer or cheque. Your estimator approves every line and sends every packet; I never contact an insurer. You supply both PDFs, your photos, the insurer's responses and remittances.
>
> Refund: the USD 149 is returned if, at day 60, insurer-approved dollars above your own three-month baseline are under USD 1,000, provided that (a) you gave the baseline count and at least 10 past supplemented repair orders by day 7, (b) you sent at least 8 packets through the service in the 30 days, and (c) you gave the insurer's response for at least 80% of them. The one-page agreement has the full definition and your right to cancel within three business days of the written confirmation. I do not promise that any insurer will approve or pay anything.
>
> Sam Reyes, SupplementPacket (example sender), 100 Example Street, Vancouver, BC V0V 0V0, Canada. Reply "stop" and I will not email you again.

### 12.6 Pilot offer and the step to a recurring account

Gets: draft packets within 1 business day, the three-amount ledger, a day-60 and day-90 report against baseline. Pays: USD 149 in advance. Supplies: the inputs in [section 5](#5-offer-channel-and-pilot). Ends the pilot: day 30. **Conversion step:** at the day-30 review the owner replies "continue" in writing and names the tier; month 2 is then invoiced. No reply means the account ends; there is no silent renewal [P]. The base case assumes 75% reply "continue" (section 6).

### 12.7 Three likely objections

| Objection | Honest answer |
|---|---|
| "CCC or Mitchell already does this" or "we use VaraFix / Repairscope / SupplementAI" | They find or word missed operations. If that already covers you, this adds only the estimate-to-estimate diff, the photo per line and the approved and collected record. The free test shows whether that is worth anything on your own RO |
| "Insurers will deny it anyway" | Possibly. Nobody controls approval; competitors' approval percentages are unsourced. The pilot measures approved and collected dollars above your own baseline and refunds under USD 1,000 on the written conditions |
| "My estimator has no time" | During the pilot the founder builds the draft; the estimator spends review time only. If review takes longer than the manual comparison, cancel |

### 12.8 First 30, 60 and 90 days

Weekly target: 50 new shops, 4 conversations, 1.6 tests with demo; 0.4 paid pilots a week from week 4. Acquisition is booked as in [7.3](#73-cac-one-definition).

| Point | Shops contacted | Conversations | Tests and demos | Paid pilots (cumulative) | Continuing accounts | Cash out (acquisition + fixed) | Founder hours |
|---|---|---|---|---|---|---|---|
| Day 30 (week 4) | 200 | 16 | 4.8 | 0.4 | 0 | 240 + 800 = 1,040 | 92 |
| Day 60 (week 8) | 400 | 32 | 11.2 | 2.0 | 0.30 | 1,200 + 1,600 = 2,800 | 185 |
| Day 90 (week 13) | 500 | 40 | 16 | 4.0 | 1.49 (3.49 paying with the pilots in their first month) | 2,400 + 2,400 = 4,800 | 231 |

Check against [7.4](#74-cash-required-during-the-acquisition-ramp): cash out less revenue plus variable cost is 1,040 − 60 + 14 = 995, then 2,800 − 358 + 82 = 2,524, then 4,800 − 952 + 206 = 4,054, the cumulative figures for months 1, 2 and 3. The same 2 pilots per 250 shops, 21-day cycle, 75% continuation and USD 600 CAC are used.

### 12.9 GTM stop rule

Gates A, B and C in [section 9](#9-stop-rule). Channel-level: drop phone as the first channel if 250 shops yield fewer than 10 conversations (half the assumed 20). Drop the product if gate A or C fails. Pause for counsel if LQ-01 or LQ-03 is answered against the plan.

## 13. Sources and assumptions

All consulted 2026-11-10. For archive rows the official host `app.leg.wa.gov` refused connections from the author's machine; the text was read in the Internet Archive capture dated in the row, and claims resting on it carry the label [S-arch].

| ID | Source | Jurisdiction | Scope used | Access restriction and capture dates |
|---|---|---|---|---|
| SRC-01 | https://supplementai.pages.dev/ ; https://supplementai.com/ | US vendor | Prices, features, claims; domain listing | None |
| SRC-02 | https://repairscope-prod.pages.dev/ ; https://repairscope.co/ | US vendor | Prices, features, claims | None |
| SRC-03 | https://varafix.com/ ; https://varafix.com/terms ; CollisionWeek 2026-08-25 launch note | US vendor | Price, scope, terms, launch date | CollisionWeek teaser only |
| SRC-04 | WAC 284-30-310, -320, -330, -360, -370, -380, -390 | Washington | Unfair claims settlement practices | **Archive.** -330: 2026-10-03, -360: 2026-09-17, -370: 2026-09-23 (each shows the version effective 2026-10-18). -310: 2026-08-08. **-320: 2026-06-09, -390: 2026-07-15, -380: 2026-01-17: pre-amendment captures, current text unverified.** -390 also compared with the Cornell LII copy |
| SRC-05 | RCW 46.71 | Washington | Automotive repair estimates and unlawful practices | **Archive**, 2026-02-18 |
| SRC-06 | RCW 19.158 (whole chapter), 80.36.390, 9.73.030, 19.190 | Washington | Telephone solicitation, recording, email and text | **Archive.** 19.158: 2026-01-19; 80.36.390: 2026-10-31; 9.73.030: 2026-11-08; 19.190: 2026-10-31 |
| SRC-07 | FTC, CAN-SPAM Act: A Compliance Guide for Business; 16 CFR 316 (eCFR) | US federal | Email | Guide read through a fetch tool summary; direct download returned 404 |
| SRC-08 | 16 CFR 310.3 and 310.6; 47 CFR 64.1200 (eCFR, current) | US federal | Phone | None |
| SRC-09 | CASL (S.C. 2010, c. 23) ss. 6, 12; SOR/2013-221 s. 3(f) and schedule (Justice Laws) | Canada | Email sent from Canada | None |
| SRC-10 | Toyota TIS Terms of Use, techinfo.toyota.com | US, licensor terms | OEM procedure rights, including the linking clause | One OEM only |
| SRC-11 | https://oem1stop.com/terms-use/ | US | Position-statement index rights | None |
| SRC-12 | https://www.enlyte.com/terms-use | US | Mitchell parent, website terms only | Product licence not public |
| SRC-13 | cccis.com policy pages; cccsecureshare.com permitted uses | US | CCC licence | **Blocked, HTTP 403. Unverified; search snippet only** |
| SRC-14 | Solera and Audatex terms | US | Audatex licence | **Not found, HTTP 404. Unverified, no source consulted** |
| SRC-15 | BLS QCEW open data, 2025 Q1, NAICS 811121 | US | Establishment counts | None |
| SRC-16 | https://scrs.com/affiliate-associations/ | US | Association names | None |
| SRC-17 | Repairer Driven News, 2026-04-10 | US | Repair cost and DRP share | **Archive**, 2026-04-10 |
| SRC-18 | Bank of Canada Valet, FXUSDCAD, 2026-11-09 | Canada | Rate comparison | None |
| SRC-19 | https://stripe.com/pricing | US | Card fee 2.9% + 30¢ | None |
| SRC-20 | Washington Department of Revenue, remote sellers page | Washington | USD 100,000 threshold | Software taxability pages returned 404 |
| SRC-21 | OWASP ASVS 5.0.0, tag `v5.0.0`, chapters V2, V4, V5, V6, V7, V8, V14, V16 | n/a | Security requirements cited in [TRD](TRD.md#113-threat-model) | None |
| SRC-22 | W3C WCAG 2.2 Recommendation | n/a | Criteria cited in [design.md](design.md#8-accessibility-map) | None |

Not opened today and therefore **unverified, no source consulted**: the ICBC policy and the 56.5% calibration figure (from the research record); every OEM's terms except Toyota's; I-CAR, SCRS and DEG terms; the US business-visitor rules; Washington software taxability; the telephone-solicitor registration fee; privacy law; any insurance-fraud statute. VaraFix's 2026 launch rests on a trade-press teaser; the launch dates of the other two vendors are unknown. Methods: arc42 section order is used in the TRD and the Spec Kit split of outcome, plan and task in the PRD, TRD and execution plan; neither site was reopened today.

**Unresolved assumptions preserved:** every funnel rate, the continuation rate, churn, CAC, revenue per account, the tier mix, packets per month, recovery per repair, hand-run hours, hand-run capacity, and the share of shops meeting the profile.
