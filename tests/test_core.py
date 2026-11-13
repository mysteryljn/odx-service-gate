from pathlib import Path
import tempfile
import unittest
import zipfile

from odx_service_gate.core import OdxInputError, compare, snapshot


ROOT = Path(__file__).parents[1]
BEFORE = ROOT / "odx_service_gate" / "fixtures" / "before.odx"
AFTER = ROOT / "odx_service_gate" / "fixtures" / "after.odx"


class CoreTests(unittest.TestCase):
    def test_demo_reports_parameter_change_and_new_service(self):
        report = compare([BEFORE], [AFTER])
        codes = {item["code"] for item in report["changes"]}
        self.assertIn("parameter_changed", codes)
        self.assertIn("service_added", codes)
        self.assertFalse(report["passed"])

    def test_service_identity_includes_layer_and_name(self):
        report = compare([BEFORE], [BEFORE])
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["changes"], 0)

    def test_service_id_change_is_breaking(self):
        with tempfile.TemporaryDirectory() as folder:
            current = Path(folder) / "current.odx"
            text = BEFORE.read_text(encoding="utf-8").replace("0x22", "0x23")
            current.write_text(text, encoding="utf-8")
            report = compare([BEFORE], [current])
            self.assertTrue(any(item["code"] == "service_id_changed" for item in report["changes"]))

    def test_removed_parameter_is_breaking(self):
        with tempfile.TemporaryDirectory() as folder:
            current = Path(folder) / "current.odx"
            text = BEFORE.read_text(encoding="utf-8").replace('<PARAM><SHORT-NAME>DID</SHORT-NAME><BYTE-POSITION>0</BYTE-POSITION><BYTE-LENGTH>2</BYTE-LENGTH><DOP-REF ID-REF="DOP_DID"/></PARAM>', "")
            current.write_text(text, encoding="utf-8")
            report = compare([BEFORE], [current])
            self.assertTrue(any(item["code"] == "parameter_removed" for item in report["changes"]))

    def test_response_reference_change_is_breaking(self):
        with tempfile.TemporaryDirectory() as folder:
            current = Path(folder) / "current.odx"
            current.write_text(AFTER.read_text(encoding="utf-8").replace("resp.read.ok.v2", "resp.read.ok.v3"), encoding="utf-8")
            report = compare([AFTER], [current])
            self.assertTrue(any(item["code"] == "response_reference_changed" for item in report["changes"]))

    def test_pdx_members_are_read_without_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "data.pdx"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("nested/demo.odx", BEFORE.read_bytes())
            loaded = snapshot([archive])
            self.assertEqual(len(loaded["services"]), 1)
            self.assertIn("!nested/demo.odx", loaded["files"][0])

    def test_duplicate_service_is_error(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "one.odx"
            second = Path(folder) / "two.odx"
            first.write_bytes(BEFORE.read_bytes())
            second.write_bytes(BEFORE.read_bytes())
            report = compare([first, second], [first])
            self.assertTrue(any(item["code"] == "ambiguous_service" for item in report["changes"]))

    def test_unsupported_service_is_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unsupported.odx"
            path.write_text("<ODX><DIAG-SERVICE><SHORT-NAME>Broken</SHORT-NAME></DIAG-SERVICE></ODX>", encoding="utf-8")
            report = compare([path], [path])
            self.assertEqual(report["issues"][0]["code"], "unsupported_service")
            self.assertTrue(report["passed"])

    def test_invalid_xml_is_input_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.odx"
            path.write_text("<ODX>", encoding="utf-8")
            with self.assertRaises(OdxInputError):
                compare([path], [BEFORE])

    def test_any_policy_blocks_added_service(self):
        report = compare([BEFORE], [AFTER], "any")
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
