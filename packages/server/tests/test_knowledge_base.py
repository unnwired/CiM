import json
import tempfile
import unittest
from pathlib import Path

from server import knowledge_base as kb


class KnowledgeBaseTests(unittest.TestCase):
    def test_default_document_has_all_pages(self):
        doc = kb.default_document()
        self.assertEqual(set(doc["pages"].keys()), set(kb.KB_PAGE_IDS))

    def test_put_and_get_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            payload = {
                "title": "Test Dashboard",
                "sections": [
                    {
                        "heading": "Intro",
                        "paragraphs": ["First paragraph.", "Second paragraph."],
                    }
                ],
            }
            saved = kb.put_page(data_dir, "dashboard", payload)
            self.assertEqual(saved["title"], "Test Dashboard")
            self.assertEqual(len(saved["sections"]), 1)
            loaded = kb.get_page(data_dir, "dashboard")
            self.assertEqual(loaded["title"], "Test Dashboard")
            self.assertEqual(loaded["sections"][0]["paragraphs"], ["First paragraph.", "Second paragraph."])

    def test_funds_page_has_its_own_content(self):
        self.assertIn("funds", kb.KB_PAGE_IDS)
        page = kb.default_page("funds")
        self.assertEqual(page["title"], "Funds")
        text = " ".join(p for s in page["sections"] for p in s["paragraphs"])
        self.assertIn("AMFI", text)
        self.assertNotIn("NSE Dashboard is Charts In Motion's primary stock screener", text)

    def test_unknown_guide_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                kb.get_page(Path(tmp), "not-a-page")

    def test_normalize_document_merges_missing_pages(self):
        raw = {
            "version": 1,
            "pages": {
                "dashboard": {
                    "title": "Only Dashboard",
                    "sections": [{"heading": "H", "paragraphs": ["P"]}],
                }
            },
        }
        doc = kb.normalize_document(raw)
        self.assertEqual(doc["pages"]["dashboard"]["title"], "Only Dashboard")
        self.assertIn("watchlist", doc["pages"])

    def test_save_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            kb.save_document(data_dir, kb.default_document())
            path = kb.kb_path(data_dir)
            self.assertTrue(path.is_file())
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            self.assertIn("pages", parsed)


if __name__ == "__main__":
    unittest.main()
