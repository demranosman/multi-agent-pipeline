"""Pipeline'daki tüm kontrol adımlarının paylaştığı veri modelleri."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"          # araç çalıştırılamadı (yüklü değil, timeout vb.)
    SKIPPED = "skipped"       # proje tipine uymadığı için atlandı


@dataclass
class Issue:
    """Bir aracın raporladığı tek bir bulgu (satır bazlı)."""
    file: str | None = None
    line: int | None = None
    severity: str = "info"   # info | low | medium | high | critical
    message: str = ""
    rule: str | None = None  # eslint kural adı, bandit test id'si vb.


@dataclass
class CheckResult:
    """Tek bir aracın (ruff, bandit, eslint, mutmut ...) çalıştırma sonucu."""
    check_id: str             # 'lint', 'type_check', 'security', ...
    tool: str                 # 'ruff', 'eslint', 'bandit', ...
    status: Status
    duration_sec: float
    summary: str = ""         # insan tarafından okunabilir tek satır özet
    issue_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    raw_output: str = ""      # aracın ham stdout/stderr çıktısı
    command: str = ""         # çalıştırılan gerçek komut
    error: str | None = None  # araç hiç çalışmadıysa (yüklü değil vb.) hata mesajı

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class PipelineReport:
    project_path: str
    project_types: list[str]          # ['python'], ['node'], ['python', 'node']
    started_at: float
    finished_at: float | None = None
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def overall_status(self) -> Status:
        statuses = [r.status for r in self.results]
        if Status.FAIL in statuses or Status.ERROR in statuses:
            return Status.FAIL
        if Status.WARN in statuses:
            return Status.WARN
        return Status.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "project_types": self.project_types,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "overall_status": self.overall_status.value,
            "results": [r.to_dict() for r in self.results],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def to_markdown(self) -> str:
        STATUS_LABEL = {
            Status.PASS: "✅ Geçti", Status.WARN: "⚠️ Uyarı", Status.FAIL: "❌ Başarısız",
            Status.ERROR: "🛑 Hata", Status.SKIPPED: "⏭️ Atlandı",
        }
        started = datetime.fromtimestamp(self.started_at).strftime("%Y-%m-%d %H:%M:%S")
        finished = (
            datetime.fromtimestamp(self.finished_at).strftime("%Y-%m-%d %H:%M:%S")
            if self.finished_at else "-"
        )

        lines: list[str] = []
        lines.append("# Kod Kalitesi ve Test Raporu\n")
        lines.append(f"- **Proje Dizini:** `{self.project_path}`")
        lines.append(f"- **Proje Tipi:** {', '.join(self.project_types)}")
        lines.append(f"- **Başlangıç:** {started}  •  **Bitiş:** {finished}")
        lines.append(f"- **Genel Durum:** {STATUS_LABEL.get(self.overall_status, self.overall_status.value)}\n")

        lines.append("| Adım | Araç | Durum | Bulgu | Süre | Özet |")
        lines.append("|---|---|---|---|---|---|")
        for r in self.results:
            lines.append(
                f"| {r.check_id} | {r.tool} | {STATUS_LABEL.get(r.status, r.status.value)} "
                f"| {r.issue_count} | {r.duration_sec}s | {r.summary} |"
            )
        lines.append("")

        for r in self.results:
            if not r.issues and not r.error:
                continue
            lines.append(f"### {r.check_id} ({r.tool})")
            if r.error:
                lines.append(f"> {r.error}\n")
            for issue in r.issues[:50]:
                loc = f"`{issue.file}:{issue.line}`" if issue.line else (f"`{issue.file}`" if issue.file else "")
                rule = f" ({issue.rule})" if issue.rule else ""
                lines.append(f"- {loc}{rule} — {issue.message}")
            if len(r.issues) > 50:
                lines.append(f"- ... ve {len(r.issues) - 50} bulgu daha")
            lines.append("")

        return "\n".join(lines)

    def save_markdown(self, path: Path) -> None:
        path.write_text(self.to_markdown(), encoding="utf-8")

    @staticmethod
    def now() -> float:
        return time.time()
