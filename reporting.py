"""
Pipeline'ın ham JSON raporlarını insan-okur bir Markdown dokümanına çevirir.
"""
import json

from schemas import PipelineOut, LogOut

STAGE_TITLES = {
    "research": "🔍 Araştırma",
    "planning": "🏗️ Planlama / Mimari",
    "coding": "💻 Kodlama",
    "testing": "🧪 Test",
    "marketing": "📣 Pazarlama",
}


def _render_value(value) -> list[str]:
    """Bir full_output alanının değerini (liste/dict/skaler) Markdown satırlarına çevirir."""
    lines: list[str] = []
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
    lines.append("# Pipeline Raporu")
    lines.append("")
    lines.append(f"**Fikir:** {pipeline.idea_text}")
    lines.append(f"**Pipeline ID:** `{pipeline.id}`")
    lines.append(f"**Durum:** {pipeline.status.value}")
    lines.append(f"**Mevcut aşama:** {pipeline.current_stage.value}")
    lines.append(f"**Oluşturulma:** {pipeline.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for log in logs:
        title = STAGE_TITLES.get(log.stage.value, log.stage.value)
        revision_label = f" (deneme #{log.revision_round + 1})" if log.revision_round else ""
        lines.append(f"## {title}{revision_label}")
        lines.append("")
        lines.append(f"*{log.summary}*")
        lines.append("")

        if isinstance(log.full_output, dict):
            for key, value in log.full_output.items():
                lines.append(f"**{key}**")
                lines.extend(_render_value(value))
                lines.append("")
        else:
            lines.append(str(log.full_output))
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
