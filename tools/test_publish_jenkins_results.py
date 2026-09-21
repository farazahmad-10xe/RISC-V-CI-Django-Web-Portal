import argparse
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.publish_jenkins_results import (
    build_payload,
    normalize_status,
    read_artifact_categories,
    read_xlsx_categories,
)


class PublisherTests(unittest.TestCase):
    def test_status_aliases(self):
        self.assertEqual(normalize_status("SUCCESS"), "PASS")
        self.assertEqual(normalize_status("not run"), "SKIPPED")
        self.assertEqual(normalize_status("unexpected"), "UNKNOWN")

    def test_merges_reference_and_hardware_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root = root / "state"
            run_root = root / "run"
            state_root.mkdir()
            run_root.mkdir()
            (state_root / "state.env").write_text(
                "RUN_ID=jenkins_weekly_7\nEXPECTED_CASES=2\nACT_REVISION=abc123\n"
            )
            (state_root / "sail_reference_status.tsv").write_text(
                "test_name\tsail_status\thardware_elf\nExceptionsM-01\tPASS\tyes\n"
            )
            (state_root / "spike_status.tsv").write_text("ExceptionsM-01\tPASS\n")
            (run_root / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "test_name": "ExceptionsM-01",
                            "status": "FAIL",
                            "root_cause": "Signature mismatch",
                            "report": "per_case/ExceptionsM-01/report.md",
                        }
                    ]
                )
            )
            args = argparse.Namespace(
                state_root=state_root,
                run_root=run_root,
                board_slug="vf2",
                board_name="VisionFive 2",
                core_profile="SiFive U74",
                job_name="vf2-privileged-weekly",
                build_number=7,
                build_url="https://jenkins/job/vf2-privileged-weekly/7/",
                status="AUTO",
                started_at="",
                finished_at="",
            )
            payload = build_payload(args)
        self.assertEqual(payload["status"], "RUNNING")
        self.assertEqual(payload["failed_cases"], 1)
        self.assertEqual(payload["results"][0]["sail_status"], "PASS")
        self.assertEqual(payload["results"][0]["spike_status"], "PASS")
        self.assertEqual(payload["results"][0]["hardware_status"], "FAIL")

    def test_reads_suite_membership_from_status_workbook(self):
        workbook_xml = """<?xml version="1.0"?>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="Privileged Tests" sheetId="1" r:id="rId1"/>
            <sheet name="Non-Privileged Tests" sheetId="2" r:id="rId2"/>
          </sheets>
        </workbook>"""
        relationships_xml = """<?xml version="1.0"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
          <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
        </Relationships>"""

        def sheet_xml(test_name):
            return f"""<?xml version="1.0"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="inlineStr"><is><t>Test Name</t></is></c></row>
                <row r="2"><c r="A2" t="inlineStr"><is><t>{test_name}</t></is></c></row>
              </sheetData>
            </worksheet>"""

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "matrix.xlsx")
            with ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook_xml)
                archive.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
                archive.writestr("xl/worksheets/sheet1.xml", sheet_xml("ExceptionsM-01"))
                archive.writestr("xl/worksheets/sheet2.xml", sheet_xml("I-add-01"))
            categories = read_xlsx_categories(path)

        self.assertEqual(categories["ExceptionsM-01"], "Privileged")
        self.assertEqual(categories["I-add-01"], "Non-Privileged")

    def test_reads_suite_membership_from_act_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = {
                "priv/ExceptionsM/ExceptionsM-01.sig.elf": "Privileged",
                "rv64i/I/I-add-01.sig.elf": "Non-Privileged",
                "rv64v/V/V-add-01.sig.elf": "Vector",
            }
            for relative_path in artifacts:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            categories = read_artifact_categories(root)

        self.assertEqual(
            categories,
            {
                "ExceptionsM-01": "Privileged",
                "I-add-01": "Non-Privileged",
                "V-add-01": "Vector",
            },
        )


if __name__ == "__main__":
    unittest.main()
