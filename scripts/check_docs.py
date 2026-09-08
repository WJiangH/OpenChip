#!/usr/bin/env python3
"""Check tracked public Markdown paths, placement and canonical skill mirrors.

This intentionally checks path existence, not Markdown anchors or remote URLs.
Imported/generated/private documentation follows its own rules. Add a narrowly
scoped engineering-report exception with its reason when preserving real evidence.
"""
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

EXCLUDED_PARTS = {"vendor", "third_party", "external", "generated", ".local-designs",
                  "_ci_artifacts", "node_modules"}
ENGINEERING_ROOTS = {"hw", "sw", "sim", "workloads", "explore"}
DOMAIN_NAMES = {"README.md", "SPEC.md", "TESTPLAN.md", "vplan.md", "BUGS.md",
                "SIGNOFF.md", "FORMAL.md", "CONSTRAINTS.md", "REGISTER_MAP.md",
                "IP.md", "LICENSE.md", "NOTICE.md", "SKILL.md"}
REPORT_EXCEPTIONS = {
    "explore/npu-dse/results.md": "Reproducible reference architecture exploration",
    "workloads/tinystories/profile.md": "Versioned reference workload measurements",
    "sw/reports/firmware-footprint.md": "Reproducible compiler/firmware footprint evidence",
}
LINK = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+['\"][^\n]*?['\"])?\s*\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", re.MULTILINE)


def excluded(name):
    path = PurePosixPath(name)
    return bool(set(path.parts) & EXCLUDED_PARTS) or name.startswith("hw/ip/")


def prose(text):
    """Ignore fenced examples, whose illustrative paths need not exist."""
    output, fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            output.append(line)
    return "\n".join(output)


def check(root, names):
    root = Path(root).resolve()
    names = set(names)
    errors, links, documents = [], 0, 0
    for name in sorted(names):
        if excluded(name):
            continue
        rel, path = PurePosixPath(name), root / name
        if rel.name == "AGENTS.md" and name != "AGENTS.md":
            errors.append(f"{name}: duplicate constitution; use root AGENTS.md")
        if rel.suffix != ".md" or path.is_symlink():
            continue
        if not path.is_file():
            errors.append(f"{name}: tracked document is missing (stage intended deletions)")
            continue
        documents += 1
        if rel.parts[0] in ENGINEERING_ROOTS and rel.name not in DOMAIN_NAMES and name not in REPORT_EXCEPTIONS:
            errors.append(f"{name}: use README.md or a reviewed domain/report exception")
        content = prose(path.read_text(encoding="utf-8"))
        targets = [m.group(1) for pattern in (LINK, REFERENCE) for m in pattern.finditer(content)]
        for target in targets:
            url = urlsplit(target.strip("<>"))
            if url.scheme or url.netloc or not url.path:
                continue
            links += 1
            destination = (root / unquote(url.path).lstrip("/") if url.path.startswith("/")
                           else path.parent / unquote(url.path))
            resolved = destination.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                errors.append(f"{name}: local link escapes repository: {target}")
                continue
            # A local untracked file cannot make a public link valid.
            present = relative in names or any(n.startswith(relative.rstrip("/") + "/") for n in names)
            if not destination.exists() or not present:
                errors.append(f"{name}: missing public link target: {target}")
    for name in sorted(names):
        rel = PurePosixPath(name)
        if len(rel.parts) != 4 or rel.parts[:2] != (".agents", "skills") or rel.name != "SKILL.md":
            continue
        role = rel.parts[2]
        for leaf in ("SKILL.md", "references"):
            canonical = root / ".agents/skills" / role / leaf
            mirror_name = f".claude/skills/{role}/{leaf}"
            mirror = root / mirror_name
            expected = f"../../../.agents/skills/{role}/{leaf}"
            if leaf == "references" and not any(n.startswith(f".agents/skills/{role}/references/") for n in names):
                if mirror_name in names:
                    errors.append(f"{mirror_name}: mirror has no tracked canonical references")
            elif mirror_name not in names or not mirror.is_symlink() or str(mirror.readlink()) != expected or not canonical.exists():
                errors.append(f"{mirror_name}: expected canonical symlink {expected}")
        agent_name = f".claude/agents/{role}.md"
        agent = root / agent_name
        if agent_name not in names or not agent.is_file() or name not in agent.read_text(encoding="utf-8"):
            errors.append(f"{agent_name}: missing canonical method entrypoint")
    return errors, documents, links


def main():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, stdout=subprocess.PIPE)
    names = [n for n in result.stdout.decode().split("\0") if n]
    errors, documents, links = check(root, names)
    for error in errors:
        print(error, file=sys.stderr)
    print(f"docs: {'FAIL' if errors else 'PASS'} ({documents} documents, {links} local links, {len(errors)} errors)")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
