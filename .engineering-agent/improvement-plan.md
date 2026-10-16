# İyileştirme / Modernizasyon Planı

- **Proje:** `multi-agent-pipeline`
- **Temel alınan audit:** `.engineering-agent/audit.json` (hash `ec12b5c8…c35c8b`), genel durum **WARN**
- **Hedef:** Çalışan davranışı korunarak gürültünün temizlenmesi, gerçek sinyalin görünür olması, bağımlılık hijyeni.
- **Yaklaşım:** Big-bang rewrite yok. Aşamalı, her adımı doğrulanabilir küçük değişiklikler.

## Ön doğrulama (plan hazırlanırken ölçülen mevcut durum)

| Ölçüm | Komut | Sonuç |
|---|---|---|
| Test baseline | `.venv/Scripts/python.exe -m pytest -q` | **9 passed**, 1 deprecation uyarısı |
| Lint | `ruff check .` | 15 bulgu |
| Tip | `mypy .` | 0 |
| Bandit (audit komutu) | `bandit -r . -x <liste>` | 56 bulgu |
| Bandit (`-c pyproject.toml`) | `bandit … -c pyproject.toml` | **1 bulgu (B110)** |
| pip-audit | `pip-audit -r requirements.txt` | 0 zafiyet |
| vulture | — | 0 |
| jscpd | — | %0.3 (2 blok) |
| Uygulama importları | `import main, orchestrator, …` | Hepsi OK |

> Kritik tespit: `pyproject.toml` içindeki `[tool.bandit]` bölümü, audit'in kullandığı komut tarafından **okunmuyor**. Bu yüzden 56 bandit bulgusunun 55'i yapılandırma kaynaklı gürültü.

---

## 1. Bulgu Triyajı (audit bulguları otomatik "hata" sayılmadı)

| Bulgu | Sayı | Gerçek mi? | Karar / Gerekçe |
|---|---|---|---|
| `RUF059` unused `code` | 11 | Kozmetik | `code, out, err = run_command(...)` → dönüş kodları kullanılmıyor. Davranış aynı; `_` yapıldı. |
| `PIE810` startswith | 1 | Kozmetik | `startswith("FAILED") or startswith("ERROR")` → tuple. Davranış aynı. |
| `UP017` `timezone.utc` | 2 | Modernizasyon | Python ≥3.11 `datetime.UTC`. Davranış aynı. |
| `S110` try/except/pass | 1 | **Gerçek (düşük)** | `run_pytest_execution` kapsam JSON'u parse edilemezse sessizce yutuluyor. Hata `error` alanına yazılmalı. |
| `B110` try/except/pass | 1 | **Gerçek** | Yukarıdakiyle aynı satır (`python_checks.py:208`). |
| `B101` assert (testler) | 52 | Yanlış pozitif | Testlerde `assert` doğru kullanım. `pyproject` zaten `tests`'i hariç tutuyor; sorun komutun config'i okumaması. |
| `B105` hardcoded password `'pass'` | 1 | Yanlış pozitif | `Status.PASS = "pass"` enum değeri. |
| `B404` subprocess import | 1 | Kabul edilebilir | Zorunlu; `shell=False`, argüman listesi, timeout var. Skip listesinde. |
| `B603` subprocess call | 1 | Kabul edilebilir | Aynı şekilde; girdi `shutil.which` ile çözülen sabit araç listesi. |
| `jscpd` kopya blok | 2 (%0.3) | Kabul edilebilir | Araç kendi eşiğinde PASS; 3 satırlık ortak `run_command` + issue-parse deseni. Abstraksiyon erken olur. |
| `mypy` / `vulture` / `pip-audit` | 0 | — | Yapılacak yok. |

---

## 7. Uygulama Sonucu (bu tur)

