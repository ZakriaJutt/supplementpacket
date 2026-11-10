# Design brief — SupplementPacket

Proposed UX and UI direction for the screens in [App-flow.md](App-flow.md#1-screen-inventory). The user is an estimator at a desk in a busy shop office, moving between the estimating system, a phone and this tool. Nothing here is built or tested.

## 1. Design decisions

| ID | Decision | Reason |
|---|---|---|
| DD-01 | The three ledger amounts always appear together, in the same order and colours, and are never summed | The decisive question is whether cash is collected, not what was asked |
| DD-02 | Draft, Approved, Excluded, Frozen and Sent are distinguished by a text label plus an icon; colour is secondary | Estimators must not mistake a draft for an approved line |
| DD-03 | Every suggested line shows where it came from (Comparison, Checklist, Typed by you, AI suggestion) | Origin drives trust and the incremental metric |
| DD-04 | Source evidence is one click away and opens beside the line, not in a new tab | Checking must be cheaper than trusting |
| DD-05 | The product says in plain words that it does not send | Removes any doubt about who contacts the insurer |
| DD-06 | Dense tables, large numerals for money, no decorative imagery | Desk work with many lines |
| DD-07 | References show title, publisher and identifier only; no procedure text preview | [Decision 3.1](Decision.md#31-rights-to-supporting-repair-material) |

## 2. Hierarchy and layout

- **Shell:** top bar with shop name, location switcher, navigation (Repair orders, Tracker, Pilot, Settings) and the user menu with Sign out. Inside an RO, a header shows RO number, vehicle, insurer, the step bar (Documents, Lines, Packet, Ledger) and the three totals.
- **Reading order on work screens:** what needs a decision first (blockers, needs-review lines), then the lines, then totals, then history.
- **Grid:** 12 columns, 1,280 px design width, 24 px gutters; content maximum 1,440 px. Work tables use the full width; forms are at most 640 px wide.
- **Split view** (S-05, S-07): source document on the left 5 columns, data on the right 7; the divider is adjustable with the keyboard and with buttons, never by dragging only.

## 3. Typography

System UI font stack; no web fonts. Sizes: 14 px table text, 16 px body and inputs, 20 px section headings, 24 px page titles, 28 px ledger totals. Money and hours use tabular numerals, right-aligned, always with the currency code on totals ("USD 1,284.50"). Line height 1.5 for body, 1.35 in tables. Text can be resized to 200% without loss of content.

## 4. Colour

| Token | Light value | Use |
|---|---|---|
| `ink` | #1B1F24 | Text |
| `ink-muted` | #57606A | Secondary text (4.5:1 or better on `surface`) |
| `surface` | #FFFFFF | Page |
| `surface-alt` | #F4F6F8 | Table header, panels |
| `line` | #8C959F | Borders of inputs and controls (3:1 against `surface`) |
| `action` | #0B5CAD | Primary buttons, links |
| `requested` | #5B3FA6 | Requested amount marker |
| `insurer-approved` | #0F6B4F | Insurer-approved amount marker only |
| `estimator-approved` | #1F4E79 | "Approved by you" line status only; never used for an amount |
| `collected` | #8A5A00 | Collected marker |
| `warning` | #8A4B00 on #FFF4D6 | Needs review, unreconciled |
| `danger` | #A4262C | Errors, denied, destructive confirmation |

Every colour meaning is repeated in text or an icon. Contrast figures are design intent and must be measured on the built screens.

## 5. Components

| Component | Behaviour |
|---|---|
| Status chip | Icon plus word: Draft (outline circle), Approved by you or by a named estimator (check, `estimator-approved`), Excluded (slash), Needs review (triangle), Frozen (lock), Sent (arrow), Superseded (history) |
| Origin badge | Comparison, Checklist, Typed by you, AI suggestion |
| Lines table | Sticky header; sortable by category and amount; row checkbox (for Exclude selected only); per-row Approve and Exclude buttons at least 24 by 24 px with 8 px spacing; row opens on Enter |
| Ledger strip | Three boxes left to right: Requested, Insurer approved, Collected (evidenced); under them "Not yet approved", "Approved, not yet collected" and, when present, "Recorded, not evidenced" in muted text outside the boxes |
| Job chip | Queued, Reading estimate…, Building PDF…, Failed, Partly done; elapsed time; Retry where safe |
| Evidence tile | Thumbnail with file state; "Taken by our shop" tag or the note saying who took it; who attested and when; Remove (removes the line's approval, and says so first) |
| Reference card | Material type, publisher, title, identifier, date accessed; Open link only for openly published material |
| Blocker list | One row per blocker with a link that moves focus to the line |
| Confirmation dialog | States the object, count and total in words; primary button repeats the verb ("Freeze packet"); focus starts on Cancel for irreversible actions |
| Toast and live region | Brief confirmations; never the only place an error appears |

## 6. Principal screens

- **S-06 Lines workspace.** RO header and ledger strip at the top. Left rail: filters (All, Draft, Approved, Excluded, Needs review) with counts, and the checklist grouped by repair area. Centre: the lines table with columns Category, Description, Insurer estimate, Shop plan, Requested, Origin, Evidence, Status, actions. A yellow "Needs review (3)" group sits above the table. Sticky footer: "9 approved · USD 1,284.50 requested · 4 draft" and the Review packet button.
- **S-07 Line detail.** Left: the two source lines, each with "Show in PDF" that opens the page with the row outlined. Right: amount, explanation box, photo grid with an upload target and a file button, reference cards, Approve and Exclude. Bottom: history of this line.
- **S-08 Packet review.** A single column that reads like the packet: recipient block, each line with amount, evidence thumbnails and reference titles, total. A fixed right panel lists blockers, then the Freeze button with the sentence "Frozen packets cannot be edited. You send the packet yourself."
- **S-09 Packet.** Status chip, PDF preview, Download, the email draft in a read-only box with Copy, and a boxed notice: "SupplementPacket does not send this for you." Below: Mark as sent.
- **S-10 RO ledger.** Ledger strip large at the top. Per packet a table: Line, Requested, Response (select), Approved amount, Reason, Date. Payments table beneath with Add payment. The two gap figures sit between the boxes.
- **S-12 Pilot report.** Three condition rows with Met or Not met and counts; two rows of three figures, each written out: approved on qualifying packets, baseline expectation, incremental approved against the USD 1,000 threshold; then evidenced collected, baseline expectation, incremental collected (PM-1). PM-2 below. Each figure has its formula in a sentence and "Show the packets counted".

**Responsive behaviour.** Built for 1,280 px and wider. From 768 to 1,279 px the left rail collapses into a filter button and the split view stacks. Below 768 px the lines table becomes one card per line with the same actions; evidence upload and response entry stay usable on a phone; parse review shows a notice that it is best on a wider screen and still works by stacking. No horizontal scrolling at 320 px width except inside the PDF viewer.

## 7. Microcopy

| Situation | Text |
|---|---|
| Pending operation | "Reading the insurer estimate… usually under a minute. You can keep working; this page updates by itself." |
| Pending, long | "Still reading (2 min). Nothing is lost. You can leave and come back." |
| Recoverable error | "We could not read page 3 of this PDF. Your other lines are safe. Retry, or enter the lines from page 3 yourself." |
| Partial success | "7 of 9 photos added. 2 failed: IMG_2041.heic (over 15 MB), IMG_2044.jpg (not an image). Retry failed." |
| Human approval, line | "Approve this line? You confirm the work is required for this repair and the amount is correct. Approved by you, Alex Kim, will appear on the packet." |
| Human approval, freeze | "Freeze packet 2 for RO 4471: 9 lines, USD 1,284.50. Frozen packets cannot be edited. You send the packet yourself." |
| Approval removed | "Approval removed because the amount changed. Review and approve again." (the same sentence names a photo, a reference, a source line or a re-run comparison when that was the change) |
| Changed since review | "Nothing was frozen. 2 things changed since you reviewed this packet: a photo was replaced on line 4; the email text was edited. Review them, then freeze." |
| Photo attestation | "These are photos of this vehicle, taken by our shop. They are not screenshots or copies of repair procedures, estimating guides or other licensed documents." |
| Not evidenced | "Recorded, not evidenced. Attach the remittance to count this as collected." |
| Not permitted | "Only the shop's estimator can approve lines. You can prepare drafts." |
| Unreconciled | "Parsed lines total USD 4,212.10; the estimate prints USD 4,262.10. Fix the lines or confirm the difference with a reason before freezing a packet." |
| No evidence | "No attached evidence. Add a photo or reference, or explain in at least 20 characters why none is needed." |
| Not computable | "Not computable — fewer than 10 complete baseline repair orders. We do not estimate a baseline." |

**Inspecting source evidence.** "Show in PDF" on any parsed or compared line opens the page with the row outlined; photo thumbnails open full size with the file's upload date and uploader; a reference card for openly published material opens the publisher's page in a new tab with a visible "opens in a new tab" label; a subscription-portal reference shows the citation only.

**Correcting a suggestion.** Every suggested value is an ordinary editable field. Editing marks the line "Edited by you"; the original value stays visible in the history. An AI wording suggestion sits in the explanation box with the label "Suggestion — edit before saving" and a Discard button.

**Drafts versus approved results.** Draft lines have an outline chip and no approver name. Approved lines show the check chip, the approver and the time. A frozen packet shows a lock, the packet version and the PDF code; its screen has no edit controls. Draft packet previews carry a diagonal "DRAFT — NOT APPROVED" watermark that is absent only from the frozen PDF.

**Interaction feedback.** Buttons show a busy state within 100 ms and are disabled while a request is in flight. Saves confirm inline beside the field ("Saved"). Totals that change are updated in place and announced. Errors appear beside the control and in a summary.

## 8. Accessibility map

Target: WCAG 2.2 level AA [S: SRC-22]. Nothing is built, so every row is a planned manual check with result **Not run**. No conformance is claimed.

| Criterion | Screens | Manual check |
|---|---|---|
| 1.1.1 Non-text Content | S-07, S-08, S-09 | Each photo thumbnail has a text name (file name and line); status icons have text |
| 1.3.1 Info and Relationships | S-05, S-06, S-10 | Tables use header cells; a screen reader announces column and row for each amount |
| 1.4.1 Use of Color | S-06, S-10, S-12 | Status and the three amounts are identifiable in greyscale |
| 1.4.3 Contrast (Minimum); 1.4.11 Non-text Contrast | All | Measure text at 4.5:1 and control borders and focus rings at 3:1 |
| 1.4.4 Resize Text; 1.4.10 Reflow | S-06, S-10 | 200% zoom and 320 px width without loss or two-way scrolling (PDF viewer excepted) |
| 2.1.1 Keyboard | S-05, S-06, S-07 | Review, edit, approve, exclude, upload, resize the split view and open the PDF location with the keyboard only |
| 2.4.3 Focus Order; 2.4.7 Focus Visible | S-06, S-08 | After a dialog closes focus returns to the control that opened it; focus ring visible on every control; after the S-06 "line changed" conflict focus is on that line's message; after a refused freeze on S-08 focus is on the heading of the "Changed since you reviewed" list, whose items are links to the lines |
| 2.4.11 Focus Not Obscured (Minimum) | S-06 | The sticky footer and header never fully cover the focused row |
| 2.5.7 Dragging Movements | S-05, S-07 | Photo upload and split-view resizing work without dragging |
| 2.5.8 Target Size (Minimum) | S-06, S-10 | Row buttons are at least 24 by 24 CSS px or spaced so |
| 3.3.1 Error Identification; 3.3.3 Error Suggestion | S-04, S-06, S-07, S-08, S-10 | Submit invalid data; focus moves to the error summary; each message names the field and the fix |
| 3.3.2 Labels or Instructions | S-04, S-12 | Optional fields say "optional"; amount fields state the currency |
| 3.3.4 Error Prevention (Legal, Financial, Data) | S-08, S-09, S-10, S-14 | Freeze, mark sent, payment and deletion each show a review step and can be cancelled |
| 3.3.7 Redundant Entry | S-04, S-10 | Insurer, adjuster and claim details typed once are reused on the packet and ledger |
| 3.3.8 Accessible Authentication (Minimum) | S-01, S-02 | Password managers and paste work for the password and the code |
| 2.2.1 Timing Adjustable | All | Before the idle timeout a dialog offers to extend the session; unsaved text survives sign-in from the server-side draft |
| 4.1.3 Status Messages | S-04, S-06, S-07, S-09, S-10 | Job completion, partial failure, "Saved", and changed totals are announced by a screen reader without moving focus |

**Known gaps, stated as gaps:** the embedded PDF page view of a third-party estimate is not accessible to screen readers beyond the parsed lines beside it (1.1.1 not met for the page image itself); the chart on S-11 is supplementary to its table.
