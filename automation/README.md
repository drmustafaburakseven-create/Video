# Günlük hareketli video otomasyonu

Varsayılan **studio akışı**, her gün beş kaynaklı konu önerisi ve bir seçilmiş
senaryo hazırlar; uygun girdiler varsa sizin ElevenLabs klon sesinizle bir
60 saniyelik dikey video üretir. Görüntü hedefi **52 sn uygun stok/önceden üretilmiş
ara çekim + 8 sn konuşan avatar**; yeterli kaynak yoksa **44 sn stok + 8 sn yeni
Gemini görüntüsü + 8 sn avatar** kullanılabilir. Aynı MP4, Reels ve Shorts için uygundur.

- **[Türkçe kullanım planı, güncel durum ve yaklaşık maliyet](DAILY_REELS_PLAN.md)**
- **[Çalışan Gemini + ElevenLabs avatar örneği](GEMINI_VOICE_GUIDE.md)**
- **[Gemini’ye verilecek prompt](GEMINI_PROMPT.md)**
- **[GitHub dışında sürekli çalışan sunucu kurulumu](WORKER.md)**
- **[Medya ekleme, avatar ve günlük üretim rehberi](HYBRID_GUIDE.md)**

**17 Kasım 2026 durumu:** kendi fotoğrafınızdan Gemini ile konuşan video
üretildi; konuşma ElevenLabs Voice Changer ile kendi klon sesinize çevrildi.
**60 saniyelik örnek artık dört saniyelik konuşan avatar içeriyor:**
`video-output/Ek-Gida-Mustafa-Avatarli-60sn.mp4`. Kalan 56 saniye lisanslı,
hareketli stok görüntülerden oluşuyor. Ayrıntılı doğrulama ve tekrar kullanım
[Gemini rehberinde](GEMINI_VOICE_GUIDE.md). Dosya yalnız bu çalışma alanında;
GitHub'a video veya özel portre yüklenmedi.

Fal ve ElevenLabs Aurora adaptörleri alternatif olarak kalır. Aktif Creator
hesabının ElevenLabs Flows video API'sindeki Pro gereksinimi, çalışan Voice
Changer yöntemiyle aynı özellik değildir. Fal anahtarı bu yeni yöntem için gerekmez.

GitHub Actions engeli ve kalıcı sunucu dağıtımı ayrı işlerdir; **günlük otomasyon
henüz canlı değil**. Kısa Gemini avatar komutu, eski studio'nun günlük üretim
yöntemini kendiliğinden değiştirmez. Gerçek 60 saniyelik örnek ayrıca birleştirildi.

## İlk kurulum — şifre gerekmez

