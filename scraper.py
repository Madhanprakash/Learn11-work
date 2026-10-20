"""Collect readable scheme information from the Tamil Nadu government portal."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from dotenv import load_dotenv

SOURCE_URL = "https://www.tn.gov.in/scheme_list.php?dep_id=Mg=="
ALLOWED_HOST = "www.tn.gov.in"
DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_PATH = DATA_DIR / "raw_documents.jsonl"
USER_AGENT = "TamilNaduSchemeAssistant/1.0 (educational research; contact: site administrator)"
FIELD_LABELS = {
    "eligibility": ("eligibility criteria", "eligibility", "who can apply"),
    "benefits": ("types of benefits", "benefits", "benefit", "assistance", "incentive"),
    "required_documents": ("required documents", "documents required",
                           "documents to be submitted", "enclosures", "proof required"),
    "application_instructions": ("how to avail", "how to apply", "application procedure",
                                 "apply", "application process", "where to apply"),
}
SECTION_BOUNDARIES = (
    "concerned department", "concerned district", "organisation name", "scheme details",
    "scheme title/name", "associated scheme", "sponsered by", "sponsored by",
    "state funding pattern", "funding pattern", "beneficiaries", "types of benefits",
    "eligibility criteria", "income", "age from", "age to", "community", "how to avail",
    "how to apply", "the application is to be submitted to", "validity of the scheme",
    "validity of scheme", "introduced on", "description", "scheme type", "uploaded file",
    "required documents", "documents required", "documents to be submitted",
)
LOG = logging.getLogger(__name__)


@dataclass
class CollectedDocument:
    title: str
    source_url: str
    retrieval_date: str
    department: str | None
    description: str | None
    eligibility: str | None
    benefits: str | None
    required_documents: str | None
    application_instructions: str | None
    content: str


class SiteClient:
    def __init__(self, timeout: float, delay: float) -> None:
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request = 0.0
        self._robots: dict[str, RobotFileParser] = {}

    def _request(self, url: str) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            return False
        if parsed.hostname not in self._robots:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                response = self.session.get(
                    robots_url,
                    timeout=self.timeout,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=False,
                )
                self._last_request = time.monotonic()
            except requests.RequestException as exc:
                LOG.warning("Cannot check robots.txt for %s: %s", parsed.hostname, exc)
                return False
            if response.status_code == 404:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse([])
            elif response.ok:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
            else:
                LOG.warning("robots.txt returned HTTP %s; refusing to crawl %s",
                            response.status_code, parsed.hostname)
                return False
            self._robots[parsed.hostname] = parser
        return self._robots[parsed.hostname].can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> requests.Response:
        for _ in range(6):
            if not self.can_fetch(url):
                raise PermissionError(
                    f"robots.txt disallows or could not authorize fetching {url}"
                )
            response = self._request(url)
            if not response.is_redirect:
                return response
            location = response.headers.get("Location")
            if not location:
                raise requests.HTTPError("Redirect response did not include a Location header",
                                         response=response)
            url = urljoin(url, location)
        raise requests.TooManyRedirects(f"Too many redirects while fetching {url}")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _section_value(content: str, labels: tuple[str, ...],
                   boundaries: tuple[str, ...] = SECTION_BOUNDARIES) -> str | None:
    label_pattern = "|".join(
        re.escape(label) for label in sorted(labels, key=len, reverse=True)
    )
    match = re.search(rf"(?:^|(?<=\s))(?:{label_pattern})\s*[:\-]?\s*",
                      content, flags=re.IGNORECASE)
    if not match:
        return None
    following = content[match.end():]
    boundary_pattern = "|".join(
        re.escape(label) for label in sorted(boundaries, key=len, reverse=True)
    )
    next_label = re.search(
        rf"\b(?:{boundary_pattern})\b\s*[:/\-]?", following, flags=re.IGNORECASE
    )
    value = _clean_text(following[:next_label.start()] if next_label else following)
    value = value.strip(" :-|/")
    return value or None


def _main_content(soup: BeautifulSoup) -> Tag:
    for selector in ("main", "article", "#content", "#main-content", ".content"):
        selected = soup.select_one(selector)
        if isinstance(selected, Tag):
            return selected
    return soup.body or soup


def _extract_page(response: requests.Response, url: str) -> CollectedDocument:
    retrieval_date = date.today().isoformat()
    content_type = response.headers.get("Content-Type", "").lower()
    if "pdf" in content_type or urlparse(url).path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF encountered; install the declared pypdf dependency") from exc
        import io

        pdf = PdfReader(io.BytesIO(response.content))
        content = _clean_text("\n".join(page.extract_text() or "" for page in pdf.pages))
        title = Path(urlparse(url).path).name or "Government scheme document"
        return CollectedDocument(title, url, retrieval_date, None, None, None, None,
                                 None, None, content)

    soup = BeautifulSoup(response.content, "html.parser")
    main = _main_content(soup)
    for element in main.select("script, style, noscript, nav, footer, header, form"):
        element.decompose()
    content = _clean_text(main.get_text(" ", strip=True))
    title_tag = main.find(["h1", "h2"])
    title = _clean_text(title_tag.get_text(" ", strip=True)) if title_tag else ""
    if not title:
        title = _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else url
    if urlparse(url).path.endswith("scheme_list.php") and title == "Government of Tamil Nadu":
        title = "Tamil Nadu government scheme listing"

    department = _section_value(content, ("concerned department",))
    description = _section_value(content, ("description",))
    eligibility = _section_value(content, FIELD_LABELS["eligibility"])
    if not eligibility and description and re.search(
        r"\b(eligible|eligibility|preference|beneficiar(?:y|ies)|age|income)\b",
        description, flags=re.IGNORECASE,
    ):
        eligibility = description
    benefits = _section_value(content, FIELD_LABELS["benefits"])
    funding = _section_value(content, ("state funding pattern", "funding pattern"))
    if funding:
        benefits = f"{benefits}; Funding pattern: {funding}" if benefits else funding
    required_documents = _section_value(content, FIELD_LABELS["required_documents"])
    application_boundaries = (
        "validity of the scheme", "validity of scheme", "introduced on",
        "description", "scheme type", "uploaded file",
    )
    application = _section_value(
        content, FIELD_LABELS["application_instructions"], application_boundaries,
    )
    if not application:
        application = _section_value(
            content, ("the application is to be submitted to",), application_boundaries,
        )
        if application:
            application = "The application is to be submitted to: " + application

    if not description:
        description = content
        if title and description.startswith(title):
            description = description[len(title):].strip(" :-")
    return CollectedDocument(title, url, retrieval_date, department,
                             description or None, eligibility, benefits,
                             required_documents, application,
                             content)


def _relevant_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str, str | None]]:
    main = _main_content(soup)
    links: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for anchor in main.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        absolute = urldefrag(urljoin(page_url, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            continue
        if absolute in seen or absolute == page_url:
            continue
        seen.add(absolute)
        text = _clean_text(anchor.get_text(" ", strip=True))
        surrounding = (
            _clean_text(" ".join(
                str(node) for node in anchor.parent.find_all(string=True, recursive=False)
            ))
            if anchor.parent else ""
        )
        path = parsed.path.lower()
        is_pdf = path.endswith(".pdf")
        is_scheme_named = any(word in (text + " " + surrounding).casefold()
                              for word in ("scheme", "benefit", "eligibility", "assistance"))
        is_detail_path = any(word in path for word in ("scheme", "schemes", "benefit"))
        if is_pdf or is_scheme_named or is_detail_path:
            links.append((absolute, text or Path(path).name or absolute, surrounding or None))
    return links


def scrape(max_pages: int, timeout: float, delay: float) -> list[CollectedDocument]:
    client = SiteClient(timeout=timeout, delay=delay)
    listing_response = client.fetch(SOURCE_URL)
    listing_doc = _extract_page(listing_response, listing_response.url)
    listing_soup = BeautifulSoup(listing_response.content, "html.parser")
    documents = [listing_doc]
    seen_urls = {listing_response.url}
    links = _relevant_links(listing_soup, listing_response.url)
    if not links:
        LOG.warning("No relevant scheme links were found on the listing page")

    for url, title, context in links:
        if len(documents) >= max_pages:
            break
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            response = client.fetch(url)
            document = _extract_page(response, response.url)
        except (requests.RequestException, PermissionError, RuntimeError, ValueError) as exc:
            LOG.warning("Skipping %s: %s", url, exc)
            continue
        if not document.content:
            LOG.warning("Skipping empty page: %s", url)
            continue
        if document.title == url or len(document.content) < 80:
            LOG.warning("Page may require JavaScript or contain no readable content: %s", url)
        if document.title.lower() in ("government of tamil nadu", "home page"):
            document.title = title
        if context and not document.description:
            document.description = context
        documents.append(document)

    return documents


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(levelname)s: %(message)s")
    max_pages = int(os.getenv("CRAWL_MAX_PAGES", "25"))
    timeout = float(os.getenv("REQUEST_TIMEOUT", "20"))
    delay = float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
    if max_pages < 1 or timeout <= 0 or delay < 0:
        raise ValueError("CRAWL_MAX_PAGES and REQUEST_TIMEOUT must be positive; delay cannot be negative")

    documents = scrape(max_pages=max_pages, timeout=timeout, delay=delay)
    if not documents or not any(document.content for document in documents):
        raise RuntimeError("The official source did not yield any readable content")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as output:
        for document in documents:
            output.write(json.dumps(asdict(document), ensure_ascii=False) + "\n")
    print(f"Saved {len(documents)} readable documents to {OUTPUT_PATH}")
    for document in documents:
        print(f"- {document.title} | {document.source_url} | {len(document.content)} characters")


if __name__ == "__main__":
    main()