| İş | Durum | Kanıt |
|---|---|---|
| P0-1 bandit `-c pyproject.toml` | ✅ | `run_bandit_security` 56 → **0** bulgu (P1-1 de düzeltildiği için gerçek B110 kalmadı) |
| P0-2 `pip-audit` requirements'a | ✅ | `requirements-dev.txt`'e eklendi; temiz venv'de artık SKIPPED olmayacak |
| P1-1 S110/B110 sessiz except | ✅ | `python_checks.py` kapsam parse hatası özete yazılıyor; bandit 0 |
| P1-2 lint temizliği | ✅ | `ruff check .` → **All checks passed** (15 → 0) |
| P2-1 bağımlılık hijyeni | ✅ | `openai` kaldırıldı; `httpx` tek dosyada; ruff/mypy/bandit/vulture dev'e taşındı; `pytest-cov`+`pip-audit` eklendi |
| P2-2 kod tekrarı | ✅ (aksiyon yok) | %0.3, eşik altı |
| P3 `pipeline_*.md` takipten çıkarma | ✅ | `.gitignore`'a `pipeline_*.md`; `git rm --cached` yapıldı |
| Regresyon testi | ✅ | `test_bandit_respects_pyproject_config` eklendi; `pytest` → **10 passed** |
| `pytest-cov` eksikliği (yeni) | ✅ | venv'e kurulunca `test_runner` pass, Kapsam %60.8 |

### 7.1 Plan dışı YENİ TESPİT — mypy sonucu güvenilmez (karar bekliyor)

Audit "mypy 0 tip hatası (PASS)" diyordu; bu **yanlış bir PASS**. İki ayrı sorun var:

1. **Araç çözümlemesi PATH'e bağlı:** `run_command` araçları `shutil.which` ile PATH'ten buluyor. Venv aktive edilmezse `mypy`/`pytest` global Python 3.13 kurulumundan geliyor. Global mypy, numpy stub'ında ölümcül hata (`rc=2`) verip projeyi hiç taramıyor → parser 0 bulgu yazıyor.
   - Ayrıca parser regex'i `^[^:]+:` ile sürücü harfli mutlak Windows yollarını (`C:\...`) **hiç eşleştiremiyor** — ayrı bir kör nokta.
2. **Gerçekten 30 tip hatası var:** venv mypy ile `mypy .` → 30 hata (SQLAlchemy 2.0 legacy `Column[...]` atamaları + `node_checks` `counts` anotasyonu).

**Seçenekler (henüz uygulanmadı):**
- **A (önerilen, ayrı iş):** `models.py`'yi `Mapped[...]` / `mapped_column` stiline taşı → 30 hatanın çoğu kalkar. ORM katmanına dokunur; testlerle doğrulanmalı.
- **B (hızlı):** Sorunlu modüllerde mypy'ı gevşet (`disallow_untyped_defs`/per-module ignore) — hatayı gizler, borç birikir.
- Her iki seçenekten bağımsız **C (✅ uygulandı):** `run_command`/`tool_available` artık önce proje venv'ini (`.venv/venv/env`, `Scripts|bin`) tercih ediyor; parser regex'i Windows mutlak yollarını (`C:\...`) eşleştiriyor.

### 7.2 C uygulama sonucu (kanıt)

```
find_tool('mypy', '.')  -> .venv\Scripts\mypy.EXE   (PATH değiştirilmeden)
run_pipeline:
  lint 0 · mypy 30 (FAIL, artık dürüst) · bandit 0 · pip-audit 0
  vulture 0 · test_runner pass (Kapsam %61.1) · jscpd %0.2 (1 blok)
pytest -> 11 passed
```

> C sonrası audit `OVERALL fail` döner; nedeni **gerçek 30 mypy hatası**. Yani denetim artık yalan söylemiyor. Kalan karar: A mı B mi?

### 7.3 A uygulama sonucu (✅)

`models.py` SQLAlchemy 2.0 stiline taşındı (`Column(...)` → `Mapped[...]` + `mapped_column(...)`), ve `database.py`'de `declarative_base()` → `class Base(DeclarativeBase)`.

