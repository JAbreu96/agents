---
name: resume-review
description: Analyze a resume against a job description like a senior recruiter. Gives a match score, top missing keywords, red flags, rewrites the experience section using the Google XYZ formula, then runs an ATS + hiring manager scan. Use when the user provides a job URL or pastes a job description.
argument-hint: "[job_url or company_name (optional)]"
---

Analyze Joelchrist's resume against a job description using the arguments: `$ARGUMENTS`

## Base Resume (Google Doc)

- **Google Doc ID:** `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk`
- **Google Drive Resumes Folder ID:** `10QqchL7fb18Hw3Gd5KLBHct96ijIb3rR`
- **Service Account:** `/Users/joelchristabreu/Documents/agents-491602-service-account.json`
- **Link:** https://docs.google.com/document/d/1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk/edit

**Read the live resume at the start using the Docs API:**

```python
from googleapiclient.discovery import build
from google.oauth2 import service_account

DOC_ID = "1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk"
SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/documents.readonly"]
)
docs = build("docs", "v1", credentials=creds)
doc = docs.documents().get(documentId=DOC_ID).execute()

# Extract plain text from all paragraph elements
lines = []
for el in doc.get("body", {}).get("content", []):
    if "paragraph" in el:
        text = "".join(
            r.get("textRun", {}).get("content", "")
            for r in el["paragraph"].get("elements", [])
        ).strip()
        if text:
            lines.append(text)

resume_text = "\n".join(lines)
print(resume_text)
```

Use the output of this script as the resume content for the analysis. If the script fails, fall back to the `mcp__claude_ai_Google_Drive__read_file_content` tool with fileId `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk`.

---

## Step 1 — Get the job description

If a job_url was provided:
- If it's a Greenhouse URL (`greenhouse.io/{company}/jobs/{id}`): fetch `https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}` and extract the `content` field (strip HTML).
- If it's a Lever URL (`jobs.lever.co/{company}/{uuid}`): fetch `https://api.lever.co/v0/postings/{company}/{uuid}` and extract `descriptionPlain`.
- If it's a LinkedIn URL or any URL that fails to fetch: ask the user to paste the job description.
- Otherwise: use WebFetch to retrieve the page content.

If no URL was provided and no description is available: ask the user to paste the job description before continuing.

---

## Step 2 — Recruiter analysis (match score + gaps)

Act as a **senior recruiter** for the exact company and role.

Analyze the resume against the job description and return:

**Match Score: X/100**

Brief 1–2 sentence rationale for the score.

**Top 5 Missing Keywords**
List the 5 most important keywords or skills from the job description that are absent or weak in the resume. For each, note where it could naturally be added.

**3 Red Flags a Hiring Manager Would Spot in Under 10 Seconds**
Be blunt. What would make a recruiter pause or skip this resume for this specific role?

---

## Step 3 — Rewrite the experience section

Rewrite Joelchrist's experience section to:
- Naturally incorporate the missing keywords from Step 2 where they genuinely apply — don't force keywords that don't fit
- Address the red flags identified in Step 2
- Apply the **Google XYZ formula** to every bullet: _Accomplished X as measured by Y by doing Z_
- Keep all existing metrics (5,969 downloads, 393 accounts, 545 accounts, 5 production agents, etc.)
- Maintain the same company names, titles, and date ranges
- Do not invent experience or fabricate metrics

Return the full rewritten experience section, formatted cleanly.

---

## Step 4 — ATS + hiring manager scan

Now act as both:
1. An **ATS filter** scanning for keyword density and formatting issues
2. A **hiring manager** reading 200 resumes in one sitting

Using the rewritten experience section from Step 3:

**Sections That Would Get Skipped**
List any bullets or section that are weak, vague, or would get skimmed past — and why.

**Rewrites to Stop the Scroll**
For each flagged section, provide a sharper version that earns attention. Lead with impact, be specific, cut filler.

---

## Step 5 — Final summary

Wrap up with:
- Revised match score after the rewrites (X/100)
- 2–3 sentences on the strongest angle to emphasize when applying to this specific role

---

## Step 6 — Create a tailored resume copy in Google Drive

### 1-page rule
The final resume **must fit on one page — use as much of that page as possible**. Target **380–450 words** of body content (excluding header and section labels). Every experience section must have **at least 3 bullets**.

**Bullet targets per section:**
- Meta: 5 bullets (trim to 4 only if still over limit after tightening wording)
- Razortooth: 3 bullets
- Strategio: 3 bullets

