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

# Proje kökünde aranacak sanal ortam klasörleri (öncelik sırasıyla).
VENV_DIR_NAMES = (".venv", "venv", "env")


def _venv_bin_dirs(project_path: Path) -> list[Path]:
    """Projedeki sanal ortamların çalıştırılabilir dizinlerini döner."""
    bin_name = "Scripts" if os.name == "nt" else "bin"
    return [d for name in VENV_DIR_NAMES if (d := project_path / name / bin_name).is_dir()]


def find_tool(name: str, project_path: Path | None = None) -> str | None:
    """Aracı önce proje venv'inde, yoksa PATH'te arar; bulunan tam yolu döner."""
    if project_path is not None:
        for bin_dir in _venv_bin_dirs(project_path):
            found = shutil.which(name, path=str(bin_dir))
            if found:
                return found
    return shutil.which(name)


def tool_available(name: str, project_path: Path | None = None) -> bool:
    """Verilen komutun proje venv'inde veya PATH üzerinde bulunup bulunmadığını kontrol eder."""
    return find_tool(name, project_path) is not None


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Bir komutu çalıştırır, (returncode, stdout, stderr) döner."""
    if cmd:
        head = str(cmd[0])
        # Yalnızca çıplak araç adını çöz (yol içeren komutlara dokunma).
        # Öncelik proje venv'inde; yoksa PATH'e düşer.
        if os.sep not in head and "/" not in head:
            resolved = find_tool(head, cwd)
            if resolved:
                cmd = [resolved, *cmd[1:]]
        if os.name == "nt" and str(cmd[0]).lower().endswith((".cmd", ".bat")):
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
            check=False,
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
