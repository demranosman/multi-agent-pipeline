"""Node/TypeScript projelerine özel kontroller: eslint, tsc, npm audit, depcheck."""
from __future__ import annotations

import json
import os
from pathlib import Path

from quality_checker.checks.base import missing_tool_result, run_command, timed, tool_available
from quality_checker.models import CheckResult, Issue, Status

_SEVERITY_MAP = {1: "low", 2: "medium"}  # eslint: 1=warning, 2=error


def _local_bin_path(project_path: Path, name: str) -> Path | None:
    """node_modules/.bin altında bu aracı bulur."""
    local_dir = project_path / "node_modules" / ".bin"
    candidates = [f"{name}.cmd", name] if os.name == "nt" else [name]
    for candidate in candidates:
        path = local_dir / candidate
        if path.exists():
            return path
    return None


def _has_bin(project_path: Path, name: str) -> bool:
    return tool_available(name) or _local_bin_path(project_path, name) is not None


def _local_cmd(project_path: Path, name: str) -> str:
    local = _local_bin_path(project_path, name)
    return str(local) if local else name


@timed
def run_eslint(project_path: Path) -> CheckResult:
    if not _has_bin(project_path, "eslint"):
        return missing_tool_result("lint", "eslint", "npm install eslint --save-dev")

    cmd = [_local_cmd(project_path, "eslint"), ".", "--format", "json"]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    try:
        data = json.loads(out) if out.strip() else []
        for file_result in data:
            for msg in file_result.get("messages", []):
                issues.append(Issue(
                    file=file_result.get("filePath"),
                    line=msg.get("line"),
                    severity=_SEVERITY_MAP.get(msg.get("severity"), "low"),
                    message=msg.get("message", ""),
                    rule=msg.get("ruleId"),
                ))
    except json.JSONDecodeError:
        pass

    errors = sum(1 for i in issues if i.severity == "medium")
    status = Status.FAIL if errors else (Status.WARN if issues else Status.PASS)
    return CheckResult(
        check_id="lint", tool="eslint", status=status, duration_sec=0.0,
        summary=f"{len(issues)} lint bulgusu ({errors} hata)", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_tsc_type_check(project_path: Path) -> CheckResult:
    if not (project_path / "tsconfig.json").exists():
        return CheckResult(
            check_id="type_check", tool="tsc", status=Status.SKIPPED,
            duration_sec=0.0, summary="tsconfig.json bulunamadı, TypeScript projesi değil.",
        )
    if not _has_bin(project_path, "tsc"):
        return missing_tool_result("type_check", "tsc", "npm install typescript --save-dev")

    cmd = [_local_cmd(project_path, "tsc"), "--noEmit", "--pretty", "false"]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    for line in out.splitlines():
        if ": error " in line:
            try:
                file_part, rest = line.split("(", 1)
                line_no = int(rest.split(",")[0])
                issues.append(Issue(file=file_part.strip(), line=line_no, severity="medium", message=line.strip()))
            except (ValueError, IndexError):
                issues.append(Issue(severity="medium", message=line.strip()))

    status = Status.PASS if not issues else (Status.FAIL if len(issues) > 20 else Status.WARN)
    return CheckResult(
        check_id="type_check", tool="tsc", status=status, duration_sec=0.0,
        summary=f"{len(issues)} tip hatası", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_npm_audit(project_path: Path) -> CheckResult:
    if not tool_available("npm"):
        return missing_tool_result("dependency_audit", "npm", "Node.js/npm kurulu olmalı")

    cmd = ["npm", "audit", "--json"]
    code, out, err = run_command(cmd, project_path)

    counts = {}
    try:
        data = json.loads(out) if out.strip() else {}
        counts = (data.get("metadata", {}) or {}).get("vulnerabilities", {}) or {}
    except json.JSONDecodeError:
        pass

    total = sum(v for k, v in counts.items() if k != "total" and isinstance(v, int))
    high_critical = counts.get("high", 0) + counts.get("critical", 0)
    status = Status.FAIL if high_critical else (Status.WARN if total else Status.PASS)
    return CheckResult(
        check_id="dependency_audit", tool="npm audit", status=status, duration_sec=0.0,
        summary=f"{total} zafiyet ({high_critical} yüksek/kritik)", issue_count=total,
        raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_depcheck(project_path: Path) -> CheckResult:
    if not tool_available("npx"):
        return missing_tool_result("dead_code", "depcheck", "npm install -g depcheck (veya npx ile otomatik)")

    cmd = ["npx", "--yes", "depcheck", "--json"]
    code, out, err = run_command(cmd, project_path, timeout=180)

    issues: list[Issue] = []
    try:
        data = json.loads(out) if out.strip() else {}
        for dep in data.get("dependencies", []):
            issues.append(Issue(severity="low", message=f"Kullanılmayan bağımlılık: {dep}"))
        for dep, files in (data.get("missing", {}) or {}).items():
            issues.append(Issue(severity="medium", message=f"Eksik/bildirilmemiş bağımlılık: {dep}", file=", ".join(files[:3])))
    except json.JSONDecodeError:
        pass

    status = Status.WARN if issues else Status.PASS
    return CheckResult(
        check_id="dead_code", tool="depcheck", status=status, duration_sec=0.0,
        summary=f"{len(issues)} bulgu (kullanılmayan/eksik bağımlılık)", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_jest_coverage(project_path: Path) -> CheckResult:
    if not tool_available("npx"):
        return missing_tool_result("coverage", "jest", "npm install jest --save-dev")

    cov_dir = project_path / ".pipeline_coverage"
    cmd = ["npx", "--yes", "jest", "--coverage", "--coverageReporters=json-summary", f"--coverageDirectory={cov_dir.name}", "--silent"]
    code, out, err = run_command(cmd, project_path, timeout=600)

    coverage_pct = None
    summary_file = cov_dir / "coverage-summary.json"
    if summary_file.exists():
        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
            coverage_pct = data.get("total", {}).get("lines", {}).get("pct")
        except (json.JSONDecodeError, OSError):
            pass
        finally:
            import shutil
            try:
                shutil.rmtree(cov_dir)
            except OSError:
                pass

    if coverage_pct is None:
        status = Status.SKIPPED
        summary = "Coverage verisi okunamadı (jest yapılandırılmamış olabilir)"
    elif coverage_pct >= 80:
        status, summary = Status.PASS, f"Kapsam %{coverage_pct:.1f}"
    elif coverage_pct >= 50:
        status, summary = Status.WARN, f"Kapsam %{coverage_pct:.1f} (düşük)"
    else:
        status, summary = Status.FAIL, f"Kapsam %{coverage_pct:.1f} (çok düşük)"

    return CheckResult(
        check_id="coverage", tool="jest", status=status, duration_sec=0.0,
        summary=summary, raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )
