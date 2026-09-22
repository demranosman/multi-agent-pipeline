"""Python projeleri için statik analiz ve test kontrolleri."""
from __future__ import annotations

import json
import re
from pathlib import Path

from quality_checker.checks.base import (
    bandit_exclude_arg,
    missing_tool_result,
    mypy_exclude_arg,
    run_command,
    timed,
    tool_available,
    vulture_exclude_arg,
)
from quality_checker.models import CheckResult, Issue, Status


@timed
def run_ruff_lint(project_path: Path) -> CheckResult:
    if not tool_available("ruff"):
        return missing_tool_result("lint", "ruff", "pip install ruff")

    cmd = ["ruff", "check", ".", "--output-format", "json"]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    try:
        data = json.loads(out) if out.strip() else []
        for item in data:
            issues.append(Issue(
                file=item.get("filename"),
                line=(item.get("location") or {}).get("row"),
                severity="medium",
                message=item.get("message", ""),
                rule=item.get("code"),
            ))
    except json.JSONDecodeError:
        pass

    status = Status.PASS if not issues else (Status.FAIL if len(issues) > 10 else Status.WARN)
    return CheckResult(
        check_id="lint", tool="ruff", status=status, duration_sec=0.0,
        summary=f"{len(issues)} lint bulgusu", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_mypy_type_check(project_path: Path) -> CheckResult:
    if not tool_available("mypy"):
        return missing_tool_result("type_check", "mypy", "pip install mypy")

    cmd = ["mypy", ".", "--no-error-summary", "--no-color-output", "--exclude", mypy_exclude_arg()]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    pattern = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?:\d+:)?\s*error:\s*(?P<msg>.+)$")
    for line in out.splitlines():
        m = pattern.match(line.strip())
        if m:
            issues.append(Issue(
                file=m.group("file"), line=int(m.group("line")),
                severity="medium", message=m.group("msg"),
            ))

    status = Status.PASS if not issues else (Status.FAIL if len(issues) > 10 else Status.WARN)
    return CheckResult(
        check_id="type_check", tool="mypy", status=status, duration_sec=0.0,
        summary=f"{len(issues)} tip hatası", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_bandit_security(project_path: Path) -> CheckResult:
    if not tool_available("bandit"):
        return missing_tool_result("security", "bandit", "pip install bandit")

    cmd = ["bandit", "-r", ".", "-f", "json", "-q", "-x", bandit_exclude_arg()]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    try:
        data = json.loads(out) if out.strip() else {}
        for item in data.get("results", []):
            issues.append(Issue(
                file=item.get("filename"),
                line=item.get("line_number"),
                severity=str(item.get("issue_severity", "")).lower(),
                message=item.get("issue_text", ""),
                rule=item.get("test_id"),
            ))
    except json.JSONDecodeError:
        pass

    high_count = sum(1 for i in issues if i.severity in ("high", "critical"))
    status = Status.FAIL if high_count else (Status.WARN if issues else Status.PASS)
    return CheckResult(
        check_id="security", tool="bandit", status=status, duration_sec=0.0,
        summary=f"{len(issues)} güvenlik bulgusu ({high_count} yüksek riskli)",
        issue_count=len(issues), issues=issues[:200],
        raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_pip_audit(project_path: Path) -> CheckResult:
    if not tool_available("pip-audit"):
        return missing_tool_result("dependency_audit", "pip-audit", "pip install pip-audit")

    # Sadece proje dizininde requirements.txt varsa tara (ortamın tamamını taramasın)
    req_file = project_path / "requirements.txt"
    if not req_file.exists():
        return CheckResult(
            check_id="dependency_audit", tool="pip-audit", status=Status.SKIPPED,
            duration_sec=0.0, summary="Projede requirements.txt bulunmadığı için bağımlılık denetimi atlandı.",
        )

    cmd = ["pip-audit", "-r", req_file.name, "--format", "json"]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    try:
        data = json.loads(out) if out.strip() else []
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        for dep in deps or []:
            for vuln in dep.get("vulns", []):
                issues.append(Issue(
                    file=dep.get("name"),
                    severity="high",
                    message=f"{dep.get('name')} {dep.get('version')}: {vuln.get('id')}",
                    rule=vuln.get("id"),
                ))
    except (json.JSONDecodeError, AttributeError):
        pass

    status = Status.FAIL if issues else Status.PASS
    return CheckResult(
        check_id="dependency_audit", tool="pip-audit", status=status, duration_sec=0.0,
        summary=f"{len(issues)} bilinen zafiyetli bağımlılık", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_vulture_deadcode(project_path: Path) -> CheckResult:
    if not tool_available("vulture"):
        return missing_tool_result("dead_code", "vulture", "pip install vulture")

    cmd = ["vulture", ".", "--min-confidence", "80", "--exclude", vulture_exclude_arg()]
    code, out, err = run_command(cmd, project_path)

    issues: list[Issue] = []
    pattern = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<msg>.+)$")
    for line in out.splitlines():
        m = pattern.match(line.strip())
        if m:
            issues.append(Issue(
                file=m.group("file"), line=int(m.group("line")),
                severity="low", message=m.group("msg"),
            ))

    status = Status.WARN if issues else Status.PASS
    return CheckResult(
        check_id="dead_code", tool="vulture", status=status, duration_sec=0.0,
        summary=f"{len(issues)} kullanılmayan kod bulgusu", issue_count=len(issues),
        issues=issues[:200], raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )


@timed
def run_pytest_execution(project_path: Path) -> CheckResult:
    """Projede bulunan testleri (test_*.py) pytest ile çalıştırır."""
    if not tool_available("pytest"):
        return missing_tool_result("test_runner", "pytest", "pip install pytest pytest-cov")

    test_files = list(project_path.glob("**/test_*.py")) + list(project_path.glob("**/*_test.py"))
    if not test_files:
        return CheckResult(
            check_id="test_runner", tool="pytest", status=Status.SKIPPED,
            duration_sec=0.0, summary="Projede çalıştırılacak test_*.py dosyası bulunamadı.",
        )

    cov_file = project_path / ".pipeline_coverage.json"
    cmd = ["pytest", "-v", "--tb=short", f"--cov=.", f"--cov-report=json:{cov_file.name}"]
    code, out, err = run_command(cmd, project_path, timeout=300)

    issues: list[Issue] = []
    if code != 0:
        for line in out.splitlines():
            if line.startswith("FAILED") or line.startswith("ERROR"):
                issues.append(Issue(
                    severity="high",
                    message=line.strip(),
                ))

    status = Status.PASS if code == 0 else Status.FAIL
    summary = f"Pytest tamamlandı (Çıkış kodu: {code})" if code == 0 else f"Pytest başarısız: {len(issues)} test hatası"

    if cov_file.exists():
        try:
            cov_data = json.loads(cov_file.read_text(encoding="utf-8"))
            pct = cov_data.get("totals", {}).get("percent_covered")
            if pct is not None:
                summary += f", Kapsam: %{pct:.1f}"
        except Exception:
            pass
        finally:
            try:
                cov_file.unlink()
            except OSError:
                pass

    return CheckResult(
        check_id="test_runner", tool="pytest", status=status, duration_sec=0.0,
        summary=summary, issue_count=len(issues), issues=issues,
        raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )
