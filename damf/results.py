"""Test result parser and JUnit XML / JSON report exporter for DAMF."""

from __future__ import annotations

import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

from damf.models import TestCaseResult, TestSuiteResult


class ResultParser:
    """Processes raw test result files or TestSuiteResult objects and exports JUnit XML / JSON."""

    def __init__(self, result_file_path: str | Path = ".", report_output_path: str | Path | None = None):
        self.result_file_path = Path(result_file_path)
        self.output_location = Path(report_output_path) if report_output_path else self.result_file_path

    def parse_key_value_file(self, file_path: str | Path) -> dict[str, str]:
        """Parse lines formatted as `test_name: PASS|FAIL|SKIP`."""
        path = Path(file_path)
        results: dict[str, str] = {}
        if not path.exists():
            return results
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in raw_line:
                continue
            name, _, status = raw_line.partition(":")
            clean_status = status.strip().upper()
            if clean_status in ("PASS", "FAIL", "SKIP"):
                results[name.strip()] = clean_status
        return results

    def process_test_results(self) -> list[Path]:
        """Parse all `*_test_result` files in `result_file_path` and write JUnit XML reports."""
        if not self.result_file_path.exists():
            return []
        written: list[Path] = []
        for entry in sorted(os.listdir(self.result_file_path)):
            full = self.result_file_path / entry
            if not full.is_file() or entry.endswith(".xml") or entry.endswith(".json"):
                continue
            parsed = self.parse_key_value_file(full)
            if not parsed:
                continue
            suite_name = entry.replace("_test_result", "")
            xml_path = self.write_junit_xml(parsed, suite_name)
            written.append(xml_path)
        return written

    def write_junit_xml(
        self,
        test_results: dict[str, str] | TestSuiteResult,
        test_suite_name: str | None = None,
    ) -> Path:
        """Export test results in standard JUnit XML format."""
        self.output_location.mkdir(parents=True, exist_ok=True)
        if isinstance(test_results, TestSuiteResult):
            suite_name = test_suite_name or test_results.suite_name
            cases = test_results.cases
        else:
            suite_name = test_suite_name or "damf_suite"
            cases = [TestCaseResult(name=k, status=v.upper()) for k, v in test_results.items()]

        total = len(cases)
        failures = sum(1 for c in cases if c.status.upper() == "FAIL")
        skipped = sum(1 for c in cases if c.status.upper() == "SKIP")

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<testsuites>",
            f'  <testsuite name="{escape(suite_name)}" tests="{total}" failures="{failures}" skipped="{skipped}">',
        ]
        for case in cases:
            lines.append(f'    <testcase name="{escape(case.name)}" time="{case.duration_sec:.4f}">')
            status = case.status.upper()
            if status == "FAIL":
                msg_attr = f' message="{escape(case.message)}"' if case.message else ""
                lines.append(f"      <failure{msg_attr}/>")
            elif status == "SKIP":
                lines.append("      <skipped/>")
            lines.append("    </testcase>")
        lines.append("  </testsuite>")
        lines.append("</testsuites>")

        out_path = self.output_location / f"{suite_name}.xml"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path

    def write_json_report(self, suite: TestSuiteResult) -> Path:
        """Export a TestSuiteResult to a JSON file."""
        self.output_location.mkdir(parents=True, exist_ok=True)
        out_path = self.output_location / f"{suite.suite_name}.json"
        out_path.write_text(json.dumps(suite.to_dict(), indent=2) + "\n", encoding="utf-8")
        return out_path
