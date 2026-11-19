# Higgsfield + ElevenLabs üretimi

Güncel seçim: yalnız doktorun giriş/kapanış görüntüsü Higgsfield'de; doktorun
kendi klonu, kamera arkasındaki ayrı kadın sesi ve ara anlatım ElevenLabs'te.
İncelenmiş hareketli ara görüntüler yeniden kullanılabilir. Kurgu yerelde yapılır.

## Bu oturumda doğrulanan durum — 19 Kasım 2026

- Kullanıcının yeniden seçtiği açık mavi gömlekli özgün fotoğraf özel referans
  dosyasına alındı. Fotoğraf, sesler ve üretim kayıtları public Git'e eklenmez.
- ElevenLabs mevcut doktor klonuna ve v3/v4 modellerine erişim doğrulandı.
- Vitamin/sebze örneği için yeni giriş/kapanış sesi, üç mevcut kadın seçeneği,
  seçilmiş soru, 60 saniyelik miks, altyazı zamanları ve beş farklı hareketli
  ara kaynak hazırlandı. Konuşma hızlandırılmadı; son kelime 58,1 saniyede biter.
- Resmi Higgsfield CLI 1.2.2 kuruldu; yayımlanan SHA-256 ile doğrulandı.
- Kullanıcı ChatGPT bağlantısını tamamladığını bildirdi. Buna rağmen bu Codex
  görevinde Higgsfield MCP araçları görünmüyor ve CLI'nin bulut hesabı/çalışma
  alanı bağlı değil. Gerçek fiyat sorgusu bu noktada durdu.
- **Yeni Higgsfield avatarı ve bitmiş yeni Reels henüz yok.** Yerel testlerin
  geçmesi, sağlayıcı erişiminin veya canlı günlük üç üretimin doğrulanması değildir.

## İki ses/görüntü yolu

1. **Önce ElevenLabs, sonra fotoğraf + ses:** Ölçülmüş 15 saniyelik doktor WAV'ı
   Higgsfield'in harici ses kabul eden modeline verilir. Giriş WAV'ının ilk altı
   saniyesi sessizdir. Kadın sorusu yalnız son miksin ayrı kanalına girer; böylece
   doktor kadın cümlesini ağzıyla söylemez. Model gerçek çıktıdan ayrıca incelenir.
2. **Higgsfield doğal performansı → ElevenLabs Voice Changer:** Model yerel
   konuşma oluşturduğunda aynı performans klon sese dönüştürülür. Ses ve görüntü
   aynı başlangıç noktasında kalır. Başka zamanlamalı TTS sonradan üzerine konmaz.

`higgsfield_avatar.py` iki yolu da destekler. `higgsfield_episode.py` iki avatar
işini yönetir; doğrulanmış klipler, mevcut stok/miks/grafikler ve iki platformun
metinleriyle 60 saniyelik kurguyu oluşturur. Yeni avatarın yüz/eller/dudak
incelemesi dosya hash'iyle kaydedilir. Kayıt olmadan eski klip yeni diye kullanılmaz.

## Bağlantı ve model seçimi

