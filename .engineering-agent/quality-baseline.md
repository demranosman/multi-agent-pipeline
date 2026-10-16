# QUALITY BASELINE

Audit JSON: .engineering-agent/audit.json
Audit hash: ec12b5c8376e035f134047b964c6dd8e27a91b1633eef57ebde5a10834c35c8b
Proje: C:\Users\fikret\Desktop\multi-agent-pipeline
Tip: python
Genel durum: WARN

## Kontrol Özeti
- lint / ruff: WARN — 15 bulgu — 15 lint bulgusu
- type_check / mypy: PASS — 0 bulgu — 0 tip hatası
- security / bandit: WARN — 56 bulgu — 56 güvenlik bulgusu (0 yüksek riskli)
- dependency_audit / pip-audit: PASS — 0 bulgu — 0 bilinen zafiyetli bağımlılık
- dead_code / vulture: PASS — 0 bulgu — 0 kullanılmayan kod bulgusu
- duplicate_code / jscpd: PASS — 2 bulgu — Kod tekrarı %0.3

## Mimari Kullanım Kuralı
- Bu dosya yalnızca kalite baseline özetidir.
- Eksiksiz bulgu kaynağı `.engineering-agent/audit.json` dosyasıdır; `audit.md` özet/truncate edilebilir.
- Mimari kararlar sayıdan değil, ilgili bulgunun dosya/yol, satır, rule ve mesaj alanlarından türetilmelidir.
- İlgisiz bulguları mimariye taşımayın; yalnızca plan kapsamında etkilenen alanlarla ilişkili bulguları kararlarla eşleştirin.
