# GitHub dışında günlük çalıştırma

**18 Kasım 2026:** Worker artık `automation.batch_studio --videos 3` çağırır.
Her konu için Reels/Shorts metinleri çıkar; incelenmiş `ready.json` paketleri varsa
son onaylı 1080p sıcak-ofis videolarını birleştirir. [Güncel üçlü akış ve sınırlar](DAILY_THREE.md).
Yeni avatar/ara görüntü/ses paketlerinin tam otomatik hazırlığı henüz bağlı değildir.
Aşağıdaki Fal/tek-video üretim komutu eski yolu açıkça çağıran alternatif içindir;
yeni worker bu yola otomatik dönmez.

Bu seçenek, sürekli açık bir bilgisayar veya sunucuda **her gün Türkiye saatiyle
09.00** için hazırlanmıştır. Dosyaların depoya eklenmesi sunucu kurmaz ve günlük
üretimin başladığı anlamına gelmez. Uyuyan veya kapanan bulut ortamında çalışmaz.

Tek çalışma beş konu, üç senaryo ve paylaşım metinlerini hazırlar; incelenmiş
medya paketleri hazırsa üç video dosyasını üretir. Sonuç otomatik paylaşılmaz.

## Kurulum

Docker ve Docker Compose 2.24 veya sonrası bulunan sürekli açık makinede, depo kökünde:

```bash
mkdir -p automation/private video-output
cp automation/.env.example automation/.env
docker compose -f automation/compose.yml build
```

Gerçek API anahtarlarını yalnız `automation/.env` dosyasına girin. Bu dosya Git ve
Docker image dışında tutulur. Gemini/Claude web üyeliği API erişimi yerine geçmez.
Varsayılan metin sağlayıcısı Gemini'dir. Yeni kuyruk hazırlanmış Gemini + ElevenLabs
avatar kayıtlarını kullanır; Fal çağırmaz. Claude API isteğe bağlıdır; Claude Code bu image’a
kurulu değildir. Yalnız içerik taslağı için `VIDEO_EDITORIAL_ONLY=true` kullanılır.

Kendi net JPEG portrenizi `automation/private/portrait.jpg` olarak koyun.
PNG kullanıyorsanız compose dosyasındaki portre yolunu gerçek dosyaya göre düzenleyin.
Linux’ta klasör sahibi farklıysa `.env` içindeki `VIDEO_UID`/`VIDEO_GID` değerlerini
`id -u` ve `id -g` çıktılarıyla eşleştirin.

Stok dosyaları image içine gömülmez. Katalogdaki lisanslı kaynakları bir kez indirin:

```bash
docker compose -f automation/compose.yml run --rm --entrypoint python daily-worker -m automation.restore_media
docker compose -f automation/compose.yml run --rm daily-worker --check-only
```

İkinci komut yalnız takvimi kontrol eder; sağlayıcı kredisi kullanmaz ve videonun
üretime hazır olduğunu onaylamaz. Stok indirme gerçek internet erişimi gerektirir.

Gerekli girdiler tamamlandıktan sonra zamanlayıcıyı başlatmak için:

```bash
docker compose -f automation/compose.yml up -d
docker compose -f automation/compose.yml logs --tail=30 daily-worker
```

Bu son komutlar dağıtım adımıdır; bu rehberin hazırlanmasıyla yürütülmüş sayılmaz.
09.00’dan sonra ilk kez açılırsa o gün için bir kez çalışır; önceki günleri topluca
üretmez. Bir gün başarısız olsa bile her dakika yeniden ücretli istek göndermez.
Yeniden başlatmada `video-output/worker-state.json` kaydı aynı günü tekrar başlatmaz.

## Çıktılar ve tekrar deneme

`video-output/` altında durum, ses, kaynaklar, işlem kayıtları ve üretilmişse MP4
bulunur. `automation/media/` stok/üretilmiş medya kütüphanesidir. Bu klasörleri ve
işlem kayıtlarını koruyun; silmek ücretli işlemleri hatırlamayı engelleyebilir.
Portre salt okunur özel klasörden kullanılır; image veya GitHub’a kopyalanmaz.

Eksik girdiyi tamamladıktan sonra aynı günü **elle** devam ettirmek mümkündür:

```bash
docker compose -f automation/compose.yml run --rm --entrypoint python daily-worker -m automation.studio --date YYYY-MM-DD --output /data --portrait /private/portrait.jpg --avatar-provider fal --provider gemini
```

Bu komut üretim yapabilir ve sağlayıcı kredisi kullanabilir; mevcut kesin işlem
kayıtlarını yeniden kullanır. Önceki ücretli isteğin sonucu belirsizse otomatik
yeniden göndermez. Kaydı silerek körlemesine tekrar başlatmayın.

Takvim testi çalışan Docker hostunu, gerçek avatar kalitesini veya API kotalarını
doğrulamaz. İlk videoda tıbbi anlatım, kendi yüzünüz/sesiniz, dudak uyumu ve görüntü
lisansları ayrıca kontrol edilmelidir. Gerçek çekimden ayırt edilememe garantisi yoktur.
