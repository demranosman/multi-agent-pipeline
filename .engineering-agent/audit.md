# Kod Kalitesi Raporu

- **Proje:** `C:\Users\fikret\Desktop\multi-agent-pipeline`
- **Tip:** python
- **Başlangıç:** 2026-10-05 10:08:31  ·  **Bitiş:** 2026-10-05 10:09:12
- **Genel durum:** ⚠️ Uyarı

| Adım | Araç | Durum | Bulgu | Süre | Özet |
|---|---|---|---|---|---|
| lint | ruff | ⚠️ Uyarı | 15 | 0.53s | 15 lint bulgusu |
| type_check | mypy | ✅ Geçti | 0 | 3.71s | 0 tip hatası |
| security | bandit | ⚠️ Uyarı | 56 | 0.94s | 56 güvenlik bulgusu (0 yüksek riskli) |
| dependency_audit | pip-audit | ✅ Geçti | 0 | 33.25s | 0 bilinen zafiyetli bağımlılık |
| dead_code | vulture | ✅ Geçti | 0 | 0.3s | 0 kullanılmayan kod bulgusu |
| duplicate_code | jscpd | ✅ Geçti | 2 | 2.11s | Kod tekrarı %0.3 |

## lint (ruff)
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\node_checks.py:40` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\node_checks.py:77` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\node_checks.py:103` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\node_checks.py:128` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\node_checks.py:155` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:26` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:56` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:82` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:122` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:153` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:193` (PIE810) — Call `startswith` once with a `tuple`
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\python_checks.py:208` (S110) — `try`-`except`-`pass` detected, consider logging the exception
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\checks\shared_checks.py:28` (RUF059) — Unpacked variable `code` is never used
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\models.py:89` (UP017) — Use `datetime.UTC` alias
- `C:\Users\fikret\Desktop\multi-agent-pipeline\quality_checker\models.py:91` (UP017) — Use `datetime.UTC` alias

## security (bandit)
- `.\quality_checker\checks\base.py:7` (B404) — Consider possible security implications associated with the subprocess module.
- `.\quality_checker\checks\base.py:42` (B603) — subprocess call - check for execution of untrusted input.
- `.\quality_checker\checks\python_checks.py:208` (B110) — Try, Except, Pass detected.
- `.\quality_checker\models.py:14` (B105) — Possible hardcoded password: 'pass'
- `.\tests\test_pipeline.py:36` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:39` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:40` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:44` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:46` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:47` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:50` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:51` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:54` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:55` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:72` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:76` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:78` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:79` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:83` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:84` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:88` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:89` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:110` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:113` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:114` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:136` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:140` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:146` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:148` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:149` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:153` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_pipeline.py:154` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:15` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:16` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:17` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:18` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:19` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:20` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:33` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:34` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:35` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:38` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:40` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:41` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:44` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:62` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:63` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:65` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:80` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- `.\tests\test_quality_and_workspace.py:84` (B101) — Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- ... ve 6 bulgu daha (tam liste için JSON rapora bak)

## duplicate_code (jscpd)
- `quality_checker\checks\node_checks.py:91` — Kopya kod: quality_checker\checks\node_checks.py:91 <-> quality_checker\checks\python_checks.py:70
- `quality_checker\checks\python_checks.py:59` — Kopya kod: quality_checker\checks\python_checks.py:59 <-> quality_checker\checks\python_checks.py:156
