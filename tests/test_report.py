import unittest

from odx_service_gate.core import compare, demo_paths
from odx_service_gate.report import render


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        before, after = demo_paths()
        cls.report = compare([before], [after])

    def test_json(self):
        self.assertIn('"changes"', render(self.report, "json"))

    def test_markdown(self):
        self.assertIn("ODX service gate report", render(self.report, "markdown"))

    def test_html(self):
        self.assertIn("<table>", render(self.report, "html"))

    def test_junit(self):
        self.assertIn("<testsuite", render(self.report, "junit"))

    def test_sarif(self):
        self.assertIn('"version": "2.1.0"', render(self.report, "sarif"))


if __name__ == "__main__":
    unittest.main()