[Resmi CLI](https://github.com/higgsfield-ai/cli) ve
[resmi bağlantı sayfası](https://higgsfield.ai/mcp) kullanılır. CLI için aynı
üretim makinesinde `higgsfield auth login` ile oturum açılır, `higgsfield workspace
list` ve `higgsfield workspace set <id>` ile kullanıcının hesabı seçilir. Token
çıktısı sohbete, public depoya veya Actions günlüğüne yazılmaz. ChatGPT'deki bir
uygulama bağlantısının GitHub Actions'a veya bu CLI'ye aktarıldığı varsayılmaz.

`higgsfield model list --video --json` ve `higgsfield model get MODEL --json`
gerçek katalog ve parametreleri verir. Fotoğraf/ses girişi ile 15 saniyelik çıkış
desteklenmeli. Örnek paketteki `wan2_6`, resmi CLI belgesinde bu girdileri
destekleyen **fiyatı/hesap erişimi henüz doğrulanmamış adaydır**. En ucuz veya
ücretsiz olduğu iddia edilmez. [Lipsync Studio](https://higgsfield.ai/lipsync-studio)
web arayüzü ayrıca fotoğraf/video ve yüklenen sesle üretim sunar; web'deki her
modelin CLI'de de bulunduğu varsayılmaz.

## Maliyet kuralları

- Profil: `profiles/higgsfield-elevenlabs.json`. Bölüm başına iki yeni avatar
  üretimi; ara görüntüler için yeni video çağrısı yok. Ses, stok ve müzik aynı
  metin/konuyla eşleşiyorsa tekrar ücretlendirilmez.
- Önce gerçek hesap üzerinden iki klibin fiyatı sorulur. Bilinmeyen fiyat,
  para birimi veya model sessizce kabul edilmez. `max_credits_per_clip=0` ve
  `monthly_credit_limit=0` **sınırsız değildir**; yalnız sıfır kredili işe izin verir.
  Gerçek plan/teklif görülene kadar pozitif bir sınır uydurulmadı.
- Günlük üç bölüm = günde altı, 30 günde 180 avatar klibi. Aylık kredi hesabı
  **180 × gerçek 15 saniyelik klip fiyatı** üzerinden yapılır. Önceden belirlenen
  4.000 TL ek bütçe, üyelik ve API harcamaları birlikte değerlendirilmeden artırılmaz.
- Web ekranındaki **Genjutsu 720p için üç ücretsiz üretim**; tüm konuşan avatar
  modelleri, tüm süreler, MCP/CLI veya API için ücretsiz kota kanıtı değildir.
  “Unlimited & free gens work only on higgsfield.ai” notu dikkate alınır.
  Genjutsu ayrıca bir **4–30 saniyelik hareket referans videosu** ister.
- [API faturalandırması](https://docs.higgsfield.ai/docs/concepts/billing-and-retention.md)
  model/parametreye göre başarılı istekleri bakiyeden düşürür. Web promosyonu
  yerine ücretli API otomatik açılmaz. Yeni abonelik, yıllık ödeme veya bakiye
  yüklemesi yapılmadı.
- Kalıcı yerel kayıt iş kimliğini beklemeden önce saklar. Bağlantı koparsa
  kayıtlı iş takip edilir. Yanıtı belirsiz bir ücretli istek tekrar gönderilmez;
  belirsiz harcama aylık rezervasyonda sayılır. Aynı kayıt dizini korunmalıdır.
- Teklif bir tahmindir; sağlayıcının fatura üst sınırı değildir. Fiyat değişirse
  rezervasyon uyuşmazlığı işlemi durdurur. Sağlayıcı fiyatı ve hesap hareketleri
  ilk canlı çalıştırmada ayrıca karşılaştırılır.

## Çalıştırma

Özel örnek paket: `video-output/higgsfield-vitamin-sebze-20261119/episode.json`.
Bu dizin public depoda bulunmaz; aynı bulutta veya erişilebilir özel medya
alanında saklanır.

```bash
# Varsayılan yalnız fiyat sorgular; video üretmez.
python -m automation.higgsfield_episode PRIVATE/episode.json --stage quote

# Gerçek hesaba göre belirlenmiş kredi sınırlarıyla iki yeni avatar.
python -m automation.higgsfield_episode PRIVATE/episode.json --stage avatars \
  --max-credits CLIP_CREDIT_LIMIT --monthly-credits MONTHLY_CREDIT_LIMIT

# Aynı çıktıların görsel/dudak incelemesi hash ile avatar-reviews.json'a yazılınca:
python -m automation.higgsfield_episode PRIVATE/episode.json --stage assemble
```

`avatar-reviews.json`, `intro` ve `outro` için `status: approved`, gerçek MP4
`sha256`, `identity_checked`, `lipsync_checked`, `hands_checked` alanlarını taşır.
Bu alanlar prompta bakarak otomatik doldurulmaz; gerçek üretilen klip incelenir.

Çıktı: `final/video.mp4`, `final/video-telefon.mp4`, `reels.txt`, `shorts.txt`,
`paylasim.md`. Master 1080×1920 / 30 fps H.264–AAC, 60 saniye; telefon kopyası
720×1280 / 30 fps, fast-start. Gerçek telefonda denenmeden telefon testi yapılmış
sayılmaz. Video ve açıklama hazırlamak sosyal hesaba otomatik yayın izni değildir.

## Günlük otomasyonun sınırı

09.00 Türkiye / günlük üç video tercihi korunur. Mevcut GitHub kuyruğu incelenmiş
`ready.json` paketlerini işleyebilir. Yeni Higgsfield üretimi için kalıcı hesap
erişimi, doğrulanmış maliyet sınırı, özel medya ve inceleme adımı gerekir. Bunlar
bağlanmadan planın her gün kendiliğinden üç bitmiş video ürettiği söylenmez.
CLI OAuth dosyasını public depoya veya herkese açık çalışma çıktılarına koymayın.
GitHub Actions için ayrı API yolu istenirse web üyeliğinden bağımsız faturalandırma
önce doğrulanmalıdır; bu güncellemede ücretli API'ye geçilmedi.
