import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

from scraper import SiteClient, _extract_page, _relevant_links, _section_value


class ScraperExtractionTests(unittest.TestCase):
    def test_extracts_labeled_scheme_details_without_crossing_fields(self):
        html = b"""<html><head><title>Government of Tamil Nadu</title></head><body>
        <main><h1>Training to Farmers</h1>
        Concerned Department: Agriculture - Farmers Welfare Department
        Concerned District: All districts
        Types of Benefits: Grants
        State Funding Pattern: Rs.300 per farmer for 2 days.
        Eligibility criteria: Small farmers
        How To avail: Apply at the village agricultural office
        Validity of the Scheme: Ongoing
        Description: Maize growing farmers are eligible.
        </main></body></html>"""
        response = SimpleNamespace(
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=html,
        )

        document = _extract_page(response, "https://www.tn.gov.in/scheme_details.php?id=1")

        self.assertEqual(document.title, "Training to Farmers")
        self.assertEqual(document.department, "Agriculture - Farmers Welfare Department")
        self.assertEqual(document.benefits, "Grants; Funding pattern: Rs.300 per farmer for 2 days.")
        self.assertEqual(document.eligibility, "Small farmers")
        self.assertEqual(document.application_instructions, "Apply at the village agricultural office")
        self.assertEqual(document.description, "Maize growing farmers are eligible.")
        self.assertIsNone(document.required_documents)

    def test_discovers_only_relevant_official_detail_links(self):
        html = """<main>
        <a href="/scheme_details.php?id=1">Training to Farmers</a>
        <a href="https://example.com/scheme">Other scheme</a>
        <a href="/about">About</a>
        </main>"""
        links = _relevant_links(BeautifulSoup(html, "html.parser"),
                                "https://www.tn.gov.in/scheme_list.php?dep_id=Mg==")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], "https://www.tn.gov.in/scheme_details.php?id=1")

    def test_section_extraction_returns_none_for_missing_labels(self):
        self.assertIsNone(_section_value("This page has no labeled detail.",
                                         ("required documents",)))

    def test_fetch_refuses_redirects_off_the_official_domain(self):
        client = SiteClient(timeout=1, delay=0)
        redirect = SimpleNamespace(
            is_redirect=True,
            headers={"Location": "https://example.com/"},
            status_code=302,
        )
        with patch.object(client, "can_fetch",
                          side_effect=lambda url: url.startswith("https://www.tn.gov.in/")), \
             patch.object(client, "_request", return_value=redirect):
            with self.assertRaises(PermissionError):
                client.fetch("https://www.tn.gov.in/scheme_details.php?id=1")


if __name__ == "__main__":
    unittest.main()
