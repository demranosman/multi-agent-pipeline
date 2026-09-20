# Fikirden Pazarlamaya Ajan Hattı

Bir ürün/hizmet fikrini sırayla **araştırma → planlama → kodlama → test →
pazarlama** aşamalarından geçiren, her aşamada ayrı bir yapay zeka ajanının
çalıştığı bir FastAPI backend'i. Ajanlar birbirine düzeltme talebi
gönderebilir, soru sorup kullanıcıdan cevap bekleyebilir, her aşama
kullanıcı onayı gerektirecek şekilde ayarlanabilir.

## İçindekiler

- [Mimari](#mimari)
- [Kurulum](#kurulum)
- [Çalıştırma](#çalıştırma)
- [Testler (mock modu)](#testler-mock-modu)
- [Demo script'i](#demo-scripti)
- [API Uç Noktaları](#api-uç-noktaları)
- [Aşama Ayarları (stage-config)](#aşama-ayarları-stage-config)
- [Rapor Dışa Aktarma](#rapor-dışa-aktarma)
- [Bilinen Sınırlamalar](#bilinen-sınırlamalar)
- [Sorun Giderme](#sorun-giderme)
- [Proje Yapısı](#proje-yapısı)

---

## Mimari

Dört ana tablo üzerine kurulu:

| Tablo | Amaç |
|---|---|
| `pipelines` | Her fikir denemesinin ana kaydı - hangi aşamada, hangi durumda |
| `pipeline_logs` | Her aşamanın raporu. **Onaydan bağımsız, her zaman yazılır** |
| `agent_messages` | Ajanlar arası (veya kullanıcıdan gelen) düzeltme talebi / soru / cevap |
| `stage_configs` | Her aşamanın onay gerektirip gerektirmediği, hangi modeli kullandığı, etkin olup olmadığı |

**Pipeline durumları (`status`):**
- `running` - bir ajan şu an çalışıyor
- `waiting_approval` - aşama bitti, kullanıcı onayı bekleniyor
- `waiting_response` - bir ajan soru sordu, cevap bekleniyor
- `escalated` - aynı aşamada revizyon limiti aşıldı, kullanıcı karar vermeli
- `completed` - tüm aşamalar bitti

**Akış özeti:** Bir aşama çalışır → rapor loglanır (her zaman) → o aşamaya
yönelik bekleyen `blocking` bir mesaj varsa otomatik revizyon olarak işlenir
→ revizyon limiti aşıldıysa `escalated` → aşama soru sorduysa
`waiting_response` → aşama onay gerektiriyorsa `waiting_approval` →
gerektirmiyorsa otomatik bir sonraki aşamaya geçer.

Detaylı tasarım kararları için `orchestrator.py` içindeki docstring'lere
bakabilirsin - kod, üzerinde konuşulan mimariyi birebir yansıtıyor.

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

`.env.example` dosyasını `.env` olarak kopyala ve doldur:

```
ANTHROPIC_API_KEY=sk-ant-...

# Opsiyonel - SADECE üstteki anahtar belirli bir workspace'e bağlı DEĞİLSE gerekir
# ANTHROPIC_WORKSPACE_ID=wrkspc_...

# Opsiyonel - belirtilmezse ./pipeline.db (SQLite) kullanılır
# DATABASE_URL=postgresql://user:pass@localhost:5432/agent_pipeline
```

## Çalıştırma

```powershell
uvicorn main:app --reload
```

İlk çalıştırmada tablolar otomatik oluşturulur (`Base.metadata.create_all`,
ayrı bir migration adımı yok). API `http://localhost:8000` adresinde,
interaktif dokümantasyon `http://localhost:8000/docs` adresinde.

## Testler (mock modu)

```powershell
pytest tests/ -v
```

Bu testler **gerçek Anthropic API çağrısı yapmaz** - `orchestrator.AGENT_MAP`
sahte ajan fonksiyonlarıyla değiştirilir. API anahtarı ya da ağ bağlantısı
gerektirmeden orchestrator'ın mantığını (onay kapıları, revizyon döngüsü,
eskalasyon, soru-cevap akışı) doğrular. Kod üzerinde değişiklik yaptıktan
sonra önce bunları çalıştırmak, gerçek API'yi denemeden önce mantıksal
hataları yakalamanın en ucuz yolu.

## Demo Script'i

```powershell
python run_demo.py
```

Gerçek bir fikir girip pipeline'ı uçtan uca (gerçek API çağrılarıyla)
denemek için interaktif bir araç. Her aşamanın raporunu ekrana basar, onay
istediğinde Enter bekler, bir ajan soru sorarsa cevabını sorar, pipeline
tamamlandığında ya da duraklatıldığında raporu otomatik olarak
`pipeline_<id>.md` dosyasına kaydeder.

## API Uç Noktaları

| Metod & Yol | Açıklama |
|---|---|
| `POST /pipelines` | `{"idea_text": "..."}` ile yeni pipeline başlatır, research aşamasını hemen çalıştırır |
| `GET /pipelines/{id}` | Pipeline'ın güncel durumunu döndürür |
| `GET /pipelines/{id}/logs` | Tüm aşama raporları (JSON) |
| `GET /pipelines/{id}/report` | Tüm raporları tek bir Markdown dosyası olarak döndürür (indirilebilir) |
| `POST /pipelines/{id}/approve` | Mevcut aşamayı onaylar, bir sonraki aşamayı çalıştırır |
| `GET /pipelines/{id}/messages` | Ajanlar arası/kullanıcı mesajları (bekleyen sorular dahil) |
| `POST /pipelines/{id}/messages` | Bir aşamaya düzeltme talebi / öneri gönderir |
| `POST /pipelines/{id}/messages/{msg_id}/answer` | Bir ajanın sorduğu soruyu cevaplar |
| `POST /pipelines/{id}/rerun` | Mevcut aşamayı (bekleyen mesajları dikkate alarak) tekrar çalıştırır |
| `PUT /stage-config` | Aşama başına onay/model/etkinlik ayarlarını değiştirir (global varsayılan) |

Tüm gövde (body) şemaları için `http://localhost:8000/docs` en güncel
kaynak - kod değiştikçe burası da otomatik güncellenir.

## Aşama Ayarları (stage-config)

Her aşama için üç şey ayarlanabilir: onay gerekip gerekmediği
(`requires_approval`), hangi modelin kullanılacağı (`model`), ve aşamanın
tamamen devre dışı bırakılıp bırakılmayacağı (`enabled`).

```powershell
$body = @{
    stage = "coding"
    requires_approval = $true
    enabled = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/stage-config" -Method Put -Body $body -ContentType "application/json"
```

`enabled: false` yapılan bir aşama, ajanı hiç çağırmadan atlanır; `/logs` ve
`/report`'ta "devre dışı bırakıldığı için atlandı" notuyla görünür.

Varsayılan model eşlemesi (`orchestrator.py` içindeki `DEFAULT_MODELS`):

| Aşama | Varsayılan model | Gerekçe |
|---|---|---|
| research | claude-sonnet-5 | web arama + orta düzey sentez |
| planning | claude-opus-5 | yanlış mimari kararı pahalıya patlar |
| coding | claude-sonnet-5 | çoğu kodlama görevinde iyi denge |
| testing | claude-haiku-4-5-20251001 | görece basit, ucuz model yeterli |
| marketing | claude-sonnet-5 | yaratıcılık + tutarlılık dengesi |

## Rapor Dışa Aktarma

`GET /pipelines/{id}/report` tüm aşama raporlarını okunaklı bir Markdown
dokümanına çevirip indirilebilir dosya olarak döner (`reporting.py`).
`run_demo.py` bunu otomatik olarak yerel bir `.md` dosyasına kaydeder.

## Bilinen Sınırlamalar

- **`coding_agent`** kod üretir ama bir repo'ya yazmaz ya da çalıştırmaz.
  Üretimde `full_output["files"]` içeriğini gerçek bir sandbox/container'a
  yazman gerekir.
- **`testing_agent`** kodu gerçekten çalıştırmaz, statik inceleme yapıp test
  kodu önerir (`passed`/`failed` sayısı üretmez). Gerçek test çalıştırma
  için `generated_tests` içeriğini bir sandbox'ta çalıştırıp sonucu ayrı bir
  adımda eklemen gerekir.
- `coding`/`testing` aşamaları devre dışı bırakıldığında (`enabled: false`),
  `testing_agent` da devre dışıysa sorun yok; ama sadece `coding` devre
  dışı bırakılırsa `testing_agent` inceleyecek gerçek kod bulamaz - bu
  yüzden genelde ikisini birlikte açıp kapatmak mantıklı.

## Sorun Giderme

**`anthropic.BadRequestError: ... anthropic-workspace-id header gerekli`**
API anahtarın belirli bir workspace'e bağlı değil. En basit çözüm:
console.anthropic.com'da yeni bir anahtarı bir workspace içinde oluştur.
Alternatif: `.env`'e `ANTHROPIC_WORKSPACE_ID=wrkspc_...` ekle.

**`PermissionError: [WinError 32]` (pytest çalıştırırken)**
Windows'a özgü - önceki bir test çalıştırmasından kalan `.db` dosyası hâlâ
kilitli. `tests/conftest.py` her oturumda benzersiz bir dosya adı kullandığı
için bu artık oluşmamalı; yine de oluşursa proje klasöründeki
`_test_pipeline_*.db` dosyalarını elle silebilirsin.

**Yanıt `max_tokens` limitine takılıp yarıda kesiliyor**
`agents.py` içindeki ilgili `_call_structured_agent` çağrısında `max_tokens`
değerini artır. Not: Anthropic hesabının "tier"ına göre dakika başı çıktı
token limiti (OTPM) de var - çok yüksek bir `max_tokens` değeri, düşük
tier'larda `429 rate_limit_error`'a yol açabilir.

**Yeni eklenen bir `stage_configs` kolonu (`model`, `enabled` gibi)
bulunamıyor hatası**
Proje migration aracı kullanmıyor (`Base.metadata.create_all` sadece
eksik TABLOLARI oluşturur, mevcut bir tabloya yeni KOLON eklemez).
`pipeline.db` dosyasını silip sunucuyu yeniden başlat - tablo yeni şemayla
sıfırdan oluşur (geçmiş pipeline verisi kaybolur, geliştirme aşamasında
sorun olmamalı; üretimde gerçek bir migration aracı - ör. Alembic -
kullanman gerekir).

## Proje Yapısı

```
agent_pipeline/
├── main.py            # FastAPI endpoint'leri
├── orchestrator.py     # Aşama akışı, onay/revizyon/eskalasyon/soru-cevap mantığı
├── models.py           # SQLAlchemy tabloları
├── schemas.py           # Pydantic request/response şemaları
├── agents.py             # Her ajanın gerçek Anthropic API çağrısı
├── reporting.py           # JSON raporları Markdown'a çeviren yardımcı
├── database.py             # DB bağlantısı
├── run_demo.py              # İnteraktif uçtan uca deneme script'i
├── requirements.txt          # Üretim bağımlılıkları
├── requirements-dev.txt       # Test bağımlılıkları (pytest, httpx)
├── .env.example                # Ortam değişkeni şablonu
└── tests/
    ├── conftest.py              # pytest fixture'ları
    └── test_pipeline.py          # Mock ajanlarla uçtan uca testler
```
