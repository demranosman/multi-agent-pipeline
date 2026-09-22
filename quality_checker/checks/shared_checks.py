"""Hem Python hem Node projelerinde çalışan, dile bağımsız kontroller."""
from __future__ import annotations

import json
from pathlib import Path

from quality_checker.checks.base import jscpd_ignore_glob, run_command, timed, tool_available
from quality_checker.models import CheckResult, Issue, Status


@timed
def run_jscpd_duplicate_code(project_path: Path) -> CheckResult:
    """jscpd hem Python hem JS/TS dahil pek çok dilde kopya-yapıştır kod tespiti yapar."""
    if not tool_available("npx"):
        return CheckResult(
            check_id="duplicate_code", tool="jscpd", status=Status.SKIPPED,
            duration_sec=0.0, summary="npx bulunamadı (kopya kod kontrolü atlandı).",
        )

    report_dir = project_path / ".jscpd-report"
    cmd = [
        "npx", "--yes", "jscpd", ".",
        "--reporters", "json",
        "--output", str(report_dir),
        "--silent",
        "--ignore", jscpd_ignore_glob(),
    ]
    code, out, err = run_command(cmd, project_path, timeout=300)

    issues: list[Issue] = []
    report_file = report_dir / "jscpd-report.json"
    percentage = None
    if report_file.exists():
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
            percentage = (data.get("statistics", {}) or {}).get("total", {}).get("percentage")
            for dup in data.get("duplicates", [])[:200]:
                first = dup.get("firstFile", {})
                second = dup.get("secondFile", {})
                issues.append(Issue(
                    file=first.get("name"),
                    line=first.get("startLoc", {}).get("line"),
                    severity="low",
                    message=f"Kopya kod: {first.get('name')}:{first.get('startLoc', {}).get('line')} <-> "
                            f"{second.get('name')}:{second.get('startLoc', {}).get('line')}",
                ))
        except (json.JSONDecodeError, OSError):
            pass

    error_detail = None
    if percentage is None:
        status, summary = Status.SKIPPED, "jscpd raporu okunamadı veya çalıştırılamadı."
        error_detail = (err or out or "").strip()[-500:] or None
    elif percentage > 10:
        status, summary = Status.FAIL, f"Kod tekrarı %{percentage:.1f} (yüksek)"
    elif percentage > 3:
        status, summary = Status.WARN, f"Kod tekrarı %{percentage:.1f}"
    else:
        status, summary = Status.PASS, f"Kod tekrarı %{percentage:.1f}"

    return CheckResult(
        check_id="duplicate_code", tool="jscpd", status=status, duration_sec=0.0,
        summary=summary, issue_count=len(issues), issues=issues, error=error_detail,
        raw_output=(out + err)[-8000:], command=" ".join(cmd),
    )
