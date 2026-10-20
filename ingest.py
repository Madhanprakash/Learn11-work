"""Clean scraped scheme pages, split them, and persist a FAISS index."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

from scraper import DATA_DIR

RAW_PATH = DATA_DIR / "raw_documents.jsonl"
INDEX_DIR = DATA_DIR / "faiss_index"
LOG = logging.getLogger(__name__)

TEXT_FIELDS = (
    "eligibility", "benefits", "required_documents", "application_instructions",
)


def load_and_split_documents() -> list[Document]:
    if not RAW_PATH.is_file():
        raise FileNotFoundError(f"Scraped data not found at {RAW_PATH}; run scraper.py first")

    documents: list[Document] = []
    with RAW_PATH.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {RAW_PATH}") from exc

            content = str(record.get("content") or "").strip()
            if not content:
                LOG.warning("Skipping document without readable content on line %d", line_number)
                continue
            field_text = [
                f"{name.replace('_', ' ').title()}: {record[name]}"
                for name in TEXT_FIELDS if record.get(name)
            ]
            if field_text:
                content = f"{content}\n\n" + "\n".join(field_text)
            metadata = {
                key: record[key]
                for key in ("title", "source_url", "retrieval_date", "department")
                if record.get(key) is not None
            }
            documents.append(Document(page_content=content, metadata=metadata))

    if not documents:
        raise ValueError(f"No readable documents were found in {RAW_PATH}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    if not chunks:
        raise ValueError("Document splitting produced no searchable chunks")
    return chunks


def build_index() -> None:
    load_dotenv()
    chunks = load_and_split_documents()
    embeddings = OpenAIEmbeddings()
    from langchain_community.vectorstores import FAISS

    vectorstore = FAISS.from_documents(chunks, embeddings)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(INDEX_DIR))
    print(f"Indexed {len(chunks)} chunks from {len({d.metadata['source_url'] for d in chunks})} documents")
    print(f"FAISS index saved to {INDEX_DIR}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    build_index()
