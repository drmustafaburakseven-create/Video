# Günlük Reels ve Shorts planı

Hedef: her gün Türkiye saatiyle **09.00'da beş konu önerisi hazırlamak**, bunlardan
birini seçip **sizin sesinizle, kısa konuşan avatar bölümleriyle ve hareketli ara
görüntülerle yaklaşık 60 saniyelik bir video** üretmek. Aynı dikey video Instagram
Reels ve YouTube Shorts için kullanılacak. Ek bütçe hedefi ayda **4.000 TL**.

**Üretim kodu hazırlandı; sistem henüz baştan sona çalışan, her gün kendiliğinden
video teslim eden bir hizmet değil.** Fotoğraf, avatar hizmeti bağlantısı ve
sürekli çalışacak ortam tamamlanmalı.

**İlk gerçek örnek tamamlandı:** sizin klon sesiniz, hareketli stok çekimleri ve
altyazılarla **60 saniyelik, 720×1280 MP4** oluşturuldu; dosyanın baştan sona
çözümlenmesi de kontrol edildi. Bu örnekte **konuşan avatar yok**. Dosya bu bulut
bilgisayarda [video.mp4](../video-output/ekgida-hazirlik-motion-preview-9745f40a25499fb9/video.mp4)
konumunda; bu göreli bağlantı GitHub'da bir video yayını veya indirme servisi değildir.

## Şimdi sizden gereken iki şey

1. **Kendi fotoğrafınızı yeniden yükleyin.** Önceden gönderdiğiniz portreniz şu an
   erişilebilen dosyalarda bulunamadı. Yüzünüzün net göründüğü, önden çekilmiş,
   iyi ışıklı, tek kişilik bir JPG veya PNG yeterli. Poster veya ekran görüntüsü
   yerine fotoğrafın kendisini gönderin. GitHub'ın gizli bilgi boyut sınırına
   uygun küçük kopyayı teknik olarak hazırlayabiliriz; bunu sizin yapmanız gerekmez.
