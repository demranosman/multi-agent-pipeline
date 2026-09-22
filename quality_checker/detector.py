"""Verilen dizinin Python mı, Node mu, yoksa her ikisi mi olduğunu tespit eder."""
from __future__ import annotations

import os
from pathlib import Path

from quality_checker.checks.base import EXCLUDE_DIR_NAMES

PYTHON_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile")
NODE_MARKERS = ("package.json",)


def detect_project_types(project_path: Path) -> list[str]:
    types: list[str] = []
    if any((project_path / marker).exists() for marker in PYTHON_MARKERS):
        types.append("python")
    if any((project_path / marker).exists() for marker in NODE_MARKERS):
        types.append("node")

    if not types:
        has_py = False
        has_js = False

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]

            for file in files:
                if file.endswith(".py"):
                    has_py = True
                if file.endswith((".js", ".ts", ".jsx", ".tsx")):
                    has_js = True

            if has_py and has_js:
                break

        if has_py:
            types.append("python")
        if has_js:
            types.append("node")

    return types or ["unknown"]
