# Fikirden Pazarlamaya Ajan Hattı & Web Dashboard

Bir ürün/hizmet fikrini sırayla **araştırma → planlama/mimari → kodlama → test & kalite güvence → pazarlama** aşamalarından geçiren; **Anthropic Claude, DeepSeek, Google Gemini ve OpenAI** modellerini destekleyen; üretilen kodları fiziksel çalışma alanına yazıp **Ruff, Mypy, Bandit, Vulture ve Pytest** ile gerçek testlerden geçiren çoklu yapay zeka ajan platformu.

Kullanıcılar süreci hem **modern Web Dashboard** üzerinden hem de **FastAPI REST API / CLI** ile yönetebilir.

---

## 🚀 Yeni Özellikler

1. **Modern Web Dashboard (`http://localhost:8000/dashboard`)**:
   - Fikir girip tek tıkla pipeline başlatma.
   - 5 aşamalı görsel ilerleme adımları (Stepper timeline).
   - Canlı durum rozetleri (`running`, `waiting_approval`, `waiting_response`, `escalated`, `completed`).
   - İnteraktif insan-döngüde butonları: **Aşamayı Onayla & İlerlet**, **Revizyon / Düzeltme İste**, **Ajan Sorusunu Yanıtla**.
   - Üretilen kodlar için dosya seçici ve yerleşik **Kod Görüntüleyici**.
   - Detaylı **Kod Kalitesi & Test Kartları** (Ruff, Mypy, Bandit, Pytest durumları ve bulgular tablosu).
2. **Çoklu LLM Desteği (`llm_gateway.py`)**:
   - **Anthropic Claude**: `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-4-5-20251001`
   - **DeepSeek**: `deepseek-v4-pro`, `deepseek-flash` (güçlü ve uygun maliyetli kodlama/akıl yürütme)
   - **Google Gemini**: `gemini-3.8-flash`, `gemini-3.1-pro-preview`, `gemini-3.7-flash`, `gemini-3.5-flash-lite`
   - **OpenAI**: `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna`
   - **Otomatik Fallback**: Birincil model kredi/limit/ağ hatası verirse, API anahtarı tanımlı diğer sağlayıcıların en üst modeli otomatik denenir. `LLM_FALLBACK_MODELS=model1,model2` ile elle ayarlanır.
   - Aşama bazında model seçimi yapılabilir (`/stage-config`).
3. **Fiziksel Çalışma Alanı (`workspace.py`)**:
   - `coding_agent` tarafından üretilen dosyalar `workspaces/<pipeline_id>/` dizinine fiziksel olarak kaydedilir.
   - Path traversal koruması ile güvenli dosya yönetimi.
4. **Gerçek Kod Kalitesi ve Test Motoru (`quality_checker/`)**:
   - Python kontrolleri: `ruff` (lint), `mypy` (tip kontrolü), `bandit` (güvenlik analizi), `pip-audit` (bağımlılık zafiyeti), `vulture` (ölü kod), `pytest` (test koşumu & coverage).
   - Node.js kontrolleri: `eslint`, `tsc`, `npm audit`, `depcheck`.
   - Ortak kontroller: `jscpd` (kopya kod tespiti).
   - **Self-Healing Döngüsü**: Test motoru kritik bir hata (`fail`) bulursa, otomatik olarak `coding_agent`'a düzeltme talebi (`blocking`) açılır.

---

## 🛠️ Kurulum

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

`.env.example` dosyasını `.env` olarak kopyalayın ve kullanacağınız sağlayıcı anahtar(lar)ını girin:

```env
# En az biri veya tercih ettiğiniz modeller için:
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-proj-...

# Opsiyonel - Veritabanı URL (varsayılan SQLite ./pipeline.db)
# DATABASE_URL=postgresql://user:pass@localhost:5432/agent_pipeline
```

---

## ▶️ Çalıştırma

### 1. Web Dashboard ile Çalıştırma (Önerilen)

```powershell
uvicorn main:app --reload
```

Tarayıcınızda açın:
👉 **`http://localhost:8000/dashboard`** veya **`http://localhost:8000`**

### 2. Terminal Demo Script'i

```powershell
python run_demo.py
```

---

## 🧪 Testler (Mock & Unit Testler)

