#!/usr/bin/env python3
"""Produce a deterministic diagnostic census from one Verilator Coverage-3 file."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


FORMAT_HEADER = "# SystemC::Coverage-3"
REPORT_SCHEMA = "openchip.verilator-coverage-diagnostic.v1"
KNOWN_KINDS = ("branch", "expr", "line", "toggle")
FIELD_SEPARATOR = "\x01"
KEY_VALUE_SEPARATOR = "\x02"
RECORD_RE = re.compile(r"^C '(.*)' ([0-9]+)$")
REQUIRED_FIELDS = ("f", "h", "l", "n", "t")


class CoverageFormatError(ValueError):
    """Raised when an input cannot be counted without changing its denominator."""


@dataclass(frozen=True)
class CoveragePoint:
    metadata: Mapping[str, str]
    hits: int
    input_line: int

    @property
    def source(self) -> str:
        return self.metadata["f"]

    @property
    def hierarchy(self) -> str:
        return self.metadata["h"]

    @property
    def kind(self) -> str:
        return self.metadata["t"]


def _error(input_line: int, message: str) -> CoverageFormatError:
    return CoverageFormatError("line {}: {}".format(input_line, message))


def _parse_metadata(encoded: str, input_line: int) -> Dict[str, str]:
    if not encoded.startswith(FIELD_SEPARATOR):
        raise _error(input_line, "metadata does not begin with the field separator")

    fields: Dict[str, str] = {}
    chunks = encoded.split(FIELD_SEPARATOR)
    if chunks[0] != "":
        raise _error(input_line, "malformed metadata prefix")

    for chunk in chunks[1:]:
        if not chunk:
            raise _error(input_line, "empty metadata field")
        if chunk.count(KEY_VALUE_SEPARATOR) != 1:
            raise _error(input_line, "metadata field must contain exactly one key/value separator")
        key, value = chunk.split(KEY_VALUE_SEPARATOR, 1)
        if not key:
            raise _error(input_line, "empty metadata key")
        if key in fields:
            raise _error(input_line, "duplicate metadata key {!r}".format(key))
        fields[key] = value

    for key in REQUIRED_FIELDS:
        if key not in fields or fields[key] == "":
            raise _error(input_line, "missing required metadata field {!r}".format(key))
    if fields["t"] not in KNOWN_KINDS:
        raise _error(input_line, "unsupported coverage kind {!r}".format(fields["t"]))
    for key in ("l", "n"):
        if re.fullmatch(r"[0-9]+", fields[key]) is None:
            raise _error(input_line, "metadata field {!r} must be a non-negative integer".format(key))

    return fields


def parse_coverage(data: bytes) -> List[CoveragePoint]:
    """Parse one complete Coverage-3 byte stream, rejecting ambiguous input."""
    if not data:
        raise CoverageFormatError("input is empty")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoverageFormatError("input is not valid UTF-8: {}".format(exc)) from exc

    lines = text.splitlines()
    if not lines or lines[0] != FORMAT_HEADER:
        raise CoverageFormatError("expected exact Coverage-3 header {!r}".format(FORMAT_HEADER))

    points: List[CoveragePoint] = []
    seen: Dict[Tuple[Tuple[str, str], ...], int] = {}
    for input_line, line in enumerate(lines[1:], 2):
        match = RECORD_RE.fullmatch(line)
        if match is None:
            raise _error(input_line, "malformed or unsupported record")
        metadata = _parse_metadata(match.group(1), input_line)
        identity = tuple(sorted(metadata.items()))
        if identity in seen:
            raise _error(
                input_line,
                "duplicate coverage point (first seen at line {})".format(seen[identity]),
            )
        seen[identity] = input_line
        points.append(CoveragePoint(metadata=metadata, hits=int(match.group(2)), input_line=input_line))

    if not points:
        raise CoverageFormatError("input contains no coverage records")
    return points


def _empty_counts() -> MutableMapping[str, List[int]]:
    return defaultdict(lambda: [0, 0])


def _add(counts: MutableMapping[str, List[int]], point: CoveragePoint) -> None:
    bucket = counts[point.kind]
    bucket[0] += int(point.hits > 0)
    bucket[1] += 1


def _summarize(counts: Mapping[str, Sequence[int]]) -> Dict[str, Mapping[str, object]]:
    result: Dict[str, Mapping[str, object]] = {}
    for kind in KNOWN_KINDS:
        hit, total = counts.get(kind, (0, 0))
        percent: Optional[float]
        if total:
            percent = round(100.0 * hit / total, 4)
        else:
            percent = None
        result[kind] = {"hit": hit, "total": total, "percent": percent}
    return result


def _point_sort_key(point: CoveragePoint) -> Tuple[object, ...]:
    return (
        point.source,
        point.hierarchy,
        KNOWN_KINDS.index(point.kind),
        int(point.metadata["l"]),
        int(point.metadata["n"]),
        tuple(sorted(point.metadata.items())),
    )


def build_report(data: bytes, points: Iterable[CoveragePoint]) -> Mapping[str, object]:
    """Aggregate raw point counts without applying exclusions or gate thresholds."""
    point_list = list(points)
    overall = _empty_counts()
    by_source: MutableMapping[str, MutableMapping[str, List[int]]] = defaultdict(_empty_counts)
    by_scope: MutableMapping[Tuple[str, str], MutableMapping[str, List[int]]] = defaultdict(
        _empty_counts
    )

    for point in point_list:
        _add(overall, point)
        _add(by_source[point.source], point)
        _add(by_scope[(point.source, point.hierarchy)], point)

    sources = []
    for source in sorted(by_source):
        module_hierarchies = [
            {"hierarchy": hierarchy, "kinds": _summarize(by_scope[(source, hierarchy)])}
            for scope_source, hierarchy in sorted(by_scope)
            if scope_source == source
        ]
        sources.append(
            {
                "source": source,
                "kinds": _summarize(by_source[source]),
                "module_hierarchies": module_hierarchies,
            }
        )

    uncovered_points = []
    for point in sorted((item for item in point_list if item.hits == 0), key=_point_sort_key):
        uncovered_points.append(
            {
                "source": point.source,
                "hierarchy": point.hierarchy,
                "kind": point.kind,
                "line": int(point.metadata["l"]),
                "column": int(point.metadata["n"]),
                "hits": point.hits,
                "metadata": dict(sorted(point.metadata.items())),
            }
        )

    return {
        "schema": REPORT_SCHEMA,
        "coverage_closure": False,
        "coverage_gate": "not_evaluated",
        "input": {
            "sha256": hashlib.sha256(data).hexdigest(),
            "format": "SystemC::Coverage-3",
            "producer_version": "not encoded in input",
            "record_count": len(point_list),
            "source_count": len(by_source),
            "source_module_hierarchy_count": len(by_scope),
            "uncovered_point_count": len(uncovered_points),
        },
        "metric": (
            "Verilator instrumented points by t field; a point is hit when its counter is greater "
            "than zero; this is not physical source-line coverage"
        ),
        "kinds": _summarize(overall),
        "sources": sources,
        "uncovered_points": uncovered_points,
    }


def write_report(report: Mapping[str, object], output: Optional[Path]) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    output.write_text(rendered, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report raw diagnostic points from one Verilator Coverage-3 file."
    )
    parser.add_argument("coverage_data", type=Path, help="single existing coverage.dat input")
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.output is not None:
            try:
                same_file = args.coverage_data.samefile(args.output)
            except FileNotFoundError:
                same_file = args.coverage_data.resolve() == args.output.resolve()
            if same_file:
                raise CoverageFormatError("output resolves to the coverage input; refusing to overwrite evidence")
        data = args.coverage_data.read_bytes()
        points = parse_coverage(data)
        report = build_report(data, points)
        write_report(report, args.output)
    except (OSError, CoverageFormatError) as exc:
        print("coverage-report: error: {}".format(exc), file=sys.stderr)
        return 2

    if args.output is not None:
        print(
            "coverage-report: wrote {} ({} points, {} uncovered); diagnostic only; "
            "coverage_closure=false".format(
                args.output,
                report["input"]["record_count"],
                report["input"]["uncovered_point_count"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
