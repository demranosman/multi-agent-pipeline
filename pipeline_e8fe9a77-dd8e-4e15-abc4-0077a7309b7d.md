# Pipeline Raporu

**Fikir:** Hikayeden senaryo ve devamında ses, resim ve video üretecek ve her aşamada mudahele edilebilecek sonuçta sosyal medyada kullanılabilecek ürün elde etmek için bir uygulama geliştirmek istiyorum.
**Pipeline ID:** `e8fe9a77-dd8e-4e15-abc4-0077a7309b7d`
**Durum:** completed
**Mevcut aşama:** marketing
**Oluşturulma:** 2026-09-20 09:28 UTC

---

## 🔍 Araştırma

*Uygulanabilirlik puanı 4/10, pazar ihtiyacı 'orta', 10 rakip tespit edildi.*

**feasibility_score**
4

**market_need**
orta

**difficulty**
yüksek

**target_customer**
Sosyal medya içerik üreticileri, faceless kanal sahipleri (TikTok/YouTube Shorts/Instagram Reels), küçük işletmeler ve pazarlamacılar - teknik/prodüksiyon bilgisi olmayan bireysel kullanıcılar

**competitors**
- Pictory.ai (Story to AI Video Generator) - hikayeyi sahne, ses ve görsele dönüştürüyor, olgun ürün
- Fliki.ai - 2000+ ses, çoklu AI model entegrasyonu, çok olgun
- CapCut AI Lab - hikaye oluşturucudan videoya tam pipeline, dev kullanıcı tabanı
- VEED.io - script-to-video, avatar ve TTS entegre, olgun
- Media.io AI Story Video Generator - script-aware ses, müzik, karakter tutarlılığı, storyboard düzenleme
- Novi AI - multi-scene story video, Seedance 2.0 entegrasyonu, Web/Android/iOS/PC
- Morphic - storyboard önizleme + tam render, sahne bazlı müdahale
- AI Story Video (aistory.video) - script->image->voice->video pipeline, TikTok/YouTube odaklı
- Pippit.ai - metin/medya/blog'dan hikaye videosu, marka/pazarlama odaklı
- HeyGen/Canva, Adobe Firefly, VisionStory - avatar ve sahne bazlı video üretimi

**key_risks**
- Pazar aşırı doymuş: her aşamada (senaryo->ses->görsel->video) müdahale imkanı sunan çok sayıda olgun rakip zaten mevcut
- Farklılaşma zor: mevcut oyuncular (Pictory, Fliki, CapCut, Media.io, Novi AI) zaten karakter tutarlılığı, sahne bazlı düzenleme ve çoklu model entegrasyonu sunuyor
- Yüksek altyapı maliyeti: LLM+TTS+görsel+video üretim modellerinin (Seedance, MiniMax, ElevenLabs vb.) entegrasyonu ve API maliyetleri operasyonel yükü artırır
- Kullanıcı edinme maliyeti yüksek: büyük oyuncuların marka bilinirliği ve ücretsiz katmanları var, yeni girişimcinin öne çıkması zor
- Video/görsel tutarlılığı (karakter, sahne sürekliliği) teknik olarak halen zorlu bir problem, kalite beklentisi yüksek
- Hızla değişen AI model ekosistemi (yeni video/ses modelleri) sürekli entegrasyon ve güncelleme gerektirir

**reasoning**
Bu fikir teknik olarak uygulanabilir ve gerçek bir kullanıcı talebi (faceless içerik üreticileri, sosyal medya pazarlamacıları) mevcut, ancak pazar zaten Pictory, Fliki, CapCut, Media.io, Novi AI gibi çok sayıda olgun ve her aşamada müdahaleye izin veren rakiple dolu. Yeni bir girişimin bu kalabalık pazarda öne çıkması için çok net bir niş farklılaşma (örneğin belirli bir dil/kültür, çok daha ucuz fiyatlandırma veya çok daha iyi karakter tutarlılığı) gerekecek, aksi halde sadece mevcut araçların bir kombinasyonu olacaktır.

---

## 🏗️ Planlama / Mimari

*Teknik plan hazır: stack belirtilmedi, tahmini süre 24 hafta, 8 milestone.*

