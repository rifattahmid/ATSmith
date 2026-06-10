# Project Context - ATSmith

Use this file to onboard a new AI assistant instance for debugging or feature work.
Paste it at the start of a chat, then describe the issue or task.

## Project Purpose

ATSmith is a local Windows-first job application generator. It takes a job posting URL, selects the right country/category templates, tailors marked resume sentences, fills marked cover letter blanks, converts documents to PDF, and saves a complete application folder.

It is not a full resume generator. The user owns the base documents. The LLM edits only marked areas.

## Runtime Flow

`apply.py` runs in a loop:

1. Prompt for job URL. Blank, `q`, `quit`, or `exit` ends the loop.
2. `scrape_job(url)` returns a data dict with title, company, country, intro, responsibilities, qualifications, description, and captured PDF bytes when available.
3. If `PROFILES` exists in `config.py`, country detection uses `locations.json`.
4. If country detection succeeds, the matching profile is selected silently.
5. If detection fails, `_select_profile()` shows a country selector. `DEFAULT_PROFILE` is used as the preselected fallback when configured and valid.
6. `clean_job_title()` normalizes the job title.
7. `classifier.classify_job()` scores the title and description against `keywords.json`.
8. The user confirms or edits title, company, and category.
9. `generate_application(data, category)` creates the output folder and documents.

Exceptions in one URL are printed and the loop continues to the next URL.

## Main Files

```text
ATSmith/
├── apply.py                # CLI loop, profile selection, final confirmation
├── apply.ps1               # PowerShell wrapper using venv Python
├── scraper.py              # Playwright scraper, bot fallback, job extraction
├── classifier.py           # Category keyword loading and job classification
├── resume_context.py       # Resume source/extended loading and section selection
├── generator.py            # DOCX editing, PDF export, page fit, bundling
├── llm.py                  # Provider-neutral LLM helper with retry
├── constants.py            # Classifier constants and scraper timeouts
├── config.example.py       # Public config template
├── config.py               # User config, gitignored
├── keywords.example.json   # Public keyword-map example
├── keywords.json           # User keyword map, gitignored
├── locations.example.json  # Public country/location example
├── locations.json          # User country/location map, gitignored
├── README.md               # User setup guide
├── PROJECT_CONTEXT.md      # This technical handoff
└── tests/                  # Regression tests
```

Local/generated paths that should stay out of Git include `.env`, `.claude/`, `tmp/`, `.pytest_cache/`, `__pycache__/`, and `venv/`.

## Config Model

Single-country mode uses:

```python
OUTPUT_BASE = r"..."
TEMPLATE_BASE = r"..."
```

Multi-country mode uses:

```python
DEFAULT_PROFILE = "Malaysia"  # optional

PROFILES = {
    "Malaysia": {
        "OUTPUT_BASE": r"...",
        "TEMPLATE_BASE": r"...",
    },
    "United States": {
        "OUTPUT_BASE": r"...",
        "TEMPLATE_BASE": r"...",
    },
}
```

`locations.json` keys must match `PROFILES` keys. Keys starting with `_` are ignored.

Template-discovery config:

```python
RESUME_ORIGINAL_PDF_GLOB = "*_Resume.pdf"
RESUME_EDITABLE_DOCX_GLOB = "*_Resume_Edit.docx"
COVER_LETTER_DOCX_GLOB = "*Cover Letter.docx"
```

LLM config:

```python
LLM_PROVIDER = "anthropic"          # "anthropic", "openai", or "openai-compatible"
LLM_MODEL = None                    # required for openai-compatible
LLM_BASE_URL = None                 # required only for openai-compatible
```

Output naming config:

```python
RESUME_TAILORED_PDF_NAME = "{resume_stem_clean}.pdf"
COVER_LETTER_PDF_NAME = "{cover_stem_clean}.pdf"
```

Page-fit config:

```python
RESUME_PAGE_LIMIT = 1
COVER_LETTER_PAGE_LIMIT = 1
PAGE_FIT_MAX_ATTEMPTS = 2
PAGE_FIT_MAX_LINES_PER_ATTEMPT = 4
PAGE_FIT_MIN_LINE_RETAIN_RATIO = 0.88
```

Resume tailoring config:

```python
RESUME_SOURCE_FILENAME = "resume.source.md"
RESUME_SOURCE = "resume.source.md"
RESUME_EXTENDED_FILENAME = "resume.extended.md"
RESUME_EXTENDED_SOURCE = "resume.extended.md"
RESUME_TAILORING_AGGRESSION = "balanced"
RESUME_EXTENDED_SELECTION_ENABLED = True
RESUME_EXTENDED_MAX_SECTIONS = 8
RESUME_EXTENDED_MAX_CHARS = 12000
RESUME_EXTENDED_MIN_SCORE = 2
CLI_VERBOSITY = "normal"
```

## Template Structure

The selected `TEMPLATE_BASE` contains category folders. In a multi-country setup, each country profile usually points directly at that country's template root.

```text
TEMPLATE_BASE/
├── resume.source.md              # optional country-wide facts
├── resume.extended.md            # optional country-wide mappings
├── Finance/
│   ├── Name_Resume.docx          # original clean DOCX, not edited
│   ├── Name_Resume.pdf           # original static PDF copied first
│   ├── Name_Resume_Edit.docx     # editable resume template
│   ├── Name_Cover Letter.docx
│   ├── resume.source.md          # optional category facts
│   └── resume.extended.md        # optional category mappings
└── Investment/
    └── ...
```

Subfolder names must match keys in `keywords.json`.

## Classification

`classifier.py` loads `keywords.json`. Category keys are lowercased internally. Title matches receive `TITLE_MULTIPLIER` weight. Description matches receive base weight.

