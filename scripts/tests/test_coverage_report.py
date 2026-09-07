import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import coverage_report  # noqa: E402


def record(fields, hits):
    metadata = "".join(
        coverage_report.FIELD_SEPARATOR + key + coverage_report.KEY_VALUE_SEPARATOR + value
        for key, value in fields
    )
    return "C '{}' {}".format(metadata, hits)


def coverage_file(*records):
    return (coverage_report.FORMAT_HEADER + "\n" + "\n".join(records) + "\n").encode("utf-8")


BASE = (
    ("f", "hw/rtl/alpha/alpha.sv"),
    ("l", "12"),
    ("n", "7"),
    ("t", "line"),
    ("page", "v_line/alpha"),
    ("o", "then"),
    ("h", "top.u_alpha"),
)


class CoverageReportTests(unittest.TestCase):
    def test_counts_each_kind_and_lists_zero_points(self):
        points_data = [
            record(BASE, 0),
            record(tuple((key, "branch" if key == "t" else value) for key, value in BASE), 4),
            record(
                tuple(
                    (key, "expr" if key == "t" else ("8" if key == "n" else value))
                    for key, value in BASE
                ),
                1,
            ),
            record(
                tuple(
                    (key, "toggle" if key == "t" else ("9" if key == "n" else value))
                    for key, value in BASE
                ),
                0,
            ),
        ]
        data = coverage_file(*reversed(points_data))
        report = coverage_report.build_report(data, coverage_report.parse_coverage(data))

        self.assertFalse(report["coverage_closure"])
        self.assertEqual(report["coverage_gate"], "not_evaluated")
        self.assertEqual(report["input"]["record_count"], 4)
        self.assertEqual(report["input"]["uncovered_point_count"], 2)
        self.assertEqual(sum(bucket["total"] for bucket in report["kinds"].values()), 4)
        self.assertEqual(report["kinds"]["line"], {"hit": 0, "total": 1, "percent": 0.0})
        self.assertEqual(report["kinds"]["branch"], {"hit": 1, "total": 1, "percent": 100.0})
        self.assertEqual([point["kind"] for point in report["uncovered_points"]], ["line", "toggle"])
        self.assertEqual(report["sources"][0]["module_hierarchies"][0]["hierarchy"], "top.u_alpha")

    def test_absent_kind_has_null_percent_and_zero_denominator(self):
        data = coverage_file(record(BASE, 2))
        report = coverage_report.build_report(data, coverage_report.parse_coverage(data))
        self.assertEqual(report["kinds"]["toggle"], {"hit": 0, "total": 0, "percent": None})

    def test_preserves_escaped_metadata_and_apostrophe(self):
        fields = tuple(
            (key, "owner's signal with spaces" if key == "o" else value) for key, value in BASE
        ) + (("S", r"escaped\x01text\x02more"),)
        data = coverage_file(record(fields, 0))
        point = coverage_report.parse_coverage(data)[0]
        self.assertEqual(point.metadata["S"], r"escaped\x01text\x02more")
        self.assertEqual(point.metadata["o"], "owner's signal with spaces")

    def test_rejects_missing_file_field(self):
        data = coverage_file(record(tuple(item for item in BASE if item[0] != "f"), 1))
        with self.assertRaisesRegex(coverage_report.CoverageFormatError, "missing required.*'f'"):
            coverage_report.parse_coverage(data)

    def test_rejects_missing_type_field(self):
        data = coverage_file(record(tuple(item for item in BASE if item[0] != "t"), 1))
        with self.assertRaisesRegex(coverage_report.CoverageFormatError, "missing required.*'t'"):
            coverage_report.parse_coverage(data)

    def test_rejects_unknown_type_instead_of_dropping_it(self):
        fields = tuple((key, "fsm_arc" if key == "t" else value) for key, value in BASE)
        with self.assertRaisesRegex(coverage_report.CoverageFormatError, "unsupported coverage kind"):
            coverage_report.parse_coverage(coverage_file(record(fields, 1)))

    def test_rejects_duplicate_points_even_if_field_order_differs(self):
        data = coverage_file(record(BASE, 1), record(tuple(reversed(BASE)), 0))
        with self.assertRaisesRegex(coverage_report.CoverageFormatError, "duplicate coverage point"):
            coverage_report.parse_coverage(data)

    def test_rejects_duplicate_metadata_key(self):
        with self.assertRaisesRegex(coverage_report.CoverageFormatError, "duplicate metadata key"):
            coverage_report.parse_coverage(coverage_file(record(BASE + (("t", "line"),), 1)))

    def test_rejects_non_ascii_numeric_metadata_for_hit_and_uncovered_points(self):
        for key in ("l", "n"):
            for hits in (0, 1):
                fields = tuple(
                    (field, "²" if field == key else value) for field, value in BASE
                )
                with self.subTest(key=key, hits=hits):
                    with self.assertRaisesRegex(
                        coverage_report.CoverageFormatError,
                        "must be a non-negative integer",
                    ):
                        coverage_report.parse_coverage(coverage_file(record(fields, hits)))

    def test_rejects_empty_header_only_and_malformed_inputs(self):
        invalid = (
            b"",
            (coverage_report.FORMAT_HEADER + "\n").encode("utf-8"),
            b"# SystemC::Coverage-2\n",
            (coverage_report.FORMAT_HEADER + "\nnot-a-record\n").encode("utf-8"),
        )
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(coverage_report.CoverageFormatError):
                    coverage_report.parse_coverage(data)

    def test_cli_rejects_missing_input_and_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_stderr = io.StringIO()
            with contextlib.redirect_stderr(missing_stderr):
                self.assertEqual(coverage_report.main([str(root / "missing.dat")]), 2)
            self.assertIn("No such file", missing_stderr.getvalue())

            source = root / "coverage.dat"
            output = root / "report.json"
            source.write_bytes(coverage_file(record(BASE, 0)))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    coverage_report.main([str(source), "--output", str(output)]),
                    0,
                )
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(parsed["coverage_closure"])
            self.assertIn("diagnostic only", stdout.getvalue())

    def test_cli_refuses_to_overwrite_input_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "coverage.dat"
            original = coverage_file(record(BASE, 0))
            source.write_bytes(original)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    coverage_report.main([str(source), "--output", str(source)]),
                    2,
                )
            self.assertEqual(source.read_bytes(), original)
            self.assertIn("refusing to overwrite evidence", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
