import os
import shutil
import tempfile
import unittest

from github_crawler.source_scan import SourcePropertyScanner, plan_property_query


class TestSourcePropertyScanner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "src"))
        with open(os.path.join(self.test_dir, "src", "auth.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "def issue_jwt(user):\n"
                "    token = sign_jwt(user)\n"
                "    return token\n"
            )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_plan_property_query_extracts_terms(self):
        plan = plan_property_query('Look for "sign_jwt" and /issue_.+/')

        self.assertIn("sign_jwt", plan["terms"])
        self.assertEqual(plan["regexes"][0]["pattern"], "issue_.+")

    def test_scanner_finds_matching_evidence(self):
        scanner = SourcePropertyScanner("owner/repo", self.test_dir)

        result = scanner.scan("Look for JWT auth")

        self.assertTrue(result["findings"])
        self.assertEqual(result["findings"][0]["file_path"], os.path.join("src", "auth.py"))
        self.assertIn("Found", result["summary"])


if __name__ == "__main__":
    unittest.main()
