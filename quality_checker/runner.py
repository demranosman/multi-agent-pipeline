"""Tespit edilen proje tipine göre doğru kontrolleri, doğru sırada çalıştırır."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from quality_checker.checks import node_checks as nc
from quality_checker.checks import python_checks as pc
from quality_checker.checks import shared_checks as sc
from quality_checker.detector import detect_project_types
from quality_checker.models import CheckResult, PipelineReport, Status

PYTHON_STEPS: list[Callable[[Path], CheckResult]] = [
    pc.run_ruff_lint,
    pc.run_mypy_type_check,
    pc.run_bandit_security,
    pc.run_pip_audit,
    pc.run_vulture_deadcode,
    pc.run_pytest_execution,
]

NODE_STEPS: list[Callable[[Path], CheckResult]] = [
    nc.run_eslint,
    nc.run_tsc_type_check,
    nc.run_npm_audit,
    nc.run_depcheck,
]

SHARED_STEPS: list[Callable[[Path], CheckResult]] = [
    sc.run_jscpd_duplicate_code,
]


def run_pipeline(project_path: str | Path, include_slow: bool = False) -> PipelineReport:
    """Belirtilen proje dizini üzerinde tüm kalite denetimlerini çalıştırır."""
    path = Path(project_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Proje dizini bulunamadı: {path}")

    project_types = detect_project_types(path)
    report = PipelineReport(
        project_path=str(path),
        project_types=project_types,
        started_at=PipelineReport.now(),
    )

    steps: list[Callable[[Path], CheckResult]] = []
    if "python" in project_types or project_types == ["unknown"]:
        steps.extend(PYTHON_STEPS)
    if "node" in project_types:
        steps.extend(NODE_STEPS)
    steps.extend(SHARED_STEPS)

    for step in steps:
        try:
            result = step(path)
        except Exception as exc:
            result = CheckResult(
                check_id=step.__name__, tool=step.__name__, status=Status.ERROR,
                duration_sec=0.0, summary="Kontrol çalıştırılırken beklenmeyen hata oluştu.",
                error=str(exc),
            )
        report.add(result)

    report.finished_at = PipelineReport.now()
    return report