`_broad_categories` lists general categories. If a broad category wins with no title signal and a specialist category has description signal above `SPECIALIST_THRESHOLD`, the specialist category can win.

`generator.py` keeps a compatibility `classify_job()` wrapper, but new code should import from `classifier.py`.

## Resume Tailoring

Resume editing happens in `fill_resume_markers()`.

Supported marker:

```text
[A full sentence that may be edited.]
```

Ignored markers:

```text
Sentence with inline [FILL].
[RESUME_BULLET: Sentence.]
```

Only full-sentence bracket markers are sent to the configured LLM. The model must return either:

```text
1. EDIT | priority=<high|medium|low> | keyword=<keyword phrase> | sentence=<full revised sentence>
```

or:

```text
1. SKIP | reason=<short reason>
```

Normal CLI output shows counts and the per-marker keyword phrases added. Debug output also prints full edited sentences and skipped reasons.

If `return_edit_records=True`, `fill_resume_markers()` returns `(changed_count, edit_records)`. If no markers exist, it returns `(0, [])`. Old callers still receive `0`.

## Resume Context

`resume.source.md` is the factual source of truth. It should include only facts that can be directly claimed.

`resume.extended.md` is optional. It contains user-approved transferable mappings and defensible adjacent phrasing. Large extended files are parsed into sections and only the most relevant sections are sent to the resume prompt by default.

Search order for each file:

1. Category folder: `TEMPLATE_BASE/<Category>/<filename>`
2. Country/template folder: `TEMPLATE_BASE/<filename>`
3. Project fallback: configured relative file in the ATSmith project folder, usually `resume.source.md` or `resume.extended.md`

The old root `profile.resume.md` fallback is obsolete.

`resume_context.py` handles section parsing and selection. It keeps Purpose/Rules style global guidance, excludes the `Reference Section Format` authoring block, scores `###` sections against the job text plus marked resume sentences, and returns a capped selected context block.

## Resume Page Fit

`fit_resume_docx_to_page_limit()` converts the tailored resume DOCX to PDF and checks page count.

If the PDF exceeds `RESUME_PAGE_LIMIT`, it reverts accepted resume edits one by one:

1. Low priority first
2. Medium priority next
3. High priority last

After each revert it regenerates the PDF. If it fits, the fitted PDF remains. If it still does not fit after all edits are reverted, it prints a warning and leaves the latest PDF.

The resume path does not use generic line-shortening.

## Cover Letter Filling

`fill_cover_letter()` supports two marker types:

- `_`: short fill for company, role, or phrase-level content.
- `[DESCRIPTION]`: guided fill where the bracket text describes the desired sentence.

Only sentences containing a marker are sent to the configured LLM. Other cover-letter text stays untouched.

Date formatting uses `10 June 2026` style. The prompt asks the model not to use em dashes or en dashes.

Cover letter filled sentences are always printed because they are useful for review.

## Cover Letter Page Fit

`fit_docx_to_page_limit()` is the generic DOCX page-fit function currently used for cover letters.

If the rendered PDF exceeds `COVER_LETTER_PAGE_LIMIT`, it asks the configured LLM to micro-shorten a small set of long lines. Rewrites are rejected if they cut below `PAGE_FIT_MIN_LINE_RETAIN_RATIO`.

This generic shortener is not the resume fitting strategy.

## PDF Conversion And Bundles

`convert_docx_to_pdf()` uses Word COM automation through `pywin32` when available. It falls back to `docx2pdf.convert()`.

`_merge_cover_letter_bundle()` appends configured PDFs from `BUNDLE_APPENDIX` after the cover letter and writes `BUNDLE_NAME.pdf`.

Current behavior: PDF conversion failures print warnings and generation may continue, but the final status changes to `Done with warnings!` and lists the PDF issue instead of printing a clean success message.

## Scraper Notes

`scrape_job(url)` runs headless Edge and captures raw page text. It also captures a position description PDF while the browser session is open.

Bot-block detection triggers a clipboard fallback:

1. User opens the job page manually.
2. User copies page text.
3. User returns to terminal and presses Enter.
4. The tool reads clipboard text through `pyperclip`.

The configured LLM extracts structured JSON from the scraped or copied text. If the first response is invalid JSON, the scraper asks the LLM to repair the JSON once. If repair still fails, generation stops with a clear `Could not parse job posting JSON` error instead of producing weak documents with empty fields.

## LLM Notes

`llm.py` exposes `call_llm()` and keeps `call_claude()` as a backward-compatible alias.

Supported providers:

- `anthropic`: uses the Anthropic SDK, `ANTHROPIC_API_KEY`, and the Anthropic Messages API.
- `openai`: uses the OpenAI SDK, `OPENAI_API_KEY`, and the OpenAI Responses API.
- `openai-compatible`: uses the OpenAI SDK with `LLM_API_KEY` and `LLM_BASE_URL`.

Built-in defaults:

- Anthropic: `claude-haiku-4-5-20251001`
- OpenAI: `gpt-5.2`

`LLM_MODEL` overrides the provider default. It is required for `openai-compatible` because custom endpoints usually use provider-specific model names. Retry handling is shared across providers for retryable status codes plus transient timeout/connection errors.

## Testing Notes

Important regression areas:

- Country detection and `DEFAULT_PROFILE`
- Resume marker parsing
- No-marker resume behavior
- Resume edit-record return shape
- Resume page-fit rollback
- Cover-letter page-fit shortening
- Template glob selection
- Output PDF naming

Use pytest from the project venv:

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

If Windows temp/cache permissions interfere, disable pytest cache or use an approved elevated run. Do not run the app itself during read-only audits.

## GitHub

```text
https://github.com/rifattahmid/ApplyKit
```
