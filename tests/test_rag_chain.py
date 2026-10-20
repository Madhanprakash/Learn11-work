import unittest

from rag_chain import _mentioned_source_urls


class NamedSchemeRetrievalTests(unittest.TestCase):
    def test_matches_exact_scheme_titles_in_question_and_history(self):
        sources = [
            {"title": "Training to Farmers", "url": "https://example.gov/training"},
            {"title": "Generator subsidy", "url": "https://example.gov/generator"},
        ]
        self.assertEqual(
            _mentioned_source_urls(
                "For the Training to Farmers scheme, what are the benefits?", sources
            ),
            ["https://example.gov/training"],
        )

    def test_returns_no_match_when_no_indexed_title_is_named(self):
        self.assertEqual(
            _mentioned_source_urls("What schemes are available for farmers?", [
                {"title": "Training to Farmers", "url": "https://example.gov/training"},
            ]),
            [],
        )


if __name__ == "__main__":
    unittest.main()
