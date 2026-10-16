# Plan: Faz Kapıları (Contract / Scope / Placeholder)

Durum: **UYGULANDI ✅** (2026-10) — onaylanan §3 tasarımı kodlandı.
Kapsam: `engineering-workflow.ts`'teki üç "kaymayı önleme" kapısını `multi-agent-pipeline`'ın kendi mimarisine (SQLAlchemy + orchestrator ajanları) uyarlamak.

### Uygulama sonucu

| Kapı | Durum | Kanıt |
|---|---|---|
| Contract hash | ✅ | `PipelineContract` tablosu + `approve_stage` snapshot + `run_stage` doğrulama |
| Scope | ✅ | `PlanningOutput.scope_patterns` + `gates.out_of_scope_files` |
| Placeholder | ✅ | `gates.scan_placeholders` + coding öncesi blok |

- Yeni: `gates.py`, `models.PipelineContract`, `tests/test_gates.py`.
- Değişen: `agent_schemas.py` (`scope_patterns`), `agents.py` (plan prompt'u), `orchestrator.py` (`_contract_violations`, `_snapshot_contract`, `_planning_scope_patterns`, `_coding_gate_violations`, `_block`), `tests/test_pipeline.py` (4 entegrasyon testi).
- **Sonuç:** `ruff` temiz · `mypy` 0 · `pytest` **63 passed** · kapsam **%77.9** · `OVERALL: pass`. `pipeline_contracts` tablosu mevcut DB'de `create_all` ile otomatik oluşuyor (migration gerekmedi).
- **Onaylanan kararlar:** contract deposu yeni tablo; bloklama `escalated` + insan override; salt `pass` placeholder; scope kaynağı `PlanningOutput.scope_patterns`; `back plan/architecture` bu turun dışında.

---

---

## 1. Gereksinim (kendi cümlelerimle)

Onaylanan planın/mimarinin sessizce değişmesini, coding ajanının onaylı kapsam dışına dosya üretmesini ve üretilen koda placeholder bırakılmasını **mekanik** olarak engelle. İnsan onayı son karar mercii olarak kalsın.

**Kabul kriterleri**
- KR-1: Bir aşama onaylandığında çıktısının hash'i saklanır; sonradan aynı aşamanın çıktısı değişir (rerun) ve yeniden onaylanmazsa ileri aşama çalışmaz.
- KR-2: Onaylı plandaki `scope_patterns` dışına çıkan coding dosyaları workspace'e yazılmaz ve pipeline bloklanır.
- KR-3: Coding çıktısındaki placeholder (`TODO`, `FIXME`, `NotImplementedError`, salt `pass`, `...`, "implement later") tespit edilirse aynı şekilde bloklanır.
- KR-4: Mevcut 53 test yeşil kalır; kapılar engelleme üretmediğinde akış **birebir** eskisi gibi çalışır.
- KR-5: Her kapı için birim + entegrasyon testi.

**Kapsam dışı**
- Yeni `BLOCKED` statüsü (öneri: mevcut `escalated` yeniden kullanılsın — §5).
- Git tabanlı kapsam kontrolü (projede git entegrasyonu yok; workspace'teki tek değişiklik zaten coding ajanının yazdığı dosyalar).
- Plan/mimari için ayrı `.md` doküman katmanı (proje JSON çıktı kullanıyor).
- `engineering-workflow.ts`'e dokunmak.

---

## 2. Mevcut akış ve müdahale noktaları

```
run_stage(stage):
  pending blocking mesaj? → revision_note
  result = agent_fn(...)                     ← kapılar burada değerlendirilir
  [coding] write_files_to_workspace(files)
  PipelineLog yaz
  revision limiti → escalated
  requires_approval → waiting_approval
  _advance() → sonraki aşama

approve_stage():                              ← contract snapshot burada alınır
  status ∈ {waiting_approval, escalated} → _advance()
```

- `full_output` zaten her aşamanın JSON çıktısını tutuyor (`PipelineLog.full_output`) → **contract = bu çıktının hash'lenmiş kopyası**.
- Workspace'e yalnızca coding ajanı yazar → **scope/placeholder kapıları coding aşamasına** bağlanır.
- Mevcut self-healing: `blocking` AgentMessage → sonraki `run_stage`'ta `revision_note` olur. Kapılar aynı kanalı kullanacak (yeni mekanizma icat edilmez).

---

## 3. Tasarım

### Kapı 1 — Contract hash (KR-1)

**Veri modeli:** yeni tablo `PipelineContract`
| kolon | tip | açıklama |
|---|---|---|
| id | str PK | gen_id |
| pipeline_id | str FK | pipelines.id, index |
| stage | SAEnum(StageName) | onaylanan aşama |
| source_log_id | str FK | hash'i alınan PipelineLog |
| content_hash | str | sha256(canonical json of full_output) |
| content | JSON | çıktının kopyası (denetim/rapor için) |
| created_at | datetime | utcnow |

- `Base.metadata.create_all` eksik tabloyu **oluşturur**; mevcut `pipeline.db` için migration gerekmez (kolon eklenmiyor).
- Aynı (pipeline_id, stage) için yeni onay satırı ekler (en son onay geçerli).

**Snapshot:** `approve_stage(db, pipeline)` içinde, onaylanan aşamanın **en son** `PipelineLog`'u bulunur, `content_hash` hesaplanır, satır upsert edilir; sonra `_advance`.

**Doğrulama:** `run_stage` başında, `stage != current_stage` olan tüm contract'lar için: ilgili aşamanın **en son** log'unun hash'i contract ile aynı mı?
- Farklı → `_block(...)`: `PipelineLog` yazılmaz, `pipeline.status = escalated`, `blocking` `correction_request` mesajı (kanal: mevcut AgentMessage) oluşturulur, ajan çalıştırılmaz.
- Aynı → normal akış.

**Neden "stage != current":** Onaylı bir aşamayı bilerek rerun etmek (`rerun_current_stage` / `answer_question`) serbest olmalı; ama rerun sonrası o aşama upstream'e dönünce hash tutmaz ve **yeniden onay** gerekir.

**Canonicalizasyon:** `json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)` → sha256.

### Kapı 2 — Scope (KR-2)

- `agent_schemas.PlanningOutput`'a `scope_patterns: list[str] = []` eklenir; `PLANNING_SYSTEM_PROMPT` "coding aşamasında izin verilen dosya/dizin desenleri" ister (örn. `app/*`, `tests/*`, `*.md`).
- Onaylı planın `scope_patterns` (contract content'inden) coding aşamasında referans alınır.
- `files[].path` her biri desenlerle eşleşmiyorsa ihlal. Desen→regex: `./` kırp, `*`→`.*`, `^...$`, case-insensitive (extension ile aynı).
- `scope_patterns` boşsa kapı **atlanır** (mevcut davranış korunur).

### Kapı 3 — Placeholder (KR-3)

- `gates.scan_placeholders(files)`: `TODO`, `FIXME`, `implement later`, `raise NotImplementedError`, satır tek başına `pass` / `...`, "coming soon".
- Yalnızca coding aşamasının ürettiği dosyalar taranır (workspace'e yazılmadan önce). `testing_agent.generated_tests` şu an diske yazılmadığı için kapsam dışı.

### Ortak bloklama davranışı
```
_apply_gates(stage, result, contract) -> violations[]
violations varsa:
  - dosyalar workspace'e YAZILMAZ (all-or-nothing)
  - PipelineLog yine yazılır (hata görünür olsun, summary'ye "KAPI: ..." eklenir)
  - pipeline.status = escalated
  - blocking correction_request AgentMessage (from_agent="gate", to_agent=f"{stage}_agent")
  - return pipeline   # _advance yok
```

---

## 4. Dosya bazlı değişiklik listesi

| Dosya | Değişiklik | ~ |
|---|---|---|
| `models.py` | `PipelineContract` modeli | +15 |
| `gates.py` (yeni) | `contract_hash()`, `check_contract()`, `scope_violations()`, `scan_placeholders()`, `pattern_to_regex()` — saf fonksiyonlar | +80 |
| `agent_schemas.py` | `PlanningOutput.scope_patterns` | +1 |
| `agents.py` | `PLANNING_SYSTEM_PROMPT`'a scope_patterns alanı | +2 |
| `orchestrator.py` | `approve_stage` snapshot; `run_stage` başında contract doğrulama; coding sonrası scope+placeholder; `_block()` yardımcısı | +50 |
| `tests/test_gates.py` (yeni) | saf fonksiyon testleri (hash, scope, placeholder) | +60 |
| `tests/test_pipeline.py` | contract stale→blok, scope ihlali→blok, placeholder→blok, mutlu yol | +60 |

Toplam ~270 satır; mimari değişimi yok, mevcut katmanlar korunur.

---

## 5. İki seçenek (trade-off)

**A. Contract deposu:** (a) yeni `PipelineContract` tablosu *(önerilen)* — çok aşamalı, sorgulanabilir, denetlenebilir. (b) `Pipeline`'a JSON kolonu — daha az satır ama tek/çok aşama ayrımı ve geçmiş yok.
→ **Öneri: (a).**

**B. Bloklama statüsü:** (a) mevcut `escalated` *(önerilen)* — yeni enum DB/şema/frontend değişikliği yok; `approve_stage` escalated'ı kabul ettiği için **insan açıkça override edebilir** (insan = son karar mercii, projenin felsefesi). (b) yeni `BLOCKED` statüsü — daha katı ama enum + `schemas.py` + `static/index.html` + DB enum değişikliği gerekir.
→ **Öneri: (a), bilinçli "override hakkı" ile.**

---

## 6. Davranış değişiklikleri ve riskler

| Risk | Etki | Önlem |
|---|---|---|
| Placeholder false-positive (ör. meşru `except: pass`) | Coding aşaması bloklanır | Salt-`pass` deseni yalnız satır tek başına `pass` ise; kullanıcı approve ile override edebilir |
| LLM `scope_patterns`'i yanlış/eksik üretir | Geçerli dosya bloklanır veya kapı atlanır | Boş→atla; desenler onaylı planın parçası, plan onayında görülür/ayarlanır |
| `full_output` non-deterministik (retry/fallback ile değişir) | Contract sürekli stale görünür | Hash yalnız **onay anındaki snapshot** ile karşılaştırılır; fallback aynı aşama içinde olur, onaydan sonra aşama yeniden çalışmadıkça hash değişmez |
| Yeni tablo mevcut DB'de yok | — | `create_all` eksik tabloyu oluşturur; doğrulanacak |
| `requires_approval=False` aşamalar | Contract alınmaz → KR-1 korumaz | Bilinçli: contract yalnız onaylanan aşamalar için; dokümante edilir |

---

## 7. Doğrulama planı

```bash
ruff check .            # 0
mypy .                  # 0
pytest -q               # >=53 + yeni testler
python -c "from pathlib import Path; from quality_checker.runner import run_pipeline; ..."  # OVERALL pass
```

Test senaryoları:
1. `contract_hash` aynı içerik→aynı hash, farklı içerik→farklı.
2. Scope: `app/*` deseni `app/main.py` geçer, `other/x.py` ihlal; boş desen→geç.
3. Placeholder: `TODO`, `NotImplementedError`, salt `pass`, `...` yakalanır; `password = "x"` yanlış pozitif vermez; `except: pass` → **karar**: satır salt `pass` değilse geç.
4. Entegrasyon: onayla→rerun (hash değişir)→ileri aşama bloklanır ve blocking mesaj oluşur.
5. Entegrasyon: coding mock'u kapsam dışı dosya döndürür → yazılmaz, `escalated`, mesaj var.
6. Entegrasyon: coding mock'u `TODO` içeren dosya döndürür → aynı.
7. Mutlu yol: mevcut `test_dashboard_and_files_endpoints` değişmeden geçer.

---

## 8. Onay için açık sorular

1. **Contract deposu** → yeni `PipelineContract` tablosu (öneri) mi, `Pipeline` JSON kolonu mu?
2. **Bloklama statüsü** → `escalated` + insan override (öneri) mi, yeni `BLOCKED` mı?
3. **Placeholder `pass`** → salt satır `pass` bloklansın mı (öneri), yoksa yalnız TODO/FIXME/NotImplementedError mu?
4. **Scope kaynağı** → `PlanningOutput.scope_patterns` (öneri) onaylandı mı, yoksa coding ajanı mı önersin?
5. Bu turda ayrıca **`back plan/architecture`** (upstream'e bilinçli dönüş + contract invalidasyonu) eklensin mi, yoksa ayrı iş mi?

Onay verirsen §3'teki tasarımı sırayla (model → gates.py → orchestrator → prompt/şema → testler) uygularım; her adımda ruff/mypy/pytest çıktısını gösteririm.
