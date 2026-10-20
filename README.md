# Tamil Nadu Government Schemes Assistant

A conversational retrieval-augmented chatbot that collects scheme information
from the Tamil Nadu government portal, indexes it with OpenAI embeddings and
FAISS, and answers questions with links to the official pages used as evidence.

The source is the
[Tamil Nadu government scheme listing](https://www.tn.gov.in/scheme_list.php?dep_id=Mg==).
The scraper follows relevant HTTPS links on `www.tn.gov.in`, checks
`robots.txt`, limits the number of pages, and waits between requests. It does
not use browser automation, bypass access controls, or authenticate. The
government site returned HTTP 404 for `/robots.txt` when this project was
tested; if that changes, its rules will be respected. HTML is parsed without
JavaScript execution. PDFs are supported when they are linked and contain
extractable text. Pages that need JavaScript and scanned PDFs may not yield
usable content.

Scraped information can be incomplete or outdated. Verify scheme requirements
and current details with the linked official sources. Never treat an answer as
an official determination.

## Requirements

- Python 3.12 (the source is written for Python 3.12; Python 3.13 can also be
  used for local development).
- An OpenAI API key with access to the configured chat and embedding models.
- Internet access to the government portal and OpenAI API.

## Setup (Windows PowerShell)

From this directory, create and activate a virtual environment. Use Python
3.12 if installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If Python 3.12 is not installed, Python 3.13 is supported for development:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install packages and configure the API key:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `OPENAI_API_KEY` in `.env`. The defaults are `gpt-4o-mini` and
`text-embedding-3-small`. The `.env` file is ignored by Git; never put an API
key in source code or commit it.

## Collect, index, and run

```powershell
python scraper.py
python ingest.py
streamlit run app.py
```

Open the local URL printed by Streamlit. Use the **Refresh official data and
rebuild index** button in the sidebar to scrape the source again and rebuild
the persistent FAISS index. A refresh requires a working API key because index
creation calls the embeddings API.

## Configuration

Copy and adjust these optional values in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Required OpenAI API key |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `CRAWL_MAX_PAGES` | `25` | Maximum pages, including the listing page |
| `REQUEST_TIMEOUT` | `20` | Per-request timeout in seconds |
| `REQUEST_DELAY_SECONDS` | `1.0` | Minimum pause between page requests |
| `RETRIEVAL_K` | `5` | Number of chunks retrieved for a question |

The scraper writes UTF-8 JSON Lines to `data/raw_documents.jsonl`. Ingestion
stores the FAISS index and its metadata under `data/faiss_index/`. Generated
data and indexes are git-ignored.

## Verification and limitations

The scraper was run successfully against the live source and collected 25
readable pages (the listing and 24 linked detail pages) in the test run. It
extracts available department, description, eligibility, benefit/funding, and
application information; required-document fields are retained when present.
Fields absent from a source remain empty rather than being invented. The
listing itself may include links to schemes from multiple departments, and the
crawl cap means this initial dataset is not comprehensive.

FAISS ingestion was tested with the configured OpenAI API and created a
persistent index of 77 chunks from 25 source pages. Live question answering
and a follow-up eligibility question were also tested; both returned the
matching scheme's official detail URL. Named scheme titles are matched against
the collected page metadata to avoid unrelated vector matches for explicit
scheme questions. Four scraper extraction/security tests and two named-scheme
retrieval tests pass.

Python 3.12 was not installed in the development environment; setup, scraping,
indexing, and tests used Python 3.13. English is the initial supported
interaction language. The retrieval and document metadata are designed so
Tamil support can be added later.
