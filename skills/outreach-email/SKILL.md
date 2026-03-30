---
name: outreach-email
description: Draft a short, personalized outreach email for a job opportunity — 3 paragraphs covering intro/interest, relevant skills from Meta experience, and a closing ask for a call. Use when the user wants to reach out to a recruiter or contact about a role.
argument-hint: "[recipient name] [recipient email] [job description or URL]"
---

Draft a personalized outreach email using the inputs provided in `$ARGUMENTS` and the context below.

## Inputs to extract from `$ARGUMENTS`

- **Recipient name** — the person being emailed
- **Recipient email** — their email address
- **Job description** — either pasted text or already fetched content describing the role and company

If any of these are missing, ask for them before continuing.

---

## Step 0 — Research the company and confirm news to include

1. Use WebSearch to find recent news about the company (last 12 months). Look for:
   - Funding rounds, acquisitions, or valuation milestones
   - Product launches or major feature releases
   - Notable partnerships, customer wins, or growth metrics
   - Press coverage or founder/executive interviews

2. Present a short numbered list of the most interesting findings to the user (2–4 items max). Ask: *"Which of these would you like to mention in the email, if any? You can pick one, suggest your own, or say 'none'."*

3. Wait for the user's response before drafting the email. Use their chosen news in paragraph 3.

---

## Joelchrist's Background & Projects (Meta, Apr 2025 – Mar 2026)

Use this dossier to select the most relevant 2–3 accomplishments when writing paragraph 2. Pick projects that best match the role's tech stack, scope, or domain.

**ADM Graph Viewer (Jan – Mar 2026)**
- Built an interactive graph visualization tool in VCI rendering Rights Manager entity relationships (Assets, MPX Clusters, Conflicts, Matches) as a navigable graph
- Replaced manual querying and ID cross-referencing for ops and engineers investigating asset hierarchies
- Designed modular trait-based backend with a context-aware loader factory and reusable traits for dynamic ADM/MPX switching
- Implemented level-based lazy loading on frontend and backend for performance on large graphs
- Extracted layout logic into reusable hook `useAssetDataModelLayout`; built UX features including deep linking, context switching, and node highlighting
- Owned project end-to-end: Design Doc, Proposal, Deep Research Report, structured feedback form, launch intro doc

**Reports API — Reports Widget & Reports Tab (Jul – Nov 2025)**
- Built full-stack from GraphQL schema through frontend widget — rights holders gained a single surface to view and download their five most recent data exports
- Designed GraphQL schema patterns (RightsManagerDataReportPattern, BulkActionReport) unifying pre-generated and on-demand reports
- Implemented filtering, sorting, pagination with retention logic and boundary cases
- External adoption: Reports Tab drove 5,969 downloads from 393 unique accounts; Reports Widget recorded 3,156 clicks from 1,484 unique accounts (~35 clicks/day)
- Drove project from design doc through rollout; partnered with Alex Chun, Hasim K, and Yueran Zhao

**Overview TodoList (May – Aug 2025)**
- Replaced legacy todo widget with a multi-category component showing counts for Ineligible Content, Reference Conflicts, and Match Disputes across three timeframes, with deep links to action pages
- Resolved production OOM errors by optimizing EntQL queries
- Built full stack: GraphQL APIs for todo list counts and React frontend with tabs, badges, and timeframe switching
- Refactored Match Disputes to use Alacorn Queries, replacing Galileo; fixed match dispute count inconsistency by removing non-actionable statuses
- External adoption: 4,198 action-item clicks from 545 unique accounts; 5,803 timeframe-selector clicks

**Exportables List / CSV Mappers (Dec 2025 – Jan 2026)**
- Consolidated fragmented CSV export mappers for Reference Conflicts, Reference Library, Ineligible Content, and Match Rules — enabling standardized data exports across four content types
- Added ODDE type param to differentiate cluster-level vs copyright-level rows
- Wrote integration and unit tests covering Music Works, Copyrights, and Conflicts
- Established repeatable mapper pattern (capability checks → quality checks → tests) for future export types; authored Mapper Design Doc, Eng Execution Doc, and Rollout plan

**Data Quality & Consistency (May – Oct 2025)**
- Flagged and addressed duplicate exclusion ownership segments by building consistency rules and fixers for MediaCopyrightUpdateRecord and VideoCopyright
- Documented findings in a Deduplication Design Doc

---

## Email Format

Write the email in exactly **3 short paragraphs**:

**Paragraph 1 — Intro & Interest**
Open with who you are, where you currently work (Meta), and a specific, genuine reason why this company or role caught your attention. Reference something concrete from the job description or company (product, mission, tech, growth stage). Keep it 2–3 sentences.

**Paragraph 2 — Relevant Skills**
Highlight 2–3 of the most relevant projects from the dossier above, matched to what the role requires. Be specific — name the project, what you built, and the impact. Keep it 3–4 sentences max. Do not list everything; pick what's most relevant.

**Paragraph 3 — Closing & Follow-up**
This is the most confident paragraph. If the WebSearch from Step 0 surfaced something specific and recent — a funding round, a product launch, a notable partnership, a growth metric — open with it naturally (e.g. "Saw that you just closed your seed with Maveron..." or "The recent [X] caught my eye..."). If nothing newsworthy was found, open instead with a specific observation about the company's mission or traction from the job description itself. Then make a direct, confident case for why you're a strong fit: name 1–2 concrete reasons (skills, mindset, or past experience) that map directly to what they need. Close with a clear ask: *"Would love to find 20–30 minutes to connect — what's the best time for a quick call?"* or a natural variation. Aim for 3–5 sentences total.

---

## Signature (always include exactly as written)

```
Best,
Joelchrist Abreu
ajoelcrist@gmail.com
+1 (516) 637-6783
linkedin.com/in/jc-abreu
```

---

## Output

Print the full email ready to send, including:
- `To:` line with the recipient's email
- `Subject:` line (concise, specific to the role/company — not generic)
- The 3-paragraph body
- The signature block

Keep the tone warm, direct, and confident — not stiff or overly formal. No fluff.