**architecture_notes**
Next.js (React) tabanlı web istemcisi + Node/NestJS API Gateway; iş mantığı Python (FastAPI) orkestrasyon servisinde. Akış: Hikaye metni -> LLM ile sahne bazlı senaryo/storyboard JSON'u -> her sahne için paralel iş kuyruğu (BullMQ/Redis + Celery) ile TTS, görsel ve video üretimi -> FFmpeg render servisi ile birleştirme -> S3/R2 üzerinde CDN çıktısı. Proje durumu Postgres'te sahne-varlık (scene/asset) ilişkisel modeliyle versiyonlanır; her aşama regenerate edilebilir ve kullanıcı düzenlemesi yeni asset versiyonu olarak saklanır. Model sağlayıcıları soyutlanmış bir 'provider adapter' katmanı arkasında tutulur (model değişimi konfigürasyonla). Karakter tutarlılığı için referans görsel + karakter kütüphanesi (IP-Adapter/reference image) ve prompt şablonu yönetimi. WebSocket/SSE ile canlı ilerleme, Stripe ile kredi bazlı ödeme, maliyet takibi için her job'da token/saniye bazlı ölçüm.

**milestones**
- Ürün nişini netleştirme (Türkçe/yerel dil + faceless kanal şablonları) ve teknik PoC: metin->senaryo JSON şeması.
- Auth, proje/sahne veri modeli, kredi sistemi ve temel web arayüzü iskeleti.
- LLM senaryo üretimi + storyboard düzenleyici (sahne ekle/sil/yeniden yaz) MVP'si.
- TTS entegrasyonu: ses seçimi, sahne bazlı seslendirme, zamanlama ve yeniden üretim.
- Görsel üretim katmanı + karakter referans kütüphanesi ile tutarlılık mekanizması.
- Video üretimi (image-to-video) ve FFmpeg tabanlı render/altyazı/müzik birleştirme servisi.
- Dikey format şablonları, sosyal medya dışa aktarımı ve doğrudan paylaşım entegrasyonları.
- Kapalı beta, maliyet/kalite optimizasyonu, Stripe ile ücretli lansman.

**key_integrations**
- LLM: OpenAI GPT / Anthropic Claude (senaryo, sahne bölme, prompt üretimi)
- TTS: ElevenLabs veya Azure/Google TTS (çok dilli, klonlama)
- Görsel: Replicate/fal.ai üzerinden Flux, SDXL veya Google Imagen
- Video: Runway, Kling, MiniMax/Hailuo veya Seedance API (image-to-video)
- Depolama/CDN: AWS S3 veya Cloudflare R2 + CloudFront
- Ödeme: Stripe (kredi/abonelik) ve kullanım ölçümleme
- Kuyruk/altyapı: Redis + BullMQ/Celery, GPU gerekirse Modal veya RunPod
- Sosyal yayın: TikTok Content Posting API, YouTube Data API, Meta Graph API

**estimated_weeks**
24

**risks**
- Üçüncü parti video modeli API'lerinin gecikme, kota ve fiyat değişiklikleri maliyet öngörüsünü bozabilir.
- Sahneler arası karakter ve stil tutarlılığı hâlâ çözülmemiş bir problem; kalite beklentisi karşılanmayabilir.
- Uzun süren render işlerinde kuyruk yönetimi, hata toleransı ve kısmi yeniden üretim karmaşıklığı.
- Kullanıcı başına GPU/API maliyetinin abonelik fiyatını aşması (negatif birim ekonomi).
- Model sağlayıcılarının sık değişmesi nedeniyle sürekli adapter bakım yükü.
- Telif/lisans ve AI içerik etiketleme (platform politikaları) uyumluluk riski.
- Ses-görsel senkronizasyonu ve zamanlama hassasiyetinde FFmpeg pipeline hataları.
- Rakiplerin ücretsiz katmanları karşısında kullanıcı edinme maliyetinin sürdürülemez olması.

**reasoning**
Teknik olarak proje büyük ölçüde mevcut API'lerin orkestrasyonu olduğundan çekirdek zorluk model geliştirme değil, sahne bazlı versiyonlanabilir veri modeli, asenkron job orkestrasyonu ve maliyet kontrolüdür. Provider adapter soyutlaması, hızla değişen AI model ekosistemine karşı en kritik mimari korumadır. Pazar doygun olduğu için MVP'nin yatay bir 'her şeyi yapan' araç yerine dar bir niş (dil/format/şablon) üzerinden konumlandırılması ve 24 hafta içinde ücretli beta'ya çıkılması önerilir.

---

## 💻 Kodlama

*Bu aşama config üzerinden devre dışı bırakıldığı için atlandı.*

**skipped**
True

---

## 🧪 Test

*Statik inceleme tamamlandı: 0 bulgu (0 engelleyici), 0 test üretildi.*

**findings**
_(boş)_

**generated_tests**
_(boş)_

**recommended_action**
approve

**reasoning**
Verilen içerik bir kod dosyası değil, sadece `{"skipped": true}` şeklinde boş/atlanmış bir yapıdır. İncelenecek geçerli bir kod dosyası bulunmadığı için analiz yapılmamıştır.