**If over 450 words:**
- First trim any bullet over 40 words — cut filler, preserve the metric
- Then remove the lowest-impact bullet from Meta only (never drop below 3 bullets per section)
- Use `deleteContentRange` — always delete from **highest index to lowest** to avoid index shifting

**If under 380 words:**
- Add back a previously trimmed bullet, prioritizing the most role-relevant one
- Use `insertText` to insert at the right position, then `createParagraphBullets` to apply list formatting
- Process insertions from **highest index to lowest** in the batchUpdate so earlier inserts don't shift subsequent positions

After applying all changes, verify word count by re-reading the doc. Report the final word count alongside the result link.

---

1. **Extract the company name** from the job description (e.g. "Zoox", "Sesame", "Microsoft").

2. **Copy the base Google Doc** using `mcp__claude_ai_Google_Drive__copy_file`:
   - `fileId`: `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk`
   - `parentId`: `10QqchL7fb18Hw3Gd5KLBHct96ijIb3rR`
   - `title`: `Joelchrist Abreu — Resume — {Company}`
   - Save the returned file ID as `COPY_DOC_ID`

3. **Apply the rewritten bullets to the copy** using the Docs API. For each bullet that changed between the original and the rewrite, issue a `replaceAllText` request:

```python
import warnings
warnings.filterwarnings("ignore")

from googleapiclient.discovery import build
from google.oauth2 import service_account

COPY_DOC_ID = "{COPY_DOC_ID}"  # from step 2
SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/documents"]
)
docs = build("docs", "v1", credentials=creds)

# List of (original_text, rewritten_text) pairs — only bullets that changed
replacements = [
    ("ORIGINAL BULLET TEXT", "REWRITTEN BULLET TEXT"),
    # ... one entry per changed bullet
]

requests = [
    {
        "replaceAllText": {
            "containsText": {"text": old, "matchCase": True},
            "replaceText": new
        }
    }
    for old, new in replacements
]

result = docs.documents().batchUpdate(
    documentId=COPY_DOC_ID,
    body={"requests": requests}
).execute()

for reply, (old, _) in zip(result.get("replies", []), replacements):
    count = reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
    status = "✅" if count > 0 else "⚠️  0 matches"
    print(f"{status} {old[:60]}...")
```

   **Important:** Only replace bullets that genuinely changed. Do not replace bullets that stayed the same — this preserves all original formatting, fonts, and styling in the copy.

   Share the service account with the new doc if needed — it inherits permissions from the copied doc automatically since it already has access to the base.

4. **Fix bold formatting** — after applying rewrites, run the following to enforce tasteful bolding. Rules:
   - **Bold**: name, section headers (`TECHNICAL SKILLS`, `WORK EXPERIENCE`, `EDUCATION`), skill category labels (`Proficient:`, `Exposure:`), company names only
   - **Not bold**: contact line, job titles, locations, dates, bullet text, education degree/school
   - Leave all other formatting untouched

```python
import warnings
warnings.filterwarnings("ignore")

from googleapiclient.discovery import build
from google.oauth2 import service_account

COPY_DOC_ID = "{COPY_DOC_ID}"
SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/documents"]
)
docs = build("docs", "v1", credentials=creds)
doc = docs.documents().get(documentId=DOC_ID).execute()

requests = []
for el in doc.get("body", {}).get("content", []):
    if "paragraph" not in el:
        continue
    para = el["paragraph"]
    for r in para.get("elements", []):
        tr = r.get("textRun", {})
        content = tr.get("content", "")
        is_bold = tr.get("textStyle", {}).get("bold", False)
        si = r.get("startIndex", 0)
        ei = r.get("endIndex", 0)

        # Remove bold from job title/location (starts with "|" in job header lines)
        if is_bold and content.strip().startswith("|") and "Software Engineer" in content:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": si, "endIndex": ei},
                    "textStyle": {"bold": False},
                    "fields": "bold"
                }
            })

        # Remove bold from education degree/school if bolded
        if is_bold and any(x in content for x in ["B.A.", "B.S.", "Bachelor", "Forensic", "Computer Science"]):
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": si, "endIndex": ei},
                    "textStyle": {"bold": False},
                    "fields": "bold"
                }
            })

if requests:
    docs.documents().batchUpdate(documentId=COPY_DOC_ID, body={"requests": requests}).execute()
    print(f"✅ Bold formatting fixed ({len(requests)} changes)")
else:
    print("✅ Bold formatting already clean")
```

5. **Verify word count and report the result:**

   Re-read the doc and count words. Then report:

   > 📄 **[Joelchrist Abreu — Resume — {Company}]({viewUrl})**
   > {word_count} words · All rewrites applied · Bold formatting cleaned up
