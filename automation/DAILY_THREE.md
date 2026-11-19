# Üç günlük video ve paylaşım metinleri

19 Kasım güncellemesi: Yeni giriş/kapanış üretimi maliyet nedeniyle kullanıcının
Gemini/Flow uygulamasında hazırlayıp yüklediği sesli kliplerden yapılacak.
`MANUAL_GEMINI_WORKFLOW.md` ve `examples/dis-cikarma-ates-20261119/` ilk örnektir.
Bu yarı otomatik yol için Google video API'sine kendiliğinden geçilmez. Aşağıdaki
üç-video takvimi hedef olarak korunur; klip yüklenmesi ve incelemesi tamamlanmadan
üç bitmiş videonun günlük otomatik teslimi sağlanmış sayılmaz.

18 Kasım 2026 tercihi: **Her gün 09.00 Türkiye saati, beş öneriden üç farklı konu,
üç adet 60 saniyelik video.** Son onaylanan sıcak-ofis biçimi, 1080×1920/30 fps,
kendi sesiniz, giriş/kapanış avatarı, en az dört hareketli ara kaynak, altyazılar
ve yumuşak kapanış. Her videonun yanında Reels ve Shorts için ayrı başlık,
açıklama ve hashtag dosyaları bulunur. Otomatik sosyal yayın yapılmaz.

En yeni fotoğraf/kimlik tercihi: her bölümün girişi ve kapanışı son özgün
fotoğraftan yeniden üretilir; önceki avatar kesitleri kullanılmaz. Fotoğrafın
kaynak kadrajı, kliniği ve ellerin doğal birleşik konumu korunur; zoom-out ve
el hareketi istenmez. Özgün fotoğraf özel klasördedir, public Git'e girmez.
`REELS_STYLE.md` ve `profiles/warm-office-60.json` bu tercihi kaydeder.
`gemini_avatar --reference-locked --attempt <bolum-tarih-rol>` yeni isteklerin
özgün fotoğrafı kullanmasını, aynı işin devamında ise mevcut ücretli kaydı
korumasını sağlar. Çıktının yüz/el anatomisi ve konuşması yine incelenir;
bu yönergeler yüzde yüz benzerlik veya hatasız parmak garantisi değildir.

## Şu anda doğrulanan durum

- Üçlü konu/senaryo kuyruğu, iki platform için paylaşım metinleri, aynı günü tekrar
  satın almadan devam etme ve hazır kurgu paketlerini birleştirme kodu var.
- **Günlük üç bitmiş videoyu kendiliğinden teslim eden sistem henüz çalışmıyor.**
  Yeni Gemini avatar/ara görüntü üretimi, doğal ses ve grafik hazırlığının bu
  kuyruğa tam otomatik bağlantısı henüz tamamlanmadı. `ready.json` paketi yoksa
  kod eski kurguya dönmez; `needs_inputs` bildirir.
- Kullanıcı 19 Kasım'da bakiye yüklediğini bildirdikten sonra Google model
  erişimi **200** döndü; açıkça istediği diş çıkarma/ateş örneğinin yeni giriş
  ve kapanış üretimleri tamamlandı. Önceki 403 faturalandırma hatası bu kontrolde
  görülmedi. Bu sonuç gelecekteki bakiye/kota veya günlük üretim garantisi değildir.
- GitHub Actions depoda kapalı. Açmak için bağlantıyla yapılan istek **403 /
  bağlantı yetkisi yetersiz** yanıtı aldı. Depo sahibi
  [Actions ayarlarını](https://github.com/drmustafaburakseven-create/Video/settings/actions)
  kontrol etmeli. Hesap/billing nedeniyle kapatılmışsa GitHub'ın o ekrandaki
  yönlendirmesi uygulanmalı; yalnız workflow dosyasını değiştirmek açmaz.
- ElevenLabs Creator aboneliği erişilebilir. Yeni üyelik satın alınmadı.
  Kullanıcının açık API isteğiyle tamamlanan diş çıkarma/ateş örneğinde bir giriş
  düzeltmesi dahil 38 saniyelik Google görüntü üretildi; video çıktısının liste
  fiyatı tahmini yaklaşık 2,64 USD'dir (girdi, ElevenLabs ve vergi hariç).
  Aylık 4.000 TL ek bütçe sınırı korunuyor; günlük üçlü ücretli üretim açılmadı.

## Çalıştırma

```bash
# Ücretsiz yapılandırma/takvim kontrolü; bunlar video üretmez.
python -m automation.batch_studio --check-only
python -m automation.worker --check-only

# Kaynakları getirir, üç senaryo + paylaşım metni hazırlar; model kredisi kullanabilir.
python -m automation.batch_studio --date YYYY-MM-DD --editorial-only

# İncelenmiş medya/ses/grafik paketleri hazırsa üç videoyu birleştirir.
python -m automation.batch_studio --date YYYY-MM-DD --ready-root /private/ready-reels
```

Kuyruk aynı günün sayı/profil/model/konu seçimlerini dondurur. Önceden bir video
olarak kaydedilen günü üçe çevirip ücretli işlemleri yeniden başlatmaz; yeni sayı
bir sonraki yeni güne uygulanır. Bir slotun eksikliği diğer iki slotun dosyalarını
silmez. Kısmi başarı `partially_completed` olarak bildirilir.

Yeni varsayılan GitHub workflow bu kuyruğu 06.00 UTC'de çağırır. Eski `plan`
girdisiyle başlatılan işler eski pipeline yolunu kullanır. Docker worker da yeni
kuyruğu çağırır; **uyuyan bulut makinesinde süreklilik garanti etmez**. Sunucuya
dağıtım yapılmış değildir. `VIDEO_DAILY_COUNT=3`; `VIDEO_READY_ROOT` isteğe bağlıdır.

## Hazır kurgu paketi

`READY_ROOT/YYYY-MM-DD/KONU_ID/ready.json` dosyası `schema: warm-ready-v1`,
`profile: warm-office-60`, `topic_id`, tam anlatımın `narration_sha256` özetini,
gerçek görsel/ses incelemesi tamamlandıktan sonra `visual_review: approved` ve
`speech_timing_review: approved` alanlarını içerir. Onay alanları kendi başına
kaliteyi ölçmez; yapılan incelemenin kaydıdır, otomatik işaretlenmez.

`segments` içinde her dosyanın `path`, `sha256`, `start`, `end`, `role`
(`intro`, `body`, `outro`), isteğe bağlı `offset` ve `entry` alanları vardır.
`audio` ve `captions` nesneleri de `path`/`sha256` içerir; ses tam 60 saniyelik
PCM mix, grafik ASS formatındadır. `fonts` en az iki dosya ve özetini içerir.
`last_spoken_word` gerçek ölçümden gelir ve 58,5 saniyeyi geçmez. Yollar bu
manifestin dizinine göre veya yerel mutlak yol olarak çözümlenir.

Renderer dosya özetlerini, sahne sürelerini, kaynak çeşitliliğini, mevcut klinik
inceleme kayıtlarını ve çıktı karelerini denetler. Eksik görüntü dondurulmaz,
konuşma hızlandırılmaz. Girdiler veya tamamlanmış çıktı değiştiyse üstüne yazmaz.

Çıktılar: `video-output/warm-studio/GÜN/KONU_ID/` altında `video.mp4`,
`delivery.json`, `reels.txt`, `shorts.txt`, `social.json`, `paylasim.md`.
`social.json` anlatım özetiyle eşleşir; paylaşıldığını iddia etmez. GitHub artifacts
yalnız dosyaları gerçekten üreten başarılı/kısmi çalışmadan sonra oluşur.
