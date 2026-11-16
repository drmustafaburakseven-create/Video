# Günlük hareketli video otomasyonu

Yeni **karma akış**, 60 saniyeyi kısa hareketli çekimlerle oluşturur: başlangıç
hedefi **44 sn stok + 8 sn Gemini görüntüsü + 8 sn konuşan avatar**. ElevenLabs
klon sesi, altyazı ve kurgu tek bir 720×1280 MP4 dosyasında birleşir. Aynı dosya
YouTube Shorts ve Instagram Reels için kullanılır.

- **[Gemini’ye verilecek prompt](GEMINI_PROMPT.md)**
- **[Medya ekleme, avatar ve günlük üretim rehberi](HYBRID_GUIDE.md)**

İlk örnek `automation/drafts/ek-gida-hybrid.json` içindedir. Katalog şu anda
boştur; gerçek stok ve kullanıcı fotoğrafıyla hazırlanmış avatar klipleri
beklenmektedir. Hazır olmayan taslak günlük kuyruğa girmez. Önceki sekiz yeni
AI klipli örnek devre dışıdır (`enabled: false`). Avatar üreticisi bağlantısı
henüz kurulmamıştır; `--prepare` aynı sesin tam parçalarını dış hizmete teslim
etmek için çıkarır. Instagram Edits zorunlu değildir.

## İlk kurulum — şifre gerekmez

Depoda **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Gerekli mi? | Nereden alınır? |
|---|---|---|
| `GEMINI_API_KEY` | Yalnız yeni Gemini klibi üretilecekse | [Google AI Studio](https://aistudio.google.com/api-keys); projede video API erişimi ve uygun ücretlendirme gerekir. |
| `ELEVENLABS_API_KEY` | Evet | ElevenLabs API key; mevcut klon sese TTS erişimi olmalı. Bulut sohbetindeki secret, GitHub'a kendiliğinden taşınmaz. |
| `ANTHROPIC_API_KEY` | Hayır | [Anthropic Console](https://console.anthropic.com/); yalnız Claude sahne yönetmeni kullanılacaksa. |

**Gemini ve Claude web abonelikleri API bakiyesi değildir.** Şifre, oturum çerezi,
iki aşamalı doğrulama kodu veya tarayıcı girişini otomasyona kaydetmeyin.
Anahtarları kod, issue, çalışma günlüğü veya sohbet içine yapıştırmayın.

İlk ek gıda planı, kullanıcının daha önce ElevenLabs ile üretilmiş klon sesini
`automation/assets/ek-gida/` içinden kullanır. Bu plan için ElevenLabs anahtarı
gerekmez ve ses yeniden ücretlendirilmez. Ses kimliği, metin ve dosya özetleri
eşleşmelidir. Yeni anlatımlar için `ELEVENLABS_API_KEY` gereklidir; metin
değiştirildiğinde eski `prepared_voice` alanını kaldırıp yeni TTS kullanın.

İsteğe bağlı **Variables**:

| Variable | Varsayılan | Açıklama |
|---|---|---|
| `ELEVENLABS_VOICE_ID` | `allzfJXSadaum3SM2UFr` | Mustafa B. Seven klonu. |
| `VEO_MODEL` | `gemini-omni-1.2-flash` | Projenizin erişebildiği, sekiz saniyelik dikey video üreten Gemini API modeli. |
| `USE_CLAUDE_DIRECTOR` | `false` | Yalnız eski sekiz klipli akışta geçerlidir; karma akış ek Claude çağrısı yapmaz. |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Hesabın erişebildiği Anthropic modeli. |

İlk kontrol için **Actions → Daily motion video → Run workflow → validate_only**
seçilebilir; bu seçenek hiçbir sağlayıcı kredisi harcamaz.
Gerçek üretim için `validate_only` kapalı çalıştırın.
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

Her gün `automation/plans/*.json` dosyalarından alfabetik sırayla **etkin ve ilk
tamamlanmamış içerik** seçilir. Bir çalıştırmada en fazla bir içerik işlenir.
`enabled: false` olanlar atlanır. Medyası tamamlanan yeni planlar eklenmelidir;
Gemini web sohbeti kendiliğinden konu dosyası yüklemez. Hazır kuyruk boşsa işlem
ücretli çağrı yapmadan `queue_empty` ile biter; aynı video her gün tekrar üretilmez.

Bir planı elle seçmek için Run workflow içindeki `plan` alanına dosya adını
yazın. Karma şema ve hazırlık sırası [HYBRID_GUIDE.md](HYBRID_GUIDE.md) içindedir.
`--prepare` taslakları okuyabilir; normal günlük üretim yalnız `plans/` okur.

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
- Karma akışta tüm stok ve avatar dosyaları ücretli istekten önce kontrol edilir.
  Aynı metin + ses kimliği aynı ses kaydını; aynı model + prompt + kaynak süresi
  aynı Gemini işlem kimliğini kullanır. Görsel plan değişince ses yeniden alınmaz.
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
.venv-video/bin/python -m automation.pipeline --plan ek-gida-hybrid.json --prepare
```

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