Ağ bağlantısı veya gerçek API anahtarı gerektirmeden tüm orkestrasyonu, workspace yönetimini ve kalite denetim motorunu doğrulamak için:

```powershell
pytest tests/ -v
```

---

## 📡 API Uç Noktaları

| Metod & Yol | Açıklama |
|---|---|
| `GET /` veya `GET /dashboard` | Modern Web Dashboard kullanıcı arayüzü |
| `GET /models/catalog` | Desteklenen sağlayıcı ve model listesi |
| `GET /pipelines` | Tüm pipeline koşularını listeler |
| `POST /pipelines` | `{"idea_text": "..."}` ile yeni pipeline başlatır |
| `GET /pipelines/{id}` | Pipeline durumunu döndürür |
| `GET /pipelines/{id}/logs` | Aşama raporları ve test çıktıları (JSON) |
| `GET /pipelines/{id}/workspace/files` | Çalışma alanında üretilen dosyaları listeler |
| `GET /pipelines/{id}/report` | Nihai Markdown raporunu indirir |
| `POST /pipelines/{id}/approve` | Aşamayı onaylar ve sonrakini çalıştırır |
| `GET /pipelines/{id}/messages` | Ajan ve kullanıcı mesajları |
| `POST /pipelines/{id}/messages` | Düzeltme talebi / revizyon gönderir |
| `POST /pipelines/{id}/messages/{id}/answer` | Ajan sorusunu yanıtlar |
| `POST /pipelines/{id}/rerun` | Mevcut aşamayı tekrar çalıştırır |
| `PUT /stage-config` | Aşama başına model, onay ve etkinlik ayarları |

---

## ⚙️ Varsayılan Model Eşlemesi

| Aşama | Varsayılan Model | Alternatif Seçenekler | Gerekçe |
|---|---|---|---|
| **research** | `claude-sonnet-5-5` | `gemini-3.8-flash`, `gpt-6-luna` | Web arama + sentezleme yeteneği |
| **planning** | `claude-opus-5-5` | `gpt-6.1-sol`, `gemini-3.1-pro-preview` | Güçlü mimari akıl yürütme |
| **coding** | `deepseek-v4-pro` | `claude-sonnet-5-5`, `deepseek-flash` | Hızlı, ekonomik ve yetenekli kodlama |
| **testing** | `claude-haiku-4-5-20251001` | `gpt-6-luna` | Statik + dinamik sonuçları özetleme |
| **marketing** | `claude-sonnet-5-5` | `gpt-6-astra`, `gemini-3.8-flash` | Yaratıcı konumlandırma ve strateji |

---

## 📁 Proje Yapısı

```
multi-agent-pipeline/
├── main.py                     # FastAPI uygulaması ve Dashboard yönlendirmeleri
├── orchestrator.py              # Aşama akışı, onay/revizyon/eskalasyon mantığı
├── models.py                    # SQLAlchemy veri modelleri
├── schemas.py                   # Pydantic şemaları
├── agents.py                    # 5 Ajan tanımı (Research, Planning, Coding, Testing, Marketing)
├── llm_gateway.py               # Çoklu LLM sağlayıcı katmanı (Anthropic, DeepSeek, Gemini, OpenAI)
├── workspace.py                 # İzole fiziksel kod dizini yöneticisi (workspaces/<id>/)
├── reporting.py                 # Markdown raporlama servisi
├── quality_checker/             # Kod Kalitesi ve Test Motoru
│   ├── runner.py                # Sıralı kontrol çalıştırıcı
│   ├── models.py                # CheckResult, Issue, PipelineReport
│   ├── detector.py              # Python / Node.js proje tespiti
│   └── checks/                  # Ruff, Mypy, Bandit, Vulture, Pytest, Eslint, JSCPD
├── static/
│   └── index.html               # Modern, interaktif Web Dashboard arayüzü
├── run_demo.py                  # CLI interaktif istemcisi
├── requirements.txt             # Bağımlılıklar
├── requirements-dev.txt         # Test bağımlılıkları
├── .env.example                 # API anahtarı şablonu
└── tests/                       # Unit ve entegrasyon testleri
    ├── conftest.py
    ├── test_pipeline.py
    └── test_quality_and_workspace.py
```