---

## 📣 Pazarlama

*Pazarlama stratejisi hazır: Türkçe içerik üreticileri ve KOBİ'ler için, her üretim aşamasında (senaryo→ses→görsel→video) tam kontrol sunan, kültürel/dilsel doğallığı ve karakter tutarlılığını önceleyen, global rakiplerin İngilizce-merkezli ürünlerinden çok daha ucuz ve yerelleştirilmiş bir 'hikaye-to-video' stüdyosu. | 8 kanal, 6 kampanya fikri.*

**positioning**
Türkçe içerik üreticileri ve KOBİ'ler için, her üretim aşamasında (senaryo→ses→görsel→video) tam kontrol sunan, kültürel/dilsel doğallığı ve karakter tutarlılığını önceleyen, global rakiplerin İngilizce-merkezli ürünlerinden çok daha ucuz ve yerelleştirilmiş bir 'hikaye-to-video' stüdyosu.

**target_messaging**
Senaryonu yaz, sesini, görselini ve videonu Türkçe'nin doğal tonuyla, karakterin her sahnede aynı kalmasını sağlayarak, istediğin her adımda müdahale ederek dakikalar içinde üret — kamera, ekip ya da teknik bilgi olmadan.

**channels**
- TikTok (Türkiye faceless içerik üretici topluluğu)
- YouTube Shorts / YouTube (Türkçe eğitim ve demo videoları)
- Instagram Reels
- Discord/Telegram toplulukları (AI içerik üreticileri, YouTube otomasyon grupları)
- Reddit (r/artificial, Türkçe AI toplulukları)
- Product Hunt (global lansman için)
- Influencer iş birlikleri (küçük-orta ölçekli Türkçe faceless kanal sahipleri)
- SEO odaklı blog (yapayzekarehber.com, startupsole.com gibi sitelerin hedeflediği anahtar kelimeler: 'faceless kanal', 'AI video üretimi Türkçe')

**campaign_ideas**
- '7 Günde Faceless Kanal' challenge — kullanıcıların uygulamayla ürettiği içerikleri paylaşmasını teşvik eden, en iyi videoya ödül veren kampanya
- Ücretsiz 'Karakter Bible' şablonu kampanyası: Tutarlı karakterli hikaye serisi üretmek isteyenlere özel onboarding + ücretsiz kredi
- Türkçe TTS/aksan karşılaştırma içeriği: rakiplerin Türkçe seslendirme kalitesizliğini gösteren şeffaf 'yan yana' demo videoları
- Mikro-işletmeler için 'Ürününü Hikayeleştir' kampanyası — KOBİ'lere özel ücretsiz deneme ve şablonlar
- Her aşamada müdahale özelliğini öne çıkaran 'Sen Yönetmensin' içerik serisi: kullanıcının senaryo, ses, görsel seçimlerini canlı gösteren before/after içerikler
- Micro-influencer ortaklıklarıyla 'İlk 100 kullanıcı' özel erken erişim programı

**content_calendar_suggestion**
1. Hafta: Sorunu tanıtan içerikler (rakiplerin İngilizce-merkezli/pahalı olması, Türkçe TTS'in doğal olmaması) + ürün teaser'ları. 2. Hafta: Ürünün temel akışını gösteren demo videolar (senaryo→ses→görsel→video, her adımda müdahale örnekleri) + karakter tutarlılığı öne çıkan kısa klipler. 3. Hafta: Kullanıcı hikayeleri / erken erişim kullanıcılarının ürettiği içerikler, UGC teşviki, 'Sen Yönetmensin' serisi. 4. Hafta: Kampanya lansmanı (7 Günde Faceless Kanal challenge), Product Hunt / topluluk duyuruları, KOBİ odaklı vaka çalışmaları.

**reasoning**
Pazar araştırması, alanın çok kalabalık ve olgun rakiplerle dolu olduğunu, farklılaşmanın niş/dil/kültür veya fiyat üzerinden gelmesi gerektiğini gösteriyor; güncel trendler de 2026'da karakter tutarlılığının artık temel beklenti haline geldiğini ve Türkçe gibi dillerde TTS/aksan kalitesinin hâlâ zayıf bir nokta olduğunu doğruluyor. Bu nedenle konumlandırma, İngilizce-merkezli devasa rakiplerin göz ardı ettiği Türkçe-öncelikli, uygun fiyatlı ve 'insan dokunuşu/kontrol' vurgulu bir nişe odaklanarak hem doygun pazardan hem de YouTube'un düşük-efor otomasyon içeriğine karşı sıkılaşan politikalarından kaçınmayı hedefliyor.

---
