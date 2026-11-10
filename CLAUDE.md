# CLAUDE.md — SupplementPacket

Read [AGENTS.md](AGENTS.md) first; it is canonical. This file adds only what is specific to this product. Commands named in this repository are proposed until code exists.

## The question

Does a Washington collision shop collect incremental cash after estimator review? Every change should make that easier to answer honestly: requested, insurer-approved and collected are separate amounts per repair order, compared with the shop's own baseline ([PRD section 11](PRD.md#11-success-metrics)).

## The buyer's workflow

Estimator uploads the insurer estimate and the shop estimate → checks the parsed lines and totals → reviews the difference list and checklist prompts → attaches the shop's photos and reference citations → approves or excludes every line → freezes the packet → downloads it and **sends it personally** → marks it sent → records the insurer's response per line → the office records payments → the owner reads the ledger and pilot report. The owner pays; the estimator is the daily user ([Decision section 1](Decision.md#1-proposed-decision)).

## Highest-consequence error

**An unapproved or unsupported line reaches an insurer.** It is defined in [PRD section 9](PRD.md#9-highest-cost-user-mistake). Guard it in every change: approval is per line and per permitted user; any change to a line, its photos or references, a source line it depends on, or a comparison re-run removes approval; freezing rechecks approvals under a lock and refuses anything that differs from what the estimator's review screen displayed, including the email draft; frozen packets never change except by a licensed-content takedown; evidence belongs to the same repair order; and there is no code path that sends.

## Sensitive data

- Estimate PDFs and response documents: vehicle-owner name and address, VIN, claim and policy numbers.
- Photos: plates, belongings, sometimes people; location metadata.
- Per-insurer requested, approved and collected amounts: commercially confidential to each shop.
- Licensed material: OEM procedures, position statements, estimating-guide content. Reference only ([Decision 3.1](Decision.md#31-rights-to-supporting-repair-material)).

## Prohibited shortcuts

- Do not add any feature that emails, uploads or otherwise delivers a packet to an insurer, "to save the estimator a step".
- Do not let the Operator, a job or a model approve, freeze or mark sent, even in test helpers.
- Do not auto-approve lines, including checklist items and exact matches, and do not add batch approval.
- Do not let an evidence change, a source-line correction or a comparison re-run leave a line approved.
- Do not count a `needs_review` line as matched or as a difference, and do not let it block other lines.
- Do not fill a missing claim number, adjuster, baseline amount or evidence with a placeholder so a step can proceed; "not provided" and "not computable" are valid results.
- Do not report gross approved or collected dollars as the pilot result; the refund test and gate C are incremental over the shop's baseline.
- Do not count a payment as collected without the packet it pays and a remittance document, and do not count a superseded packet's approvals.
- Do not merge requested, approved and collected into one "recovered" number, and do not reuse the word "approved" for both the estimator's and the insurer's decision.
- Do not add a procedure-document upload, a URL field for subscription-portal material, or any claim that the product detects licensed content.
- Do not store, quote, summarise or send to a model any OEM procedure or estimating-guide text; do not build tables of labour times or part prices; do not combine line data across tenants.
- Do not send estimate content to an AI provider unless the tenant's consent is recorded and the licence question LQ-01 is closed.
- Do not use floating point for money; do not let a model compute or adjust an amount.
- Do not present vendor-advertised recovery or approval percentages as facts in the product or its marketing.
- Do not cite an insurance regulation in a packet or tell a shop it has a legal right to a response.
- Do not state a price, a refund or a recovery figure in a phone script; do not call before T-0.1.1 is closed; do not receive a real estimate before T-0.1.2 and T-0.1.7 are closed for that shop.
- Do not keep anything a user typed in browser storage.
- Do not record calls or demos; do not add SMS outreach ([Decision 12.4](Decision.md#124-channel-sequence-and-weekly-volume)).

## First verification checks when implementation begins

1. `make dev` starts every service healthy: E2E-09 (implemented in B1 for API, worker and database; see verification-report-fixing.md section 9).
2. Tenant isolation on every endpoint and in the worker: IT-01.
3. Operator and Office cannot approve, freeze or mark sent: IT-02.
4. Freeze refuses a line, evidence item or email draft changed after approval or review: IT-06, IT-18, with UT-07 and UT-08.
5. Totals reconciliation and the unreconciled block: UT-02, E2E-02.
6. Three-amount ledger, supersede and payment evidence, and the incremental refund test: UT-10, UT-11, UT-12, UT-17, UT-18.
7. Upload idempotency and stale job events: IT-03, IT-04.
8. Licensed-material controls and takedown: IT-15, IT-19.
9. Log redaction and correlation: IT-11.

Test definitions are in [execution-plan section 7](execution-plan.md#7-test-catalogue); risks are in [verification-report-fixing.md section 5](verification-report-fixing.md#5-production-risk-register).
