"""Faz kapıları: contract bütünlüğü, kapsam denetimi ve placeholder taraması.

Bu modül yalnızca saf (yan etkisiz) yardımcılar içerir; DB ve orkestrasyon
kararları orchestrator.py'de verilir. Böylece davranış tek yerde ve test
edilebilir kalır.
"""
from __future__ import annotations

import hashlib
import json
import re

# Üretilen koda bırakılan "tamamlanmamış" izleri. Salt `pass` / `...` satırı da
# placeholder sayılır (AGENTS.md: placeholder ile "bitti" denemez).
PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"implement\s+later", re.IGNORECASE),
    re.compile(r"coming\s+soon", re.IGNORECASE),
    re.compile(r"raise\s+NotImplementedError"),
    re.compile(r"^\s*(?:pass|\.\.\.)\s*(?:#.*)?$", re.MULTILINE),
]


def canonical_json(value: object) -> str:
    """Hash için deterministik JSON: anahtar sırası sabit, unicode korunur."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def content_hash(value: object) -> str:
    """Bir çıktının (full_output) sha256 özeti."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def pattern_to_regex(pattern: str) -> re.Pattern[str] | None:
    """Onaylı kapsam desenini tam-eşleşme regex'ine çevirir ('*' → '.*').

    Boş veya anlamsız desenler (None, '<...>', 'yok') için None döner.
    Sondaki '/' bir dizin anlamına gelir: `app/` → `app/**`.
    """
    clean = str(pattern).strip().lstrip("/\\").strip().removeprefix("./")
    if not clean or "<" in clean or clean.lower() in ("none", "yok", "tbd"):
        return None
    if clean.endswith("/"):
        clean += "**"
    escaped = re.escape(clean).replace(r"\*", ".*")
    try:
        return re.compile(rf"^{escaped}$", re.IGNORECASE)
    except re.error:
        return None


def out_of_scope_files(paths: list[str], scope_patterns: list[str]) -> list[str]:
    """scope_patterns dışında kalan dosya yollarını döner.

    Desen listesi boş veya hiçbiri geçerli değilse kapsam denetimi atlanır
    (ihlal üretilmez) — mevcut davranış korunur.
    """
    regexes = [r for r in (pattern_to_regex(p) for p in scope_patterns) if r is not None]
    if not regexes:
        return []
    return [p for p in paths if not any(r.match(p) for r in regexes)]


def scan_placeholders(files: list) -> list[str]:
    """files: [{'path': ..., 'content': ...}] → 'path:satır → eşleşme' listesi."""
    hits: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        content = str(item.get("content", ""))
        for pattern in PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                hits.append(f"{path}:{line} → {match.group(0).strip()[:60]}")
    return hits
