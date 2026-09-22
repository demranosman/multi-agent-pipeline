"""
Pipeline'ın ham JSON raporlarını insan-okur bir Markdown dokümanına çevirir.
Kalite denetimi motorunun (quality_checker) sonuçlarını da tablo formatında görselleştirir.
"""
from __future__ import annotations

import json
from typing import Any

from schemas import PipelineOut, LogOut

STAGE_TITLES = {
    "research": "🔍 Araştırma",
    "planning": "🏗️ Planlama / Mimari",
    "coding": "💻 Kodlama",
    "testing": "🧪 Test & Kalite Güvence",
    "marketing": "📣 Pazarlama & Go-to-Market",
}


def _render_quality_report(qr: dict[str, Any]) -> list[str]:
    lines = []
    lines.append("### 🛡️ Otomatik Kod Kalitesi ve Test Denetimi Raporu")
    lines.append(f"- **Genel Durum:** `{qr.get('overall_status', 'N/A').upper()}`")
    lines.append(f"- **Proje Tipi:** `{', '.join(qr.get('project_types', []))}`")
    lines.append("")
    lines.append("| Araç | Kontrol Adı | Durum | Bulgu Sayısı | Süre | Özet |")
    lines.append("|---|---|---|---|---|---|")

    for r in qr.get("results", []):
        status_icon = "✅" if r.get("status") == "pass" else ("⚠️" if r.get("status") == "warn" else ("❌" if r.get("status") == "fail" else "⏭️"))
        lines.append(
            f"| `{r.get('tool')}` | {r.get('check_id')} | {status_icon} {r.get('status')} | {r.get('issue_count', 0)} | {r.get('duration_sec', 0)}s | {r.get('summary', '')} |"
        )
    lines.append("")

    # Varsa bulguları listele
    has_issues = False
    for r in qr.get("results", []):
        issues = r.get("issues", [])
        if issues:
            if not has_issues:
                lines.append("#### Tespit Edilen Bulgular:")
                has_issues = True
            lines.append(f"**{r.get('tool')} ({len(issues)} bulgu):**")
            for iss in issues[:20]:
                loc = f"`{iss.get('file')}:{iss.get('line')}`" if iss.get("line") else f"`{iss.get('file', '')}`"
                lines.append(f"- {loc} — {iss.get('message', '')}")
            if len(issues) > 20:
                lines.append(f"- *... ve {len(issues) - 20} bulgu daha*")
            lines.append("")

    return lines


def _render_value(key: str, value: Any) -> list[str]:
    """Bir full_output alanının değerini Markdown satırlarına çevirir."""
    lines: list[str] = []

    if key == "quality_report" and isinstance(value, dict):
        return _render_quality_report(value)

    if key == "files" and isinstance(value, list):
        lines.append("### 📂 Üretilen Dosyalar")
        for f in value:
            lines.append(f"- `{f.get('path')}`")
        lines.append("")
        return lines

    if isinstance(value, list):
        if not value:
            lines.append("_(boş)_")
        for item in value:
            if isinstance(item, dict):
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
            else:
                lines.append(f"- {item}")
    elif isinstance(value, dict):
        lines.append("```json")
        lines.append(json.dumps(value, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append(str(value))
    return lines


def render_markdown(pipeline: PipelineOut, logs: list[LogOut]) -> str:
    lines: list[str] = []
    lines.append("# 🚀 Fikirden Pazarlamaya Ajan Hattı Raporu")
    lines.append("")
    lines.append(f"**Fikir:** {pipeline.idea_text}")
    lines.append(f"**Pipeline ID:** `{pipeline.id}`")
    lines.append(f"**Durum:** `{pipeline.status.value}`")
    lines.append(f"**Mevcut Aşama:** `{pipeline.current_stage.value}`")
    lines.append(f"**Oluşturulma:** {pipeline.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for log in logs:
        title = STAGE_TITLES.get(log.stage.value, log.stage.value)
        revision_label = f" (deneme #{log.revision_round + 1})" if log.revision_round else ""
        model_label = f" `[{log.model}]`" if log.model else ""
        lines.append(f"## {title}{revision_label}{model_label}")
        lines.append("")
        lines.append(f"*{log.summary}*")
        lines.append("")

        if isinstance(log.full_output, dict):
            for key, value in log.full_output.items():
                if key in ("quality_report", "files"):
                    lines.extend(_render_value(key, value))
                else:
                    lines.append(f"**{key}**")
                    lines.extend(_render_value(key, value))
                    lines.append("")
        else:
            lines.append(str(log.full_output))
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
