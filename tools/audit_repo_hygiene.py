from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPORT_VERSION = "1"
SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv310",
    ".venv311",
    ".venv311-codex",
    "__pycache__",
    "node_modules",
}
ARTIFACT_DIRS = ("artifacts", ".codex_artifacts", "tmp", "outputs", "dist", "exports")
GENERATED_MARKDOWN_REPORTS = {"docs/cleanup/repo_hygiene_report.md"}
ENTRY_DOC_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "docs/development/codex_task_template.md",
    "docs/development/ai_crm_next_architecture_skill.md",
    "skills/ai-crm-next-architecture/SKILL.md",
}
CANONICAL_ARCHITECTURE_PREFLIGHT = "docs/development/ai_crm_next_architecture_skill.md"
AICRM_MARKERS = (
    ("console", re.compile(r"(?<![\w.-])console\.(?:assert|debug|dir|error|group|groupEnd|info|log|table|time|timeEnd|trace|warn)\s*\(")),
    ("debug", re.compile(r"(?<![\w.-])debugger\b")),
    ("debug", re.compile(r"\bDEBUG\b")),
    ("print", re.compile(r"(?<![\w.])print\s*\(")),
    ("todo", re.compile(r"\bTODO\b")),
    ("fixme", re.compile(r"\bFIXME\b")),
    ("legacy", re.compile(r"\blegacy_flask\b")),
    ("legacy", re.compile(r"\bopenclaw_service\b")),
    ("legacy", re.compile(r"\bproduction_compat\b")),
    ("legacy", re.compile(r"\bforward_to_legacy_flask\b")),
)
TEXT_EXTENSIONS = {".css", ".html", ".js", ".json", ".md", ".py", ".ts", ".txt", ".yaml", ".yml"}
LINK_RE = re.compile(r"(?P<image>!)?\[[^\]]*]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
FULL_LINK_RE = re.compile(r"!?\[[^\]]*]\([^)]+\)")
PATH_RE = re.compile(
    r"(?<![\w:.])(?:\.{0,2}/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\."
    r"(?:css|html|json|js|md|py|sh|toml|txt|ya?ml)(?![A-Za-z0-9_.-])"
)
SENSITIVE_ENTRY_PATTERNS = (
    "crm-prod",
    "www.youcangogogo.com",
    "scripts/prod.sh",
    "/home/ubuntu/",
    "claude_crm_debug",
    "claude-debug.sh",
    "forced-command",
)
PRODUCTION_OPS_STUB_PATHS = ("scripts/prod.sh",)
PRODUCTION_OPS_DETAIL_PATTERNS = (
    "crm-prod",
    "SSH_HOST",
    "exec ssh",
    "psql-stdin",
    "prod.sh psql",
    "diagnose-p1-bridge",
    "forced-command",
    "claude-debug.sh",
)
STALE_LEGACY_FALLBACK_PATTERNS = (
    "legacy Flask 只作为显式 fallback",
    "Legacy Flask is only an explicit fallback",
    "wecom_ability_service/` 保留为 legacy fallback",
    "wecom_ability_service/` is retained as legacy fallback",
    "production compatibility facade",
    "生产兼容 facade",
)
ACTIVE_LEGACY_REFERENCE_PATTERNS = (
    (
        re.compile(r"https://github\.com/qianlan333/AI-CRM/blob/main/wecom_ability_service/"),
        "GitHub source link points at retired wecom_ability_service path.",
    ),
    (
        re.compile(r"`wecom_ability_service\.[^`]+`"),
        "Dotted implementation path points at retired wecom_ability_service module.",
    ),
    (
        re.compile(r"`wecom_ability_service/[^`]+`"),
        "File implementation path points at retired wecom_ability_service directory.",
    ),
    (
        re.compile(r"`openclaw_service/[^`]+`"),
        "File implementation path points at deleted openclaw_service directory.",
    ),
    (
        re.compile(r"`legacy_flask/openclaw_legacy/[^`]+`"),
        "File implementation path points at deleted legacy OpenClaw directory.",
    ),
)
ACTIVE_LEGACY_REFERENCE_ALLOWED_CONTEXT = (
    "Do not",
    "do not",
    "must not",
    "not current",
    "no longer",
    "not a current",
    "historical",
    "retired",
    "removed",
    "deleted",
    "closeout",
    "不得",
    "禁止",
    "已不在",
    "不是当前",
    "已物理删除",
    "不在当前",
)


@dataclass(frozen=True)
class RepoFinding:
    category: str
    severity: str
    path: str
    line: int | None
    message: str
    evidence: str

    def as_issue(self, issue_id: str) -> dict[str, object]:
        return {
            "id": issue_id,
            "category": self.category,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class HygieneReport:
    root: str
    scanned_markdown_files: list[str]
    issues: list[RepoFinding]
    generated_at: str

    @property
    def summary(self) -> dict[str, object]:
        by_category: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for issue in self.issues:
            by_category[issue.category] = by_category.get(issue.category, 0) + 1
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        return {
            "issue_count": len(self.issues),
            "markdown_files_scanned": len(self.scanned_markdown_files),
            "issues_by_category": dict(sorted(by_category.items())),
            "issues_by_severity": dict(sorted(by_severity.items())),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "version": REPORT_VERSION,
            "root": self.root,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "issues": [issue.as_issue(f"HYG-{index:04d}") for index, issue in enumerate(self.issues, start=1)],
        }


def audit_repository(root: Path = ROOT, *, generated_at: str | None = None) -> HygieneReport:
    root = root.resolve()
    markdown_files = _iter_markdown_files(root)
    issues: list[RepoFinding] = []
    issues.extend(_audit_markdown_references(root, markdown_files))
    issues.extend(_audit_tracked_artifacts(root))
    issues.extend(_audit_agent_entry_docs(root, markdown_files))
    issues.extend(_audit_production_ops_stubs(root))
    issues.extend(_audit_active_legacy_references(root, markdown_files))
    issues.extend(_audit_aicrm_markers(root))
    return HygieneReport(
        root=".",
        scanned_markdown_files=[_display_path(path, root) for path in markdown_files],
        issues=sorted(issues, key=lambda issue: (issue.category, issue.path, issue.line or 0, issue.message, issue.evidence)),
        generated_at=generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


def render_human_summary(report: HygieneReport) -> str:
    payload = report.as_dict()
    summary = payload["summary"]
    lines = [
        "# Repo Hygiene Audit",
        "",
        f"- Version: `{payload['version']}`",
        f"- Root: `{payload['root']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Markdown files scanned: {summary['markdown_files_scanned']}",
        f"- Issues: {summary['issue_count']}",
        "",
        "## Issue Summary",
        "",
    ]
    issues_by_category = summary["issues_by_category"]
    if issues_by_category:
        for category, count in issues_by_category.items():
            lines.append(f"- `{category}`: {count}")
    else:
        lines.append("- No issues.")
    lines.extend(["", "## Issues", ""])
    issues = payload["issues"]
    if issues:
        for issue in issues:
            location = issue["path"] if issue["line"] is None else f"{issue['path']}:{issue['line']}"
            lines.append(f"- **{issue['id']}** `{issue['category']}` `{issue['severity']}` `{location}` - {issue['message']}")
            if issue["evidence"]:
                lines.append(f"  - Evidence: {issue['evidence']}")
    else:
        lines.append("No issues.")
    lines.extend(
        [
            "",
            "## Suggested Cleanup Batches",
            "",
            "- Fix stale agent-entry references before changing runtime code.",
            "- Decide whether tracked artifact directories are evidence or generated output.",
            "- Replace active docs that still point contributors at retired legacy source paths.",
            "- Review debug/TODO/legacy markers in `aicrm_next/` before expanding lint gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report_files(
    report: HygieneReport,
    *,
    summary_output: Path | None = None,
    json_output: Path | None = None,
) -> None:
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(render_human_summary(report), encoding="utf-8")
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit repository hygiene without changing runtime behavior.")
    parser.add_argument("--root", default=str(ROOT), help="Repository root to scan.")
    parser.add_argument("--json-output", help="Optional path for the JSON report.")
    parser.add_argument("--summary-output", help="Optional path for the human-readable Markdown summary.")
    parser.add_argument("--markdown-output", help=argparse.SUPPRESS)
    parser.add_argument("--generated-at", help="Override generated_at for reproducible reports.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = audit_repository(root, generated_at=args.generated_at)
    summary_output = args.summary_output or args.markdown_output
    write_report_files(
        report,
        summary_output=(root / summary_output) if summary_output else None,
        json_output=(root / args.json_output) if args.json_output else None,
    )
    print(render_human_summary(report))
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


def _iter_markdown_files(root: Path) -> list[Path]:
    tracked = _git_ls_files(root, ["*.md"])
    if tracked:
        return sorted(root / path for path in tracked if (root / path).is_file() and not _has_skipped_part(Path(path)))
    return sorted(path for path in root.rglob("*.md") if path.is_file() and not _has_skipped_part(path.relative_to(root)))


def _audit_markdown_references(root: Path, markdown_files: list[Path]) -> list[RepoFinding]:
    issues: list[RepoFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for path in markdown_files:
        if _display_path(path, root) in GENERATED_MARKDOWN_REPORTS:
            continue
        for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
            for candidate in _extract_internal_path_candidates(line):
                normalized = _normalize_reference(candidate)
                if not normalized or _reference_exists(root, path, normalized):
                    continue
                key = (_display_path(path, root), line_number, normalized)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    RepoFinding(
                        category="missing_markdown_reference",
                        severity="warn",
                        path=key[0],
                        line=line_number,
                        message="Markdown references a repo-local path that does not exist.",
                        evidence=normalized,
                    )
                )
    return issues


def _audit_tracked_artifacts(root: Path) -> list[RepoFinding]:
    tracked = _git_ls_files(root, ARTIFACT_DIRS)
    if not tracked and not _is_git_worktree(root):
        tracked = [
            _display_path(path, root)
            for directory in ARTIFACT_DIRS
            for path in sorted((root / directory).rglob("*"))
            if path.is_file() and not _has_skipped_part(path.relative_to(root))
        ]
    return [
        RepoFinding(
            category="tracked_artifact_candidate",
            severity="review",
            path=path,
            line=None,
            message="File lives under a generated-output or temporary artifact directory.",
            evidence="Classify as durable evidence under docs/reports/evidence/ or generated output ignored by git.",
        )
        for path in tracked
    ]


def _audit_agent_entry_docs(root: Path, markdown_files: list[Path]) -> list[RepoFinding]:
    entry_files = [
        path
        for path in markdown_files
        if _display_path(path, root) in ENTRY_DOC_PATHS or (path.name == "SKILL.md" and "skills" in path.parts)
    ]
    issues: list[RepoFinding] = []
    for finding in _audit_markdown_references(root, entry_files):
        issues.append(
            RepoFinding(
                category="agent_entry_missing_reference",
                severity=finding.severity,
                path=finding.path,
                line=finding.line,
                message=finding.message,
                evidence=finding.evidence,
            )
        )
    for path in entry_files:
        rel = _display_path(path, root)
        text = _read_text(path)
        if rel in ENTRY_DOC_PATHS and rel != CANONICAL_ARCHITECTURE_PREFLIGHT and CANONICAL_ARCHITECTURE_PREFLIGHT not in text:
            issues.append(
                RepoFinding(
                    category="agent_entry_missing_canonical_preflight",
                    severity="review",
                    path=rel,
                    line=None,
                    message="Agent-facing entry doc does not point to the canonical AI-CRM architecture preflight.",
                    evidence=CANONICAL_ARCHITECTURE_PREFLIGHT,
                )
            )
        for line_number, line in enumerate(text.splitlines(), start=1):
            matched = [pattern for pattern in SENSITIVE_ENTRY_PATTERNS if pattern in line]
            if matched:
                issues.append(
                    RepoFinding(
                        category="agent_entry_ops_detail",
                        severity="review",
                        path=rel,
                        line=line_number,
                        message="Agent-facing entry doc includes concrete production connection or local ops detail.",
                        evidence=", ".join(matched),
                    )
                )
            if "real external adapter 仍 blocked / fake / staging-disabled" in line:
                issues.append(
                    RepoFinding(
                        category="agent_entry_external_effect_drift",
                        severity="warn",
                        path=rel,
                        line=line_number,
                        message="Agent-facing entry doc contains stale blanket external-effect wording.",
                        evidence="Align WeCom External Effect wording with PR #1505 while keeping other real calls blocked.",
                    )
                )
            stale_legacy = [pattern for pattern in STALE_LEGACY_FALLBACK_PATTERNS if pattern in line]
            if stale_legacy:
                issues.append(
                    RepoFinding(
                        category="agent_entry_legacy_fallback_drift",
                        severity="warn",
                        path=rel,
                        line=line_number,
                        message="Agent-facing entry doc describes retired legacy fallback as a current runtime boundary.",
                        evidence=", ".join(stale_legacy),
                    )
                )
    return issues


def _audit_production_ops_stubs(root: Path) -> list[RepoFinding]:
    issues: list[RepoFinding] = []
    for rel in PRODUCTION_OPS_STUB_PATHS:
        path = root / rel
        if not path.is_file():
            continue
        for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
            matched = [pattern for pattern in PRODUCTION_OPS_DETAIL_PATTERNS if pattern in line]
            if matched:
                issues.append(
                    RepoFinding(
                        category="production_ops_stub_detail",
                        severity="review",
                        path=rel,
                        line=line_number,
                        message="Production ops entry exposes concrete connection, dispatcher, or command detail.",
                        evidence=", ".join(matched),
                    )
                )
    return issues


def _audit_active_legacy_references(root: Path, markdown_files: list[Path]) -> list[RepoFinding]:
    issues: list[RepoFinding] = []
    for path in markdown_files:
        rel = _display_path(path, root)
        if rel.startswith("docs/archive/"):
            continue
        for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
            if any(token in line for token in ACTIVE_LEGACY_REFERENCE_ALLOWED_CONTEXT):
                continue
            for pattern, evidence in ACTIVE_LEGACY_REFERENCE_PATTERNS:
                if pattern.search(line):
                    issues.append(
                        RepoFinding(
                            category="active_legacy_path_reference",
                            severity="warn",
                            path=rel,
                            line=line_number,
                            message="Active documentation points readers at a retired legacy source path.",
                            evidence=evidence,
                        )
                    )
    return issues


def _audit_aicrm_markers(root: Path) -> list[RepoFinding]:
    base = root / "aicrm_next"
    if not base.exists():
        return []
    issues: list[RepoFinding] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_EXTENSIONS or _has_skipped_part(path.relative_to(root)):
            continue
        rel = _display_path(path, root)
        for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
            for marker_type, marker in AICRM_MARKERS:
                if marker.search(line):
                    issues.append(
                        RepoFinding(
                            category=f"aicrm_next_{marker_type}_marker",
                            severity="review",
                            path=rel,
                            line=line_number,
                            message=f"`{marker.pattern}` appears in `aicrm_next/`.",
                            evidence="Review marker before turning hygiene checks into enforcement.",
                        )
                    )
    return issues


def _extract_internal_path_candidates(line: str) -> list[str]:
    candidates: list[str] = []
    for match in LINK_RE.finditer(line):
        target = match.group("target")
        if match.group("image") and _is_external_link(target):
            continue
        candidates.append(target)
    masked_line = FULL_LINK_RE.sub("", line)
    if not _contains_external_absolute_path(masked_line):
        candidates.extend(match.group(0) for match in PATH_RE.finditer(masked_line))
    return candidates


def _normalize_reference(candidate: str) -> str | None:
    value = candidate.strip().strip("`'\"").rstrip(".,;:")
    if not value or value.startswith("#"):
        return None
    if _is_external_link(value) or value.startswith("app://"):
        return None
    if value.startswith((".claude/", "github.com/")):
        return None
    value = value.split("#", 1)[0].split("?", 1)[0]
    if _is_external_absolute_reference(value):
        return None
    return value or None


def _is_external_link(value: str) -> bool:
    return "://" in value or value.startswith("mailto:")


def _contains_external_absolute_path(line: str) -> bool:
    return any(prefix in line for prefix in ("/home/", "/tmp/", "/usr/", "/var/", "/etc/"))


def _is_external_absolute_reference(value: str) -> bool:
    if not value.startswith("/"):
        return False
    return value.startswith(("/home/", "/tmp/", "/usr/", "/var/", "/etc/", "/github.com/"))


def _reference_exists(root: Path, source: Path, reference: str) -> bool:
    ref_path = Path(reference)
    candidates = []
    if ref_path.is_absolute():
        candidates.append(root / reference.lstrip("/"))
    else:
        candidates.extend([source.parent / ref_path, root / ref_path])
    return any(candidate.exists() for candidate in candidates)


def _git_ls_files(root: Path, patterns: Iterable[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *patterns],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _is_git_worktree(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _has_skipped_part(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
