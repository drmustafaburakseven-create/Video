# Günlük hareketli video otomasyonu

Bu akış **fotoğraf slaytı üretmez**. Gemini/Veo API ile sekiz hareketli klip üretir,
ElevenLabs'taki `Mustafa B. Seven` klon sesiyle birleştirir ve konuşmayla eşleşen
altyazılar ekler. İsteğe bağlı Claude aşaması sahne hareketlerini geliştirir;
tıbbi anlatımı değiştirmez. Çıktı 60 saniye, dikey 720×1280 H.264/AAC MP4'tür.

## İlk kurulum — şifre gerekmez

Depoda **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Gerekli mi? | Nereden alınır? |
|---|---|---|
| `GEMINI_API_KEY` | Evet | [Google AI Studio](https://aistudio.google.com/api-keys); projede Veo API erişimi ve uygun ücretlendirme gerekir. |
| `ELEVENLABS_API_KEY` | Evet | ElevenLabs API key; mevcut klon sese TTS erişimi olmalı. Bulut sohbetindeki secret, GitHub'a kendiliğinden taşınmaz. |
| `ANTHROPIC_API_KEY` | Hayır | [Anthropic Console](https://console.anthropic.com/); yalnız Claude sahne yönetmeni kullanılacaksa. |

**Gemini ve Claude web abonelikleri API bakiyesi değildir.** Şifre, oturum çerezi,
iki aşamalı doğrulama kodu veya tarayıcı girişini otomasyona kaydetmeyin.
Anahtarları kod, issue, çalışma günlüğü veya sohbet içine yapıştırmayın.

İsteğe bağlı **Variables**:

| Variable | Varsayılan | Açıklama |
|---|---|---|
| `ELEVENLABS_VOICE_ID` | `allzfJXSadaum3SM2UFr` | Mustafa B. Seven klonu. |
| `VEO_MODEL` | `veo-3.1-fast-generate-preview` | Projenizin erişebildiği, sekiz saniyelik dikey video üreten Gemini API modeli. |
| `USE_CLAUDE_DIRECTOR` | `false` | `true` ise Claude API anahtarı da gerekir. |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Hesabın erişebildiği Anthropic modeli. |

İlk kontrol için **Actions → Daily motion video → Run workflow → validate_only**
seçilebilir; bu seçenek hiçbir sağlayıcı kredisi harcamaz.
Gerçek üretim için `validate_only` kapalı çalıştırın.

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

Her gün `automation/plans/*.json` dosyalarından alfabetik sırayla **ilk
tamamlanmamış içerik** seçilir. Bir çalıştırmada en fazla bir içerik işlenir.
Başlangıç kuyruğunda kaynakları belirtilmiş `ek-gida-baslangic.json` vardır.
Her gün farklı içerik için aynı şemayla yeni plan dosyaları ekleyin. Kuyruk
tükenince işlem ücretli çağrı yapmadan `queue_empty` ile biter; aynı video
her gün yeniden üretilmez. Claude kendiliğinden yeni tıbbi anlatım yazmaz.

Bir planı elle seçmek için Run workflow içindeki `plan` alanına örneğin
`ek-gida-baslangic.json` yazın. Şema: `id`, `title`, `duration_seconds: 60`,
`narration`, `sources` ve sekiz adet `shots[].prompt`.

## Sonucu indirme

**Actions → Daily motion video → ilgili çalışma → Artifacts → motion-video-…**

ZIP içinde `video.mp4`, `captions.srt`, anlatım, kaynaklar, doğrulama raporu ve
kurtarma için ham klipler/ses bulunur. Artifact'ler 30 gün saklanır; kalıcı
arşiv için indirin. Sosyal medyada otomatik yayın yapılmaz.

## Maliyet ve yarıda kalma davranışı

- Her plan en fazla 8 × 8 saniyelik video üretimi, bir TTS isteği ve etkinse
  bir Claude isteği içerir. Bu **para limiti değil, istek/süre limitidir**;
  sağlayıcıların güncel ücretleri geçerlidir. Son videoda 60 saniye kullanılır.
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
- Plan, ses kimliği, Veo modeli veya Claude yönetmen ayarı değişirse yeni
  içerik kimliği oluşur ve yeni üretim ücretli olabilir.
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
.venv-video/bin/python -m automation.pipeline --plan ek-gida-baslangic.json
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