Depoda **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Gerekli mi? | Nereden alınır? |
|---|---|---|
| `GEMINI_API_KEY` | Varsayılan günlük senaryo için; ayrıca yeni Gemini klibi gerekiyorsa | [Google AI Studio](https://aistudio.google.com/api-keys); video için uygun API erişimi/ücretlendirme gerekir. |
| `ELEVENLABS_API_KEY` | Evet | ElevenLabs API key; mevcut klon sese TTS erişimi olmalı. Bulut sohbetindeki secret, GitHub'a kendiliğinden taşınmaz. |
| `FAL_KEY` | Fal ile yeni avatar için | [fal.ai](https://fal.ai/); görüntü ve mevcut sesle Aurora üretimi, kullanım başına ücretli. |
| `AVATAR_PORTRAIT_BASE64` | GitHub runner'da avatar için | Kompakt JPG/PNG fotoğrafının base64 biçimi; kodlanmış metin en fazla 48 KiB, özgün dosya en fazla 36 KiB, her kenar en az 256 piksel. Fotoğraf geldikten sonra uygun kopya hazırlanır. |
| `ANTHROPIC_API_KEY` | Hayır | [Anthropic Console](https://console.anthropic.com/); editoryal sağlayıcı Claude seçilirse gerekir. |
| `PEXELS_API_KEY` | Hayır | [Pexels API](https://www.pexels.com/api/); sonraki stok aramaları için. İlk örneğin kamuya açık klipleri anahtarsız edinildi. |

**Gemini ve Claude web abonelikleri API bakiyesi değildir.** Şifre, oturum çerezi,
iki aşamalı doğrulama kodu veya tarayıcı girişini otomasyona kaydetmeyin.
Anahtarları kod, issue, çalışma günlüğü veya sohbet içine yapıştırmayın.

GitHub secret boyut sınırı yalnız bu aktarım yöntemine aittir. Kalıcı özel
çalıştırıcıda portre dosyası en fazla 25 MB olabilir; yüksek kaliteli özgün
fotoğraf için bu yol tercih edilebilir. Portreyi public Git deposuna veya
indirme artifact'lerine eklemeyin. GitHub yöntemi fotoğrafı runner'ın geçici,
özel dizinine açar.

İlk ek gıda planı, kullanıcının daha önce ElevenLabs ile üretilmiş klon sesini
`automation/assets/ek-gida/` içinden kullanır. Bu plan için ElevenLabs anahtarı
gerekmez ve ses yeniden ücretlendirilmez. Ses kimliği, metin ve dosya özetleri
eşleşmelidir. Yeni anlatımlar için `ELEVENLABS_API_KEY` gereklidir; metin
değiştirildiğinde eski `prepared_voice` alanını kaldırıp yeni TTS kullanın.

İsteğe bağlı **Variables**:

| Variable | Varsayılan | Açıklama |
|---|---|---|
| `ELEVENLABS_VOICE_ID` | `allzfJXSadaum3SM2UFr` | Mustafa B. Seven klonu. |
| `EDITORIAL_PROVIDER` | `gemini` | Günlük senaryo için `gemini` veya `claude`. Yerel Claude Code oturumu GitHub runner'a taşınmaz. |
| `VEO_MODEL` | `gemini-omni-1.2-flash` | Projenizin erişebildiği, sekiz saniyelik dikey video üreten Gemini API modeli. |
| `USE_CLAUDE_DIRECTOR` | `false` | Yalnız eski sekiz klipli akışta geçerlidir; karma akış ek Claude çağrısı yapmaz. |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Hesabın erişebildiği Anthropic modeli. |

Actions etkinleştirildikten sonra ilk kontrol için **Actions → Daily motion video → Run workflow → validate_only**
seçilebilir; bu seçenek hiçbir sağlayıcı kredisi harcamaz.
Varsayılan studio için `plan` boş, `validate_only` kapalı ve `avatar_provider: fal`
olmalı. `editorial_only` yalnız öneri/senaryo üretir; bu, tıbbi onay veya bitmiş
video değildir. Fotoğraf ve uygun stok eksikse studio `needs_inputs` durumuyla
durur; yeni ses/avatar/video satın almaz. Editoryal taslak bir kez üretilip saklanabilir.
Yalnız avatar hazırlığı için `plan: ek-gida-hybrid.json` ve `prepare_only: true`
seçin. Eşleşen ses kaydı olmayan yeni metinlerde bu işlem TTS kredisi kullanır.

Git üzerinden açıkça üretim başlatmak için `render-video-` ile başlayan benzersiz
bir etiket gönderilebilir. Bu da aynı kuyruk ve tekrar ücretlendirme korumasını
kullanır; sıradan kod push'ları ücretli üretim başlatmaz. Son çalışmanın anahtar
içermeyen durum özeti `video-automation-state` dalındaki
`.video-state/latest-run.json` dosyasına da yazılır.

## Her gün 09.00 Türkiye saati

`daily-video.yml` içindeki `0 6 * * *`, Türkiye saatiyle 09.00'dır.
GitHub'ın zamanlanmış çalıştırmaları yoğunlukta gecikebilir; kesin dakikada
başlama garantisi yoktur. Schedule yalnız varsayılan dalda çalışır.
Fork depolarında Actions/scheduled workflows kapalıysa Actions sekmesinden
etkinleştirin. GitHub'ın uzun süre etkinlik görmeyen public depolar için
uyguladığı zamanlama kısıtları da geçerlidir.

Plan belirtilmeyen günlük çalışma **studio** yolunu kullanır: 12 başlıklı,
resmî kaynaklarla desteklenmiş havuzdan beş öneri, bir seçilmiş senaryo ve
girdiler tamamlanmışsa bir video. Bu sınırsız yeni gündem keşfi değildir.
Yeni günlerde ilgili konunun yeterli, uygun stok görüntüsü yoksa üretim durur;
medya kataloğunun o konu için tamamlanması gerekir. Gemini 3.5 Flash-Lite ile
canlı metin üretimi doğrulandı. Claude Code bu bulut ortamında kurulu ancak
oturumu açık değil; Claude API anahtarı da mevcut yerel ortamda yok.

Bir planı elle seçmek için Run workflow içindeki `plan` alanına dosya adını
yazın; bu **eski pipeline** yoludur. Eski pipeline plans kuyruğunda alfabetik
sırayla etkin ve ilk tamamlanmamış içeriği işler; boşsa `queue_empty` döner,
`enabled: false` olanları atlar. `--prepare` taslakları okuyabilir.
Karma şema ve hazırlık sırası [HYBRID_GUIDE.md](HYBRID_GUIDE.md) içindedir.

## Sonucu indirme

**Actions → Daily motion video → ilgili çalışma → Artifacts → motion-video-…**

ZIP içinde `video.mp4`, `captions.srt`, anlatım, kaynaklar, doğrulama raporu ve
kurtarma için ham klipler/ses bulunur. Artifact'ler 30 gün saklanır; kalıcı
arşiv için indirin. Sosyal medyada otomatik yayın yapılmaz.

## Maliyet ve yarıda kalma davranışı

- Karma planda yeni Gemini kaynakları en fazla 16 saniye, avatar gösterimi
  en fazla 12 saniyedir. Varsayılan tek 8 saniyelik yeni kliptir. Stok/önceden
  üretilmiş medya yeniden kullanılabilir. Bu **para limiti değil, süre limitidir**;
  sağlayıcıların güncel ücretleri geçerlidir.
- Studio/produce akışında fotoğraf ve gerekli stok dosyaları, yeni ses/avatar/video
  isteklerinden önce kontrol edilir. Eski pipeline hazır avatar dosyası bekler;
  `produce` desteklenen sağlayıcıyla avatar oluşturabilir.
  Aynı metin + ses kimliği aynı ses kaydını; aynı model + prompt + kaynak süresi
  aynı Gemini işlem kimliğini kullanır. Görsel plan değişince ses yeniden alınmaz.
- Avatar isteği fotoğraf özeti, tam ses dilimi özeti ve sağlayıcı/model bilgisiyle
  kaydedilir. Kabul edilmiş iş zaman aşımında yeniden satın alınmaz; aynı iş
  sorgulanır. Belirsiz gönderim otomatik tekrarlanmaz. İki ayrı yerel süreç de
  dosya kilidi ve güncel kayıt okumasıyla aynı ücretli işlemi çoğaltamaz.
- Eski, devre dışı sekiz klipli biçim etkinleştirilirse 8 × 8 saniye üretim
  ve isteğe bağlı Claude çağrısı yapabilir; ekonomik karma şemayı kullanın.
- `video-automation-state` dalı, her ücretli işlemden **önce** niyeti, kabulden
  sonra işlem kimliğini kaydeder. Bitmiş içerik tekrar ücretlendirilmez.
- Ses yanıtı ve hizalaması bu dalda tutulur; sonraki GitHub runner aynı sesi
  yeniden satın almaz. Bu dal kaynak anahtarları veya oturum bilgileri içermez.
- Veo işi sürüyorsa yeniden çalıştırma aynı işlem kimliğini sorgular. Zaman
  aşımıyla kabul durumu belirsiz kalan istek otomatik gönderilmez.
- Sağlayıcı eski video dosyasını artık sunmuyorsa Artifacts içindeki ham
  kliplerle yerel kurtarma yapın. Kayıtları silerek körlemesine yeniden üretim
  yaptırmayın. Model reddi veya moderasyon sonucunda başka modelle sessiz
  deneme yapılmaz.
- Metin, ses kimliği veya üretim promptu/modeli değişirse yeni üretim ücretli olabilir.
  Hazırlanmış avatar yeni ses/metinle otomatik eşleşmiş sayılmaz.
- Bu state dalını silmek, tamamlanmış içerik hafızasını kaybettirir. Dalı
  koruyun. Workflow'a bu dala yazma yetkisi engellenirse ücretli çağrıdan önce
  durur. Workflow concurrency, aynı anda iki üretim yapılmasını önler.

API izinleri/ücretlendirme ve gerçek Veo görüntü kalitesi, yerel çevrimdışı
testlerle doğrulanmış sayılmaz. Bebek/insan üretimi sağlayıcıya, ülkeye ve
modele göre kısıtlanabilir; ret halinde plan bildirilir ve işlem durur.

## Yerel kurulum ve doğrulama

```bash
python -m venv .venv-video
.venv-video/bin/python -m pip install -r automation/requirements.txt
# Sisteminizde FFmpeg/FFprobe ve DejaVu Sans fontu da kurulu olmalı.
.venv-video/bin/python -m automation.pipeline --validate
.venv-video/bin/python -m unittest discover -s automation/tests -v
```

Güvenli ortam değişkenleri tanımlandıktan sonra:

```bash
# Günlük öneriler ve tek senaryo; henüz video oluşturmaz.
.venv-video/bin/python -m automation.studio --editorial-only
# Fotoğraf ve konuya uygun stoklar tamamlanmışsa tam üretim.
.venv-video/bin/python -m automation.studio --portrait /guvenli/dizin/fotograf.jpg --avatar-provider fal
# Önceden hazırlanmış bir plan için avatar dahil üretim.
.venv-video/bin/python -m automation.produce --plan ek-gida-hybrid.json --portrait /guvenli/dizin/fotograf.jpg --avatar-provider fal
# Eski akış: yalnız mevcut planın ses/avatar hazırlık dosyalarını çıkarır.
.venv-video/bin/python -m automation.pipeline --plan ek-gida-hybrid.json --prepare
```

Yerelde `AVATAR_PORTRAIT_PATH` verilmişse studio için `--portrait` gerekli değildir.
`automation.daily` yalnız editoryal üretim, `automation.studio` günlük orkestrasyon,
`automation.produce` ise planın gerçek medya üretimi ve birleştirilmesi içindir.
`--provider claude-cli` yalnız kimliği doğrulanmış yerel Claude Code kurulumu ile
kullanılabilir; web aboneliği veya kurulu CLI tek başına açık oturum demek değildir.

Yerel modda `video-output/journal/` aynı tekrar-ücretlendirme korumasını sağlar.
Bu klasörü ve dönen API işlem kimliklerini koruyun. Anahtar değerleri komut
satırı argümanı olarak verilmez. `video-output/` Git tarafından yok sayılır.

## Doğrulama kapsamı

`video-automation-checks.yml` anahtarsız testleri çalıştırır: belirsiz ücretli
isteğin tekrar edilmemesi, kalıcı kayıt hatasında isteğin gönderilmemesi,
tamamlanan kuyruğun ücretlendirilmemesi, hata mesajlarında credential
sızdırılmaması ve FFmpeg ile hareketli test kaynağından 60 saniyelik gerçek
kodlama/çözme kontrolü. Test deseni nihai hasta eğitim videosu olarak sunulmaz.

## Kasım 2026 model güncellemesi

Google, Veo 3.1 Preview Gemini API modellerini 22 Ekim 2026 tarihinde kapattı.
Varsayılan video üretimi artık `gemini-omni-1.2-flash` ile Interactions API
üzerinden yapılır. API model listesinde bu model doğrulandı. `VEO_MODEL` değişken
adı geriye uyumluluk için korunur; daha önce eski modelle doldurduysanız
`gemini-omni-1.2-flash` olarak güncelleyin veya varsayılan için silin.
Kaynak: https://ai.google.dev/gemini-api/docs/video ve https://ai.google.dev/gemini-api/docs/omni
