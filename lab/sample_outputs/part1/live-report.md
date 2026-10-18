# SignalDesk Singapore pilot — product analysis (rev. 2: low-tech-support small businesses)

Northstar Insights / SignalDesk. Internal evidence is synthetic classroom data (fixture v1, 2026-09-17) from data/ files; competitor claims are real public web excerpts and are explicitly limited. Revision 2 narrows the segment to small businesses with limited technical support and recommends one pre-pilot improvement.

## 1. Recommendation and proposed initial segment
Run a narrow, learning-oriented pilot — no broad launch — with **Singapore small businesses (roughly 6–15 staff) that have limited technical support: no analyst, no developer, English-language feedback, collected weekly** (profiles like INT-SME-01 and INT-SME-02).

**One pre-pilot improvement: build the CSV import preview with actionable errors** (see §3.1). If engineering cannot give a defensible estimate of delivering it before the six-week start, delay the pilot rather than run it on terse-error manual uploads.

## 2. Customer needs (synthetic internal evidence)
- **INT-SME-01** (owner, 6-person online retailer, customer-interviews.md): a short list of main problems with examples she can open to verify; an import preview that tells her what needs fixing; no column renames or setup calls; ≤30-minute self-setup; English sufficient. No analyst or developer.
- **INT-SME-02** (operations lead, 12-person service business): saving time first; automatic email import long-term, manual weekly CSV acceptable only for a short pilot; asynchronous colleague comments; traceability valued over charts.
- **INT-MID-03** (research manager, regional software team): team-level access, audit export, CRM integration; analyst available for CSV prep; weekly summary alone insufficient; wants theme-accuracy evidence on own terminology. **Out of scope for this segment**, preserved as disagreement.

**Preserved disagreement:** INT-MID-03 dismisses guided onboarding and the weekly summary; INT-SME-01 calls the import preview more valuable than another dashboard. The revised segment sides with the SMEs; MID-03's requirements remain valid for a future mid-market product.

## 3. Product fit, gaps, and the one improvement (synthetic internal evidence)
**Fit:** traceable themes (link back to source rows), reviewer-approved labels, weekly Markdown summary, comment threads — matches both SMEs' core asks.

**Gaps for low-tech-support small businesses:**
- Manual fixed-column CSV upload with terse errors; no import preview; no onboarding checklist; ~2 staff-hours setup per customer (product-features.md).
- No CRM/email/messaging integration (INT-SME-02's permanent-workflow want).
- No fine-grained roles or audit exports (mid-market blocker, INT-MID-03).
- English-only; no multilingual evaluation results — a constraint for broader Singapore launch later.

### 3.1 Recommended improvement: CSV import preview with actionable errors
Why this one (options compared in runtime/notes/improvement-options.md):
1. **Named by the segment**: INT-SME-01 explicitly says an import preview beats another dashboard, and that renaming columns or booking setup calls makes her defer adoption.
2. **Relieves the binding constraint**: ~2 staff-hours setup per customer (product-features.md) vs. 4 support hours/week (internal-constraints.md) — up to five organizations would exhaust part-time support within one to two weeks. This was the report's strongest reason to delay; the preview is the improvement that most directly attacks it.
3. **Enables the ≤30-min self-setup requirement** and feeds the pilot's own success measure (setup time per organization).
4. **Ruled-out alternatives**: onboarding checklist helps only after imports work; one integration is larger scope and manual CSV is acceptable short-term; finer permissions serve mid-market, not this segment.

**Caveat:** no validated delivery estimates exist for any candidate (internal-constraints.md); this recommendation assumes engineering can commit, and the pilot should slip otherwise.

## 4. Two-competitor comparison (real public evidence; search excerpts are partial, not full webpages)
Details and URLs in runtime/notes/competitors.md.

**Dovetail** (http://dovetail.com/; https://dovetail.com/roles/customer-experience; https://docs.dovetail.com/academy/analyze-app-reviews):
- AI clusters tickets/reviews/surveys into themes; topics → themes → data-points hierarchy keeps source conversations attached (similar traceability to SignalDesk).
- ~38 native integrations plus API/MCP/CLI; real-time sentiment monitoring.
- Limitation: excerpts don't cover pricing, onboarding effort, or SME suitability.

**Productboard** (https://www.productboard.com/customer-feedback-tool; https://www.productboard.com/feature-voting-forum; 2022 Core Features PDF):
- Central feedback repository; Zendesk/Intercom/Slack/Salesforce integrations plus Zapier/Chrome/API; filter by company/user/tag/segment; insights linked to feature ideas; prioritization scores and value-vs-effort matrix.
- Limitation: excerpts emphasize product-manager prioritization workflows; the pricing PDF is dated and excerpt-only.

**Implication for this segment:** both competitors automate imports — exactly the step SignalDesk leaves manual — which strengthens the case for the import-preview improvement before the pilot. Neither excerpt establishes SME/low-tech-support focus, so a wedge for non-analyst teams remains unproven and needs pilot evidence. Excerpt-based comparison is incomplete; a full competitor comparison cannot be claimed.

## 5. Feasible next step and unanswered questions
**Next step:** with engineering's commitment, build the CSV import preview with actionable errors, then run a 4-week pilot with up to 5 Singapore small businesses (no analyst/developer on staff). Proposed success measures (not yet measured): setup time per organization, support requests per organization, share of suggested themes traceable to source feedback; target direction: setup time near INT-SME-01's 30-minute self-setup expectation.

**Unanswered questions:**
- Can the import preview be delivered before the earliest six-week start? (No validated estimates; determines pilot vs. delay.)
- Does theme accuracy hold on customers' own terminology (INT-MID-03's open question, still relevant post-import)?
- Is the non-analyst small-business segment real in Singapore at meaningful scale? Three interviews are illustrative, not representative market research.
- Which competitor capability gap matters most to this segment, and at what price point? (Pricing/onboarding evidence not covered by current excerpts.)
- Will multilingual support be required before any broader Singapore launch?