**Neden `DeclarativeBase`?** SQLAlchemy 2.0'ın mypy plugin'i `declarative_base()` ile üretilen tabanlarda `__init__` sentezlemiyor (plugin kaynağında `__init__` üretimi yok; `Mapped[]` yalnızca nitelik tiplerini düzeltiyor). `DeclarativeBase` sınıfı `@dataclass_transform` taşıdığı için mypy `Pipeline(idea_text=...)` gibi kwargs'ları tip-güvenli sentezliyor. Üç ayrı ortamda doğrulandı (mypy 1.15 / 1.20 / 2.3.1 + SQLAlchemy 2.0.54). SQLAlchemy 2.1 plugin'i tamamen kaldırdığı için bu yön zaten ileriye dönük doğru adım.

**Ek düzeltmeler:** `orchestrator._build_context`'e `dict[str, Any]` anotasyonu; `node_checks.counts`'a `dict[str, int]`; `pyproject.toml`'a `plugins = ["sqlalchemy.ext.mypy.plugin"]`.

**Şema notu (risk):** `default=` taşıyan ama açıkça `nullable` belirtilmeyen kolonlar (`current_stage`, `status`, `severity`, `requires_response`, `requires_approval`, `max_revision_rounds`, `enabled`) `Mapped[T]` ile yeni veritabanlarında **NOT NULL** olur. Tüm yazımlar ORM + default üzerinden gittiği için davranış aynı; mevcut `pipeline.db` şeması `create_all` ile değişmez.

**Nihai denetim:**

```
lint 0 · type_check 0 · security 0 · dependency_audit 0
vulture 0 · test_runner pass (Kapsam %61.2) · jscpd %0.2
OVERALL: pass          pytest -> 11 passed          ruff -> All checks passed
```

### 7.4 P3 uygulama sonucu

**CI eklendi:** `.github/workflows/quality.yml` — `push` (main) + `pull_request` üzerinde Python 3.11 ile ruff, mypy, pytest, bandit, pip-audit. Yerelde tüm adımlar geçti:
`ruff OK · pytest 11 passed · bandit Medium/High 0 · pip-audit "No known vulnerabilities"`.

**Bandit tek kaynak:** CI artık yalnızca `bandit -c pyproject.toml -r .` çalıştırıyor (mükerrer `-x` listesi yok); projede bu komut 0 bulgu veriyor.

