"""Her pipeline için izole disk çalışma alanını (workspaces/<pipeline_id>/) yönetir."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

WORKSPACE_BASE_DIR = Path(__file__).parent / "workspaces"


def get_workspace_path(pipeline_id: str) -> Path:
    """Belirli bir pipeline_id için çalışma alanı dizinini döndürür."""
    path = (WORKSPACE_BASE_DIR / pipeline_id).resolve()
    # Güvenlik: pipeline_id path traversal yapamaz
    if not str(path).startswith(str(WORKSPACE_BASE_DIR.resolve())):
        raise ValueError(f"Geçersiz pipeline ID: {pipeline_id}")
    return path


def write_files_to_workspace(pipeline_id: str, files: list[dict[str, Any]]) -> Path:
    """
    coding_agent tarafından üretilen dosyaları (files: [{"path": "...", "content": "..."}])
    fiziksel olarak diske kaydeder.
    """
    workspace = get_workspace_path(pipeline_id)
    workspace.mkdir(parents=True, exist_ok=True)

    for item in files:
        rel_path = item.get("path", "").strip().lstrip("/\\")
        if not rel_path:
            continue

        file_path = (workspace / rel_path).resolve()
        # Path traversal güvenlik kontrolü
        if not str(file_path).startswith(str(workspace)):
            raise ValueError(f"Güvenlik ihlali: Dosya yolu çalışma alanı dışına çıkamaz ({rel_path})")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = item.get("content", "")
        file_path.write_text(content, encoding="utf-8")

    return workspace


def read_workspace_files(pipeline_id: str) -> list[dict[str, Any]]:
    """Çalışma alanında bulunan dosyaları ve içeriklerini listeler."""
    workspace = get_workspace_path(pipeline_id)
    if not workspace.exists():
        return []

    result = []
    for file_path in workspace.rglob("*"):
        if file_path.is_file():
            # Cache ve git klasörlerini atla
            rel_parts = file_path.relative_to(workspace).parts
            if any(p.startswith(".") or p in ("__pycache__", "node_modules") for p in rel_parts):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = "<binary veya okunamayan dosya>"

            result.append({
                "path": str(file_path.relative_to(workspace)).replace("\\", "/"),
                "size": file_path.stat().st_size,
                "content": content,
            })
    return result


def clean_workspace(pipeline_id: str) -> None:
    """Çalışma alanını temizler."""
    workspace = get_workspace_path(pipeline_id)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