2. **[fal.ai](https://fal.ai/) hesabında API anahtarı ve kullanım kredisi hazırlayın.**
   Anahtarı sohbet mesajına yapıştırmayın; çalıştırılacak ortamın gizli bilgiler
   bölümüne **`FAL_KEY`** adıyla kaydedin. GitHub'da çalıştırılacaksa aynı adla
   [deponun Actions secrets bölümüne](https://github.com/drmustafaburakseven-create/Video/settings/secrets/actions)
   eklenmeli. Bulut ortamının gizli bilgileri ve GitHub secrets ayrı yerlerdir;
   birine kaydetmek diğerini otomatik doldurmaz.

Fal hesabı açılmadı, kredi satın alınmadı ve avatar üretimi için ücretli istek
gönderilmedi. Mevcut ElevenLabs üyeliğiniz seslendirme için kullanılacak; yalnızca
avatar API'si uğruna ElevenLabs paket yükseltmesi yapılmadı.

## Video nasıl hazırlanacak?

1. Kaynakları kontrol edilmiş çocuk sağlığı konularından beş öneri hazırlanacak.
   İlk sürüm **12 başlıklı bir konu havuzundan** seçim yapar; sınırsız yeni gündem
   taraması yaptığını varsaymayın. Yeni başlıklar kaynaklarıyla havuza eklenebilir.
2. Gemini, bir konu için ailelerin anlayacağı Türkçe metin ve sahne planı hazırlayacak.
   Kaynak bağlantıları ve taslak kaydedilecek. İlk örnekte tıbbi anlatımı gözden
   geçirmeniz gerekir.
3. ElevenLabs, metni hesabınızdaki **Mustafa B. Seven** klon sesiyle okuyacak.
   Son örnek seslendirme gerçekten üretildi ve **52,79 saniye** ölçüldü;
   bu ses ilk 60 saniyelik örnekte kullanıldı. Her yeni konuşmanın süresi ölçülerek
   60 saniyelik kurguya uygunluğu kontrol edilecek.
4. Fotoğrafınız ve bu sesin ilgili parçaları, iki kısa konuşan avatar bölümü için
   Fal Aurora'ya verilecek. Örnek bütçe hesabı **iki adet yaklaşık 4 saniyelik**
   avatar bölümü içindir.
5. Ara görüntüler için öncelik, konuya uygun **52 saniyelik mevcut hareketli
   stok veya önceden üretilmiş görüntüleri** kullanmak. Böylece her gün yeni
   Gemini videosuna ödeme yapılmaz. Yeterli uygun görüntü yoksa **44 saniye stok
   + Gemini'den 8 saniye yeni hareketli görüntü** seçeneği kullanılabilir.
   Her konu için görüntü uygunluğu ayrıca kontrol edilmelidir.
6. Görüntüler, ses, okunabilir altyazılar ve ölçülü geçişlerle birleştirilecek.
   Hedef slayt gösterisi değil, dikey bir video kurgusudur. İlk örnekte yüz
   benzerliği, dudak uyumu ve sahnelerin doğallığı birlikte değerlendirilecek.

Fotoğraftan üretilen avatarın gerçek çekimden ayırt edilemeyeceği garanti edilemez.
İlk örnek yeterince iyi değilse ücretli günlük üretime geçmeden ayarları değiştirmek
gerekir. Dosya üretimi ile sosyal medyaya otomatik yükleme ayrı işlerdir;
Instagram ve YouTube'a otomatik yayın bağlantısı henüz kurulmadı.

## Hangi bağlantılar gerçekten çalışıyor?

| Bileşen | Doğrulanan durum |
| --- | --- |
| Gemini | **Gemini 3.5 Flash-Lite** ile canlı metin üretimi başarılı. Ara görüntü için Omni yolu hazır; her yeni üretim ayrıca ücretli olabilir. |
| ElevenLabs ses | Hesaptaki klon ses erişilebilir; sizin sesinizle canlı seslendirme üretimi başarılı. |
| ElevenLabs avatar API | Mevcut Creator hesabında video API'si **402 / Pro veya üstü gerekli** yanıtı veriyor. Web arayüzündeki özelliklerin API'ye dahil olduğu varsayılmıyor. |
| Fal avatar | Fotoğraf + mevcut ses ile üretim adaptörü ve testleri hazır. **`FAL_KEY` yok; canlı avatar üretilmedi.** |
| Claude | Bu bulut bilgisayarda resmi Claude Code **2.1.326** kurulu, fakat oturum açık değil. Yerel Claude API anahtarı da yok. GitHub ortamına kurulu olduğu anlamına gelmez. |
| Stok görüntüler | Ek gıdaya hazırlık için toplam **73,14 saniyelik dört gerçek hareketli Pexels klibi** edinildi; kaynak ve lisans kayıtları tutuldu, örnek kareleri incelendi. İlk video üretildi. Farklı konuların uygun görüntüleri ayrıca tamamlanmalı. |
| Günlük otomasyon | GitHub iş akışı kodu var; deponun Actions çalıştırması şu an kapalı. Sürekli çalışan alternatif sunucu da kurulmadı. |

Claude zorunlu değildir: ilk çalışan sürüm Gemini ile hazırlanabilir. Sonradan
Claude'u metin düzenleme için bağlamak mümkündür. Claude web üyeliğinin API
kullanım kredisi sağladığı varsayılmaz.

## Aylık yaklaşık maliyet

Aşağıdaki hesap **günde bir video, ayda 30 gün** içindir. 16 Kasım 2026 tarihli
[ECB kurlarından](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml)
türetilen yaklaşık **1 USD = 50,3922 TL** kullanılmıştır; ödeme günündeki kur farklı olabilir.

| Görsel üretimi | Yaklaşık günlük | Yaklaşık 30 günlük |
| --- | ---: | ---: |
| Fal Aurora, 720p, iki adet 4 saniyelik avatar | $1,12 | **$33,60 ≈ 1.693 TL** |
| İsteğe bağlı Gemini Omni 1.2 Flash, 720p, her gün yeni 8 saniye | $0,556 | İlave **$16,68 ≈ 840 TL** |
| Her gün hem avatar hem yeni Gemini görüntüsü | $1,68 | **$50,4 ≈ 2.540 TL** |

Fal, her çıktının süresini **ayrı ayrı yukarı yuvarlayarak** ücretlendirir.
İki klip de 4,04 saniye olursa toplam 10 saniye üzerinden günlük avatar ücreti
$1,40 olur. Mevcut ara görüntüler yeniden kullanılırsa aylık avatar toplamı
**$42 ≈ 2.116 TL**; her gün yeni Gemini görüntüsü de alınırsa aylık görsel toplamı
**$58,68 ≈ 2.957 TL** seviyesine çıkar.

**Mevcut ara görüntülerle yaklaşık 1.693–2.116 TL; her gün yeni Gemini klibi de
alınırsa yaklaşık 2.540–2.957 TL yalnızca bu örnekteki görsel üretimidir.** Vergiler, kur farkı,
metin üretimi, ElevenLabs paket/kota aşımı, barındırma ve yeniden üretimler dahil
değildir. Dolayısıyla 4.000 TL içinde kalma hedefi makul bir başlangıç hesabıdır,
kesin toplam fiyat veya uygulanmış bir harcama limiti değildir. Ek denemeler ve
ücretli stok seçimi maliyeti artırır; ilk çalışan örnekten sonra gerçek faturaya
göre günlük üst sınır belirlenmelidir.

## Her gün çalışması için son adımlar

- **İsteğe bağlı stok bağlantısı:** İsterseniz ücretsiz [Pexels API](https://www.pexels.com/api/)
  anahtarını `PEXELS_API_KEY` olarak ekleyin; uygun görüntüleri seçip kullanım
  bilgileriyle kaydederiz. Alternatif olarak kullanım hakkınız olan videoları
  yükleyebilirsiniz. İlk örneğin herkese açık Pexels sayfalarından edinilen
  görüntüleri için API anahtarı şart değil. Konuya uygunluğu ayrıca kontrol edilir.
- **Kalıcı çalıştırma:** GitHub deposunda Actions yeniden etkinleştirilmeli veya
  sürekli açık bir sunucu seçilmelidir. Bu alternatif için [Docker ve günlük zamanlayıcı kurulumu](WORKER.md) hazırlandı; henüz sunucuya dağıtılmadı. Mevcut GitHub bağlantısı yönetici ayarını
  değiştiremiyor: iş başlatma **422**, yönetim isteği **403** döndü. Bu ortamda
  kimlik doğrulama başlıkları aracı tarafından değiştirildiğinden, sohbete
  yapıştırılan kişisel tokenın yetkisi doğrulanmış sayılmıyor; tekrar token
  göndermeniz bu sorunu çözmez. Bulut bilgisayar uyursa yerel zamanlayıcı çalışmaz.
- **İlk avatarlı örnek:** Fotoğraf ve Fal bağlantısı tamamlanınca avatarlı videoyu üretip
  inceleyeceğiz. Görüntü, dudak uyumu, içerik ve toplam maliyet kabul edildikten
  sonra günlük çalıştırma açılacak. GitHub zamanlamasında yoğunluğa bağlı gecikme
  olabilir; 09.00 hedef başlama saatidir.

## Resmî hizmet belgeleri

- [Fal Aurora API: fotoğraf ve ses girdileri](https://fal.ai/models/fal-ai/creatify/aurora/api?platform=http)
- [Fal Aurora güncel fiyatı](https://fal.ai/models/fal-ai/creatify/aurora)
- [Gemini API fiyatları](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Omni video özellikleri](https://ai.google.dev/gemini-api/docs/omni)
- [ElevenLabs video API](https://elevenlabs.io/docs/api-reference/flows/video/create)
- [ElevenLabs Text to Speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)

Omni'nin ses girdisi desteği bulunmadığı için sizin ElevenLabs sesinizi doğrudan
dudaklara eşlemek üzere kullanılmıyor; bu görevi fotoğraf + ses alan avatar
adaptörü üstleniyor. Teknik çalıştırma adımları [README.md](README.md) içindedir.
