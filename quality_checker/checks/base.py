"""Tüm kontrol modüllerinin kullandığı ortak subprocess yardımcıları."""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import time
from pathlib import Path

from quality_checker.models import CheckResult, Status

# Bağımlılık/derleme dizinleri: hiçbir araç bunları taramamalı.
EXCLUDE_DIR_NAMES = [
    ".venv", "venv", "env", ".env",
    "node_modules", ".git",
    "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "site-packages",
]


def tool_available(name: str) -> bool:
    """Verilen komutun PATH üzerinde bulunup bulunmadığını kontrol eder."""
    return shutil.which(name) is not None


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Bir komutu çalıştırır, (returncode, stdout, stderr) döner."""
    if os.name == "nt" and cmd:
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd = [resolved] + cmd[1:]
        if str(cmd[0]).lower().endswith((".cmd", ".bat")):
            cmd = ["cmd", "/c", *cmd]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return -1, "", f"Komut bulunamadı: {exc}"
    except subprocess.TimeoutExpired:
        return -2, "", f"Zaman aşımı ({timeout}s) - komut: {' '.join(cmd)}"


def missing_tool_result(check_id: str, tool: str, install_hint: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        tool=tool,
        status=Status.SKIPPED,  # Araç kurulu değilse pipeline'ı kırmadan skipped işaretle
        duration_sec=0.0,
        summary=f"{tool} yüklü değil (atlanıyor).",
        error=f"Kurulum için: {install_hint}",
    )


def bandit_exclude_arg() -> str:
    """bandit -x flag'i için: proje köküne göre ./dizin,./dizin2 formatı."""
    return ",".join(f"./{name}" for name in EXCLUDE_DIR_NAMES)


def vulture_exclude_arg() -> str:
    """vulture --exclude flag'i için: virgülle ayrılmış glob desenleri."""
    return ",".join(EXCLUDE_DIR_NAMES)


def mypy_exclude_arg() -> str:
    """mypy --exclude flag'i için: regex formatı."""
    alternation = "|".join(EXCLUDE_DIR_NAMES)
    return rf"(^|/)({alternation})/"


def jscpd_ignore_glob() -> str:
    """jscpd --ignore flag'i için tam glob desenleri."""
    return ",".join(f"**/{name}/**" for name in EXCLUDE_DIR_NAMES)


def timed(fn):
    """Bir check fonksiyonunun süresini ölçüp CheckResult.duration_sec'e yazan dekoratör."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> CheckResult:
        start = time.time()
        result = fn(*args, **kwargs)
        result.duration_sec = round(time.time() - start, 2)
        return result
    return wrapper