**Plugin kaldırıldı (A'nın sadeleşmesi):** `DeclarativeBase` + `Mapped[]` kombinasyonunda SQLAlchemy mypy plugin'i **gereksiz**. Doğrulandı: hem SQLAlchemy 2.0.54 hem 2.1.3, plugin olmadan mypy 0 hata (`User(id=.., name=..)` ve `reveal_type(u.name) == str`). Bu yüzden:
- `pyproject.toml`'dan `plugins = ["sqlalchemy.ext.mypy.plugin"]` kaldırıldı.
- `sqlalchemy>=2.0` üst sınırı **gerekmiyor**; SQLAlchemy 2.1 (plugin'i kaldırmış sürüm) ile de uyumluyuz.

**Lock/kilitleme: uygulanmadı (bilinçli).** Proje dağıtılmıyor, `pip-audit` 0 zafiyet ve bağımlılık `>=` aralıkları sorunsuz. uv/pip-compile iki ek dosya + yenileme yükü getirir (YAGNI). İstersen tek komutla eklenir:
`uv pip compile requirements.txt -o requirements.lock.txt`.

**Üretilen artifact temizliği:** P3 kapsamında yapıldı — `pipeline_*.md` git takibinden çıkarıldı, `.gitignore`'a `pipeline_*.md` ve `.coverage` eklendi.

---

## 8. Ürün Kalitesi Turu (güvenilirlik + çıktı kalitesi)

Denetim/CI turundan sonra asıl çalışma zamanı hata yolları sağlamlaştırıldı.

### 8.1 JSON ayrıştırma sertleştirme (agents.py)
- `_parse_json_output` artık code fence'i güvenli temizliyor (`json`/`JSON`), ve **sonucun dict olduğunu doğruluyor**; liste/sayı/dize gelirse `TypeError`.
- `_call_structured_agent` hem parse (`ValueError`) hem tip (`TypeError`) hatasını yakalayıp **çökmek yerine** ham çıktıyla özet dönüyor.
- Kapatılan gerçek hata: model geçerli ama nesne olmayan JSON döndürdüğünde `summarize()` içindeki `.get(...)` → `AttributeError` → API 500. Artık pipeline devam ediyor.

### 8.2 Ajan çıktı sözleşmeleri (yeni `agent_schemas.py`)
- 5 Pydantic modeli: `ResearchOutput`, `PlanningOutput`, `CodingOutput`, `TestingOutput`, `MarketingOutput` (+ `CodeFile`, `Finding`).
- Alanlar varsayılanlı ve `extra="allow"` — eksik alan varsayılana düşer, LLM'in ek alanları korunur. Yanlış tip şemaya uymazsa graceful hata.
- `_call_structured_agent` artık `schema=` alıp `model_validate(...).model_dump(exclude_none=True)` yapıyor. Alt ajanlara artık **tutarlı ve tip-güvenli** bir sözlük gidiyor.

### 8.3 Test kapsamı (mock'lu, ağ yok)
- `tests/test_llm_gateway.py`: katalog↔`detect_provider` tutarlılığı, bilinmeyen model fallback'i, `_call_openai_compatible` (başarı/no-choices/eksik anahtar/HTTP hatası), `call_llm` sağlayıcı yönlendirmeleri (anthropic/openai/deepseek+model eşleme/gemini), `_call_anthropic` (yalnız text blokları, workspace header).
- `tests/test_agents.py`: 5 ajanın mutlu yolu, `testing_agent`'ın 'fail' durumunda blocking bulgu zorlaması, LLM exception, `max_tokens` kesilmesi, revision note.

### 8.4 Sonuç (ürün kalitesi)

| Metrik | Önce | Sonra |
|---|---|---|
| Test sayısı | 11 | **44** |
| Test kapsamı | %61.2 | **%74.5** |
| Kod tekrarı | %0.2 | **%0.1** |
| Bilinen crash yolu (agent JSON) | 1 | **0** |
| Denetim | pass | **pass** |

### 8.5 Hâlâ açık (dürüst liste)
- Model adlarının gerçek API'de varlığı **doğrulanmadı** (katalog içi tutarlılık test edildi, canlı API değil). Canlı doğrulama için API anahtarlı isteğe bağlı smoke test eklenebilir.
- Retry/backoff/rate-limit yok; tek deneme.
- Bilinmeyen model adı sessizce Anthropic'e düşüyor (typoda yanlış sağlayıcıya gider) — farkındalık testi eklendi, davranış değiştirilmedi.
- API auth/CORS yok (yerel araç).

---

## 9. Model Kataloğu Güncellemesi (2026-10)

`PROVIDER_CATALOG` resmi sağlayıcı dokümanlarına göre en güncel üst modellere güncellendi. Emekli adlar kaldırıldı.

**Kaynaklar:** Anthropic Models overview · OpenAI Models / Using GPT-6 · Gemini API Models · DeepSeek Models & Pricing (fetch tarihi 2026-10).

| Sağlayıcı | Yeni modeller |
|---|---|
| Anthropic | `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-4-5-20251001` |
| OpenAI | `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna` |
| DeepSeek | `deepseek-v4-pro`, `deepseek-flash` (V4.1-Flash) |
| Gemini | `gemini-3.8-flash`, `gemini-3.1-pro-preview`, `gemini-3.7-flash`, `gemini-3.5-flash-lite` |

**Kaldırılanlar (emekli/artık sunulmuyor):** `claude-3-7-sonnet`, `claude-3-5-sonnet`, `deepseek-chat`, `deepseek-coder`, `deepseek-v3`, `deepseek-v4` (legacy adlar 2026-07-24'te kapatıldı), `gpt-4o*`, `o1`, `o3-mini`, `gemini-2.5-*`, `gemini-2.0-*`, `gemini-1.5-*`.

**Ek düzeltme:** `call_llm` içindeki `deepseek-v4`/`deepseek-coder` → `deepseek-coder` yeniden eşlemesi kaldırıldı; artık model adı olduğu gibi iletilir.

**Tutarlılık için güncellenen diğer yerler:** `orchestrator.DEFAULT_MODELS`, `agents.py` ajan varsayılanları, `static/index.html` (dashboard model listesi + varsayılanlar), `README.md` (iki liste), `tests/` (detect_provider + yönlendirme + anthropic testleri).

**Doğrulama:** 13 katalog modeli `detect_provider` ile doğru sağlayıcıya yönleniyor (test), `ruff` temiz, `mypy` 0, `pytest` 44 passed, denetim `OVERALL: pass`.

**Kısıt:** ID'ler resmi dokümanlardan alındı; canlı API ile son doğrulama (anahtar gerektirir) bu turun dışında bırakıldı. Sağlayıcılar model adlarını zamanla değiştirebilir — katalog bu yüzden tek yerde ve testle korunuyor.

---

## 10. Sağlayıcı Fallback'i (kredi/limit/ağ hatası)

**Problem:** `.env`'de anahtarlar var ama bazılarının kredisi bitmiş olabilir (401/402/429). Tek sağlayıcıya bağlı kalınca aşama boşa düşüyordu.

**Davranış:** `call_llm` artık birincil modeli dener; hata alırsa `fallback_models` zincirini sırayla dener. Hepsi başarısız olursa `RuntimeError` yükselir (mesajda tüm hatalar) — `_call_structured_agent` bunu yakalayıp graceful özet döndürür, pipeline çökmez.

**Fallback seçimi (`fallback_models`):**
- Farklı sağlayıcılardan, **kendi API anahtarı tanımlı** olanların en üst modeli (varsayılan `limit=2`).
- Aynı sağlayıcı atlanır: kredi tükenmesi hesap genelindedir; aynı sağlayıcının başka modeli de başarısız olur.
- `LLM_FALLBACK_MODELS=model1,model2` ile elle geçersiz kılınabilir.
- `provider_available()` strict: DeepSeek için yalnız `DEEPSEEK_API_KEY` (OPENAI anahtarıyla sayılmaz).

**Gözlemlenebilirlik:** Her başarısız aday `logging.warning` ile loglanır (“LLM çağrısı başarısız (X): … sıradaki aday deneniyor”).

**Dosyalar:** `llm_gateway.py` (`_dispatch_llm` + fallback'li `call_llm`, `provider_available`, `fallback_models`), `tests/test_llm_gateway.py` (5 yeni test), `.env.example` + `README.md` (knob belgelendi).

**Doğrulama:** `ruff` temiz · `mypy` 0 · `pytest` **49 passed** · kapsam %75.5 · `OVERALL: pass`. Testler: anahtar ayrımı, aynı-sağlayıcı atlama, env override, kredi hatasında yedeğe geçiş, tümü başarısızsa RuntimeError.

**Bilinçli atlanan (upgrade path):** fallback’te hangi modelin kullanıldığı şu an yalnız sunucu logunda; `PipelineLog.model` hâlâ istenen modeli gösteriyor. İstenirse `call_llm` 3-tuple döndürecek şekilde (`model_used`) genişletilip rapora yazılabilir.

**Yan gözlem (bu turda düzeltilmedi):** `.env`'de `WORKSPACE_ID` var; kod `ANTHROPIC_WORKSPACE_ID` okuyor — isim uyuşmadığı için o değer yok sayılıyor.

### 10.1 Fallback gözlemlenebilirliği (✅ uygulandı)

Önceki maddedeki “hangi modelin kullanıldığı yalnız logda” kısıtı kaldırıldı:

- `llm_gateway.call_llm_with_model(...)` → `(raw_text, stop_reason, model_used)`. `call_llm` geriye uyumlu sarmalayıcı olarak kaldı (2-tuple).
- `agents._call_structured_agent` her dönüşüne `model_used` ekliyor (başarı, max_tokens, parse/validation hatası; çağrı hiç başarılı olmazsa istenen model).
- `orchestrator.run_stage` → `PipelineLog(model=result.get("model_used") or model)`.
- Böylece Markdown raporu (`reporting.py`) ve dashboard (`static/index.html`) fallback'te **gerçek modeli** gösterir — ikisi de zaten `log.model` okuyor.

**Testler:** +4 (toplam **53**): `call_llm_with_model` birincil/fallback model raporlama, ajanın `model_used` döndürmesi, `PipelineLog.model`'e yansıması. Kapsam %75.9, `OVERALL: pass`. Vulture bir test lambda'sındaki kullanılmayan argümanı yakaladı ve düzeltildi.

> Bu başlık "mevcut çalışan davranışı koru / big-bang yapma" kapsamına girmediği için bu turda kodlanmadı; onay bekliyor.

---

## 2. Öncelikli Fazlar

### P0-1 — Bandit yapılandırmasının gerçekten uygulanması

- **Dosya:** `quality_checker/checks/python_checks.py` (`run_bandit_security`)
- **Gerekçe:** Audit, `[tool.bandit]` skip/exclude ayarlarını okumadığı için 55 yanlış pozitif üretiyor. Gerçek bulgu (B110) bu gürültünün içinde kayboluyor. Ayrıca `EXCLUDE_DIR_NAMES` ile `pyproject.exclude_dirs` iki ayrı kaynak; `tests`/`workspaces` yalnızca pyproject'te var.
- **Değişiklik (minimum):** Komuta, `pyproject.toml` mevcutsa `-c pyproject.toml` ekle. (Yoksa bugünkü davranış korunur.)
- **Etki:** Bandit bulgu sayısı 56 → **1** (ölçüldü). Audit çıktısı okunabilir hale gelir.
- **Risk:** Düşük. Yalnızca araç komut satırı değişir; uygulama kodu değişmez. `-c` yokluğunda fallback korunur.
- **Doğrulama:**
  ```bash
  .venv/Scripts/python.exe -c "from pathlib import Path; from quality_checker.checks.python_checks import run_bandit_security; r=run_bandit_security(Path('.')); print(r.issue_count, r.status)"
  # Beklenen: 1 warn
  ```
  + Regresyon testi: bandit sonucunda `B101`, `B105`, `B404`, `B603` **bulunmamalı**.
- **Geri dönüş:** `-c` argümanını kaldır.

### P0-2 — `pip-audit` bağımlılığının bildirilmesi

- **Dosya:** `requirements-dev.txt` (veya kalite araçlarıyla birlikte `requirements.txt`)
- **Gerekçe:** `quality_checker.run_pip_audit` bu aracı çalıştırıyor ama hiçbir requirements dosyasında yok. Proje `.venv`'inde kurulu değil (audit PASS'ı global Python'daki kurulumdan geliyor). Temiz ortamda kontrol sessizce **SKIPPED** olur.
- **Etki:** Bağımlılık denetimi her ortamda deterministik çalışır.
- **Risk:** Düşük. Sadece bağımlılık listesi.
- **Doğrulama:** Temiz venv → `pip install -r requirements-dev.txt` → `run_pip_audit` sonucu SKIPPED değil PASS/FAIL.
- **Not:** Bu, "kullanılmayan bağımlılık" değil, **eksik bağımlılık** kategorisindedir.

### P1-1 — Sessiz hata yutmanın kaldırılması (S110/B110)

- **Dosya:** `quality_checker/checks/python_checks.py:208` (`run_pytest_execution`, kapsam JSON parse)
- **Gerekçe:** `except Exception: pass` hata görünürlüğünü yok ediyor (proje kuralı: sessiz `except: pass` yasak). Kapsam okunamazsa `CheckResult.error` doldurulmalı.
- **Etki:** Kapsam parse hatası raporda görünür. Davranış: mevcut durumda zaten coverage bilgisi eklenmiyor — değişen tek şey görünürlük.
- **Risk:** Düşük. Yeni exception yolu yok; yalnızca mesaj kaydı.
- **Doğrulama:** Bozuk `.pipeline_coverage.json` ile birim testi → `result.error` dolu, test status'u eskisiyle aynı.
- **Not:** `except` yalnızca `json.JSONDecodeError/OSError`'a daraltılırsa `--cov` eksikliği gibi gerçek hatalar da yüzeye çıkar.

### P1-2 — Lint bulgularının temizlenmesi

- **Dosyalar:** `quality_checker/checks/node_checks.py` (5), `python_checks.py` (7), `shared_checks.py` (1), `quality_checker/models.py` (2)
- **Gerekçe:** 13× `code` → `_`, 1× `startswith` tuple, 2× `datetime.UTC`. Hepsi davranış-nötr.
- **Etki:** `ruff check .` → **0**. Gelecekteki gerçek lint bulguları görünür olur.
- **Risk:** Çok düşük (mekanik rename). `code` değişkeninin kullanıldığı `run_pytest_execution` **dokunulmaz**.
- **Doğrulama:** `ruff check .` (0) + `pytest -q` (9 passed) + `mypy .` (0).
- **Geri dönüş:** Mekanik; git revert.

### P2-1 — Bağımlılık hijyeni

Tek paket içinde gruplanır; hepsi ayrı ayrı doğrulanır.

| # | Değişiklik | Kategori | Gerekçe / Etki | Risk |
|---|---|---|---|---|
| a | `openai>=1.0` kaldırılsın mı? | **Kullanılmayan** | Hiçbir yerde import edilmiyor; `llm_gateway` OpenAI-uyumlu uçları `httpx` ile çağırıyor. Kurulum boyutu + saldırı yüzeyi azalır. | Düşük. **Karar sorusu (aşağıda).** |
| b | `httpx` yalnızca bir dosyada kalsın | Çift bildirim | `requirements.txt` ve `requirements-dev.txt`'te tekrarlı. | Çok düşük. |
| c | `ruff,mypy,bandit,vulture` → dev'e taşınsın | Konum hatası | Prod kurulumuna lint araçları girmemeli. | Düşük; README/CI kurulum adımları güncellenmeli. |
| d | `pytest-cov` bildirimi teyit edilsin | Eksik (dev) | `run_pytest_execution` `--cov` kullanıyor. | Çok düşük. |

- **Doğrulama:** Temiz venv'de `pip install -r requirements-dev.txt` sonrası `pytest` + `quality_checker` tam çalışır; `pip-audit -r requirements.txt` 0 zafiyet kalır.
- **Not:** `openai` kaldırılmadan önce `grep -rn "import openai" .` ile kanıtlanacak (şu an 0 sonuç).

### P2-2 — Kod tekrarı: **aksiyon yok**

- **Bulgu:** jscpd %0.3 (2 blok), aracın kendi PASS eşiğinin altında.
- **Değerlendirme:** Bloklar `run_command` dönüş yıkımı ve `file:line: mesaj` parse döngüsü. Ortak yardımcı çıkarmak 3 çağrı noktası için spekülatif soyutlama olur (YAGNI) ve P0-1/P1-2 zaten aynı satırlara dokunuyor.
- **Karar:** Şimdi yapılmaz. Tekrar oranı >%3'e çıkarsa yeniden değerlendirilir.

### P3-1 — Opsiyonel modernizasyon (karar bekliyor)

- **CI eklenmesi:** ruff + mypy + pytest + bandit + pip-audit adımları (GitHub Actions). Audit şu an manuel; asıl modernizasyon kazancı burada. *Ayrı iş kalemi.*
- **Lock/kilitleme:** `>=` alt sınırlar var, tam pin yok. `uv lock` veya `pip-compile` ile tekrarlanabilir kurulum. **Trade-off:** güncel güvenlik yamalarına otomatik kalmak vs. deterministik build. Hızlı hareket eden LLM SDK'ları nedeniyle şimdilik ertelemeye değer.
- **Üretilen artifact'lerin temizliği:** `pipeline_*.md` ve `pipeline.db` üretilen dosyalar; `.gitignore`'a girip git takibinden çıkarılmalı (`.db` zaten ignore, `.md` çıktıları takipte). Repo hijyeni.
- **Bandit için tek doğruluk kaynağı:** `-x` listesi ile `pyproject.exclude_dirs` çakışması P0-1'de giderilir; uzun vadede `EXCLUDE_DIR_NAMES`'i tek kaynak yapmak değerlendirilebilir.

---

## 3. Kategori Bazlı Özet

### Güvenlik
- **Gerçek ve düzeltilecek:** S110/B110 sessiz hata (P1-1).
- **Yapılandırma hatası (güvenlik raporunu bozan):** bandit config okunmuyor (P0-1).
- **Yanlış pozitif / kabul:** B101 (test), B105 (enum), B404/B603 (subprocess, shell yok).
- **Kapsamda taranan ve temiz çıkan:** `eval/exec/os.system/shell=True/md5` yok; SQLAlchemy ORM (raw SQL yok); workspace path traversal zaten guard'lı ve testli.
- **Kapsam dışı (bilinçli):** API'de kimlik doğrulama/CORS yok — yerel geliştirme aracı; üretime açılırsa ayrı iş.

### Bağımlılık sorunları
- 0 bilinen CVE (pip-audit).
- Alt sınır pinleme; lock yok → P3'te opsiyonel.
- `httpx` çift bildirim (P2-1b).

### Kullanılmayan / eksik bağımlılıklar
- **Kullanılmayan:** `openai` (kanıt: import yok) — karar sorusu.
- **Eksik:** `pip-audit` (kalite aracı), `pytest-cov` teyidi.
- **Yanlış konumda:** ruff/mypy/bandit/vulture prod requirements içinde.

### Kod tekrarı
- %0.3, eşik altı → **aksiyon yok**.

---

## 4. Kapsam Dışı (bu planda yapılmayacaklar)

- `quality_checker` mimarisinin yeniden yazımı / modül bölünmesi.
- Testlerdeki `assert`'lerin `pytest` dışına taşınması (B101 yanlış pozitif).
- `subprocess` kullanımının kaldırılması (B404/B603 — zorunlu ve güvenli).
- Uygulama API'sine auth/CORS eklenmesi (ayrı gereksinim).
- LLM SDK'larına geçiş (`openai`/`google-genai` SDK) — mevcut httpx yolu çalışıyor.

---

## 5. Tamamlanma Kriteri ve Doğrulama Stratejisi

Her faz sonunda aynı komut seti çalıştırılır:

```bash
.venv/Scripts/python.exe -m ruff check .                 # hedef: 0
.venv/Scripts/python.exe -m mypy .                        # hedef: 0
.venv/Scripts/python.exe -m pytest -q                     # hedef: >=9 passed
.venv/Scripts/python.exe -m bandit -r . -c pyproject.toml # hedef: 0 (P1-1 sonrası)
pip-audit -r requirements.txt                             # hedef: 0 zafiyet
```

Ardından audit yeniden çalıştırılır; `audit.json` hash'i değişir ve beklenen:
- lint: **0**
- security: **0** (B110 düzeltildikten sonra)
- dependency_audit: PASS (ve temiz ortamda SKIPPED olmaması)
- mypy/vulture: 0, jscpd: PASS

---

## 6. Kullanıcıdan Netleştirme Bekleyen Sorular

1. **`openai` paketi:** Şimdi kaldırılsın mı, yoksa SDK'ya geçiş planı var mı? (Varsayılan öneri: kaldır.)
2. **Lint araçları:** Prod `requirements.txt`'ten çıkarılıp dev'e taşınsın mı? (Varsayılan: taşı.)
3. **P3 CI:** Bu turda kapsama alınsın mı, ayrı iş mi? (Varsayılan: ayrı iş.)
4. **`pipeline_*.md` çıktıları:** Git takibinden çıkarılsın mı? (Varsayılan: evet.)
