# 60 saniyelik ekonomik karma video akışı

Amaç, aynı dikey dosyayı YouTube Shorts ve Instagram Reels için hazırlamak:
kullanıcının ElevenLabs klon sesi, çoğunlukla yeniden kullanılabilir hareketli
stok, kısa yeni AI görüntüleri ve kendi fotoğrafından oluşturulmuş konuşan avatar.
Nihai birleştirme depodaki FFmpeg akışında yapılır. Üretim, sosyal platformlara
yayınlamadan ayrı bir adımdır; burada otomatik sosyal medya yayını kurulmuş sayılmaz.

## Önerilen 60 saniye dağılımı

| Malzeme | Hedef süre | Kullanım |
|---|---:|---|
| Hareketli stok / kullanıcının çekimleri | 44 sn | Açıklanan davranışı veya nesneyi gösteren kısa kesitler. |
| Yeni Gemini görüntüsü | 8 sn | Kütüphanede eksik olan tek özel eylem; bir kaynak klipten iki adet 4 sn kesit. |
| Konuşan doktor avatarı | 8 sn | Örneğin 0–4 ve 28–32 saniyelerde iki kısa bölüm. |
| **Toplam** | **60 sn** | Tek kesintisiz anlatım; fotoğraf slaytı kullanılmaz. |

Bu oran bir başlangıç planıdır. Çoğu ara görüntü 2–4 saniye sürer. Yeni Gemini
üretimlerinin benzersiz kaynak süreleri toplamı en fazla 16 saniye, avatarın
ekranda kaldığı toplam süre en fazla 12 saniye tutulur. Aynı `generation_id`
aynı kaynağı gösterir; iki kesitte kullanılması iki ayrı API üretimi değildir.
Ücretsiz bir stok veya mevcut uygun klip varsa yeni üretim yapılmaz.

“En ucuz” olduğuna dair sabit bir ücret iddiası yoktur. Stok lisansı, yeni klip
sayısı, avatar sağlayıcısının fiyatı ve hesapların API tarifesi toplam maliyeti
belirler. Gemini web aboneliği, Gemini API kredisi veya dış avatar hizmeti
aboneliği yerine geçmez. İstek/süre sınırı para harcama limiti değildir.

## Günlük iş bölümü

1. **Gemini:** Günün konusunu, tıbbi kaynakları, doğal Türkçe anlatımı ve sahne
   planını hazırlar. Önce katalogdaki klipleri seçer; yalnız eksik ara görüntüye
   yeni üretim promptu yazar. [Hazır prompt](GEMINI_PROMPT.md) kullanılabilir.
2. **GitHub içerik dosyası:** Medyası hazır plan `automation/plans/` içine girer.
   Eksik fotoğraf, stok veya avatar varsa taslak `automation/drafts/` içinde
   kalır. GitHub’a sadece okuma erişimi olan Gemini bunu kendi başına yükleyemez;
   dosyayı kullanıcıya verir veya Codex’e aktarılır.
3. **ElevenLabs:** Konuşma metninin tamamını mevcut `Mustafa B. Seven` klonuyla
   bir kez seslendirir. Aynı yanıtın ses dosyası ve kelime/karakter zamanları
   saklanır. Hazır ve metinle eşleşen ses tekrar satın alınmaz.
4. **Avatar:** Nihai sesin ilgili kesitleri, kullanıcının kendi fotoğrafıyla
   dudak eşleme hizmetine verilir. Farklı bir hizmette ikinci kez seslendirme
   yaptırılmaz. Avatar klipleri hazır olduktan sonra kataloğa kaydedilir.
5. **Codex / kurgu akışı:** Hareketli klipleri seçer, keser, 60 saniyelik zaman
   çizelgesine yerleştirir; anlatımı, altyazıları ve kısa geçişleri birleştirir.
   Ses uzunluğu, kaynak klip süreleri, görüntü/ses uyumu ve tam dosya çözümü
   kontrol edilir. Biten dosya Actions çalıştırmasının Artifacts bölümünden alınır.

## İlk üretimde uygulanacak sıra

Komutlar depo kökünde çalıştırılır. Aşağıdaki dosya, kimlik, kaynak ve lisans
değerleri gerçek malzemeyle değiştirilmelidir; örnekler mevcut stok kaydı değildir.

1. Lisansı doğrulanmış hareketli klibi kütüphaneye alın:

   ```bash
   python -m automation.media --file /yerel/klip.mp4 --id stok-kimligi --kind stock --source-url "GERCEK_HTTPS_KAYNAK" --license "DOGRULANMIS_LISANS"
   ```

   Daha önce üretilmiş Gemini MP4’ü için aynı komutta `--kind generated`
   kullanılır. İçe aktarıcı dosyayı ve SHA-256 özetini kataloğa kaydeder.

2. Codex, taslağın gerçek stok seçimlerini ve hazırlanacak avatar kesitlerini
   netleştirir. Günlük üretim GitHub’da yapılacaksa önerilen yol **Actions →
   Daily motion video → Run workflow** üzerinden `plan: ek-gida-hybrid.json`,
   `prepare_only: true`, `validate_only: false` seçmektir. Taslak `main` dalında
   bulunmalıdır. Böylece ana ses GitHub işlem kaydında korunur; hazırlık
   dosyaları aynı çalışmanın Artifacts bölümünden indirilir.

   Hazırlık ve üretimi yerelde yapacaksanız alternatif komut:

   ```bash
   python -m automation.pipeline --plan ek-gida-hybrid.json --prepare
   ```

   `--prepare`, güvenli bir dosya adıyla `plans/` veya `drafts/` içindeki planı
   okuyabilir. Sadece şema kontrolü değildir: eşleşen kayıtlı ses yoksa
   ElevenLabs seslendirmesi üretir. Çıktılar `video-output/<job>/` altında
   `voice.mp3`, `alignment.json`, `voice-manifest.json`, `avatar-NN-speech.wav`
   ve `avatar-requests.json` olarak bulunur. Yerelde `video-output/journal/`
   korunur. Avatar üretildikten sonra farklı ses kaydıyla devam edilmez.

   **Yerelde hazırlayıp GitHub’da üretecekseniz**, hazır ses paketini plana
   aktarın; aynı yöntem GitHub’dan indirilen paketi başka ortamda kullanmak
   için de geçerlidir:

   ```bash
   python -m automation.voice --from-output "video-output/<job>" --plan automation/drafts/ek-gida-hybrid.json
   ```

   Bu komut özgün ana ses/hizalama paketini doğrular, `automation/assets/`
   içine alır ve planın `prepared_voice` alanını günceller. Oluşturduğu
   dosyalar ve güncellenen plan birlikte depoya eklenir. Yalnız avatar MP4’ünü
   taşımak yeterli değildir; eşleşen ana ses olmadan üretim durur.

3. Kullanıcının portresini ve her `avatar-NN-speech.wav` parçasını seçilen
   dudak eşleme sağlayıcısına verin. Gelen MP4’ü ilgili istek kaydının
   `asset_id` değeriyle içe alın:

   ```bash
   python -m automation.media --file /yerel/avatar.mp4 --id avatar-kimligi --kind avatar --avatar-requests "video-output/<job>/avatar-requests.json"
   ```

   `avatar-kimligi`, istek dosyasındaki gerçek kimlikle değiştirilir. İçe
   aktarma bu dosyadan zaman aralığını, anlatım ve ana ses özetlerini taşır;
   bu alanları elle tahmin etmeyin. Birden fazla avatar için her MP4 ayrı alınır.

4. Medyası tamamlanan JSON’u `automation/drafts/` dizininden `automation/plans/`
   içine taşıyın. `enabled: true` kullanın. Yerel medya kontrolü:

   ```bash
   python -m automation.pipeline --plan ek-gida-hybrid.json --check-media
   ```

   `--check-media` dosya, katalog ve kesit uyumunu okur; ücretli üretim çağrısı
   yapmaz. Normal üretim ve bu kontrol yalnız `plans/` içindeki planı kullanır.
   GitHub üretimi için plan, katalog, MP4 dosyaları ve varsa aktarılmış ses
   paketi `main` dalında erişilebilir olmalıdır. **Run workflow** içinden
   `prepare_only: false`, `validate_only: false` seçin veya günlük kuyruğu
   bekleyin. Yeni Gemini üretimi bu aşamada yapılır.

   Yerel üretimde, aynı yerel işlem kaydını koruduysanız veya ses paketini
   içe aldıysanız `python -m automation.pipeline --plan ek-gida-hybrid.json`
   kullanılabilir. Web oturumu ya da başka bilgisayardaki dosya tek başına
   ses ve görüntüleri bu ortama taşımaz.

## Avatar için gerekenler

Ek gıda taslağının mevcut klon sesinden çıkarılmış gerçek parçalar hazırdır:
[açılış 0–4 sn](assets/ek-gida/avatar-preparation/avatar-01-speech.wav),
[kapanış 56–60 sn](assets/ek-gida/avatar-preparation/avatar-15-speech.wav) ve
[eşleme istekleri](assets/ek-gida/avatar-preparation/avatar-requests.json).
Bunlar ses dosyalarıdır; avatar videosu henüz değildir. Başka konu veya
değişmiş anlatım için yeniden kullanılamazlar.

Bir adet kullanıcının kendi portresi gerekir: yüz net, karşıdan veya çok hafif
çapraz, ağız görünür, doğal ışık, yüzün önünde mikrofon/nesne olmadan. Başka bir
kişinin yüzü doktor olarak kullanılmaz. Fotoğraf henüz yoksa bu aşama hazır değildir.

Fotoğrafı hareket ettirmek konuşan avatar üretmekle aynı şey değildir. Seçilen
hizmetin **bu fotoğraf ve mevcut ses dosyasıyla dudak eşleme** yapabilmesi gerekir.
Gemini’nin web hesabının veya video API’sinin bu özelliği sunduğu varsayılmaz.
Sağlayıcı/API seçimi ve gerekli erişim tamamlanmadan otomatik avatar üretimi
çalışıyor diye bildirilmez.

Avatar, anlatımın tam ilgili zaman aralığına göre hazırlanır. Kurgu akışının
çıkardığı ses kesiti kullanılmalı; başına sessizlik eklenmemeli, hızı değiştirilmemeli
ve farklı cümleyle değiştirilmemelidir. Klipteki ağız hareketi, ses ve kimlik
teslim öncesinde görsel olarak kontrol edilir. Eksik avatarı sabit fotoğraf veya
bağlam dışı bir yüzle doldurmak uygun değildir.

Her avatar kesiti kendi ses parçasının ilk karesinden başlar; `source_start`
değeri `0` olur. Anlatım veya ses kaydı değişirse önceki avatar yeni plana
doğrudan taşınmaz; metin ve ses özeti eşleşmeleri yeniden doğrulanır.

## Hareketli medya kütüphanesi

`automation/media/catalog.json`, kullanılabilir varlıkların kaydıdır. JSON
planındaki `asset_id` gerçekten burada bulunmalıdır. Her klibin kaynak dosyası,
yaşı/bağlamı, uygun bölüm süreleri ve kullanım hakkı takip edilir. Katalog şeması
ve örnekleri depodaki güncel dosyadan okunur; hayalî bir stok kimliği veya URL
çalıştırılabilir plana yazılmaz.

Kataloğun üst düzeyi `version: 1` ve `assets` nesnesidir. `assets` anahtarları
planlarda kullanılan varlık kimlikleridir. Her varlığın zorunlu alanları:

| Alan | Kural |
|---|---|
| `path` | `automation/` köküne göre yerel MP4 yolu; örneğin `media/library/...mp4`. Yol `automation/media/` içinde kalır. |
| `kind` | `stock`, `generated` veya `avatar`; plandaki türle aynı olmalıdır. |
| `sha256` | Gerçek medya dosyasının SHA-256 özeti. |
| `source_url` | Stokta zorunlu gerçek kaynak bağlantısı. |
| `license` | Stokta zorunlu, doğrulanmış kullanım hakkı bilgisi. |
| `narration_sha256` | Avatarda zorunlu; üretildiği anlatımla eşleşmesini sağlar. |
| `audio_sha256` | Avatarda zorunlu; kesitlerin çıkarıldığı ElevenLabs ana sesinin SHA-256 özeti. |
| `timeline_start` | Avatarda zorunlu; eşlenen sesin 60 saniyelik anlatımdaki başlangıcı. |

Avatar kaydında kaynak/lisans alanları isteğe bağlıdır; sahibinin kullanıcı
olduğu `owner: "user"` metaverisiyle belirtilebilir. MP4 dosyaları GitHub
çalıştırıcısının erişebileceği şekilde depoda bulunmalı; oturum isteyen indirme
sayfaları veya erişim anahtarı içeren URL’ler medya dosyası yerine yazılmamalıdır.

Stok için indirme sayfası ve kullanım lisansı kaydedilir. Ticari sosyal medya
kullanımını kapsadığı doğrulanmamış veya sadece editoryal kullanıma izin verilen
bir çekim otomatik “uygun” kabul edilmez. Kullanıcının kendi çekimleri de kaynak
olarak işaretlenir. Gemini ile üretilmiş bir klip kütüphanede yeniden kullanılabilir,
ancak gerçek kamera çekimi diye tanıtılmaz; kökeni katalogda korunur.

Bir klip yalnız gerçekten hareketli bir video ise kullanılmalıdır. Fotoğrafın
yakınlaştırılması, bir karenin uzatılması veya birkaç saniyenin tekrar döndürülmesi
eksik hareketli çekimin yerine geçmez. `source_start + duration`, dosyanın gerçek
süresini aşamaz. Aile videosundaki davranış, tıbbi metinle ve hedef yaşla uyumlu olmalıdır.

## Plan biçimi

Karma planlarda `format` değeri `hybrid-v1` olur. Temel alanlar:

| Alan | Anlamı |
|---|---|
| `id` | Benzersiz, küçük harf/rakam/tire içeren içerik kimliği. |
| `title` | Türkçe konu başlığı. |
| `enabled` | Hazır planda `true`; alan yoksa da varsayılan `true`. `false` olan plan günlük kuyruktan alınmaz. |
| `duration_seconds` | `60`. |
| `narration` | Yalnız okunacak metin; 400–1400 karakter. |
| `sources` | Doğrulanmış resmi veya birincil kaynakların HTTPS bağlantıları. |
| `shots` | Gösterim sırasıyla kesitler; süre toplamı tam 60 saniye. |

Her kesitte `kind`, `duration` ve isteğe bağlı `source_start` bulunur. `stock`
ve `avatar` kesitlerinde geçerli `asset_id` gerekir. Hazır `generated` klipler de
katalogdaki `asset_id` ile seçilir; yeni API üretimine veya yeni üretim süresi
bütçesine girmez. Yeni `generated` kesitlerinde bunun yerine `generation_id`,
`generation_seconds` ve `prompt` kullanılır. Örneğin tek 8 saniyelik kaynak,
`source_start: 0` ve `source_start: 4` olan iki 4 saniyelik kesitte kullanılır.
Bu dosya bir şema örneği anlatır; gerçek malzeme seçmeden aktif kuyruğa örnek ID koymayın.

Hazır planlar `automation/plans/YYYY-MM-DD-konu-kimligi.json` yoluna eklenir.
Medya eksiği olan JSON taslakları ve eksik listeleri `automation/drafts/`
içinde tutulur. Avatar için ayrılmış ama henüz üretilmemiş kimlikler yalnız
bu hazırlık taslağında kullanılabilir; katalogda hazır varlık gibi sunulmaz. `enabled`
alanının unutulması dosyayı devre dışı bırakmaz; eksik plan aktif kuyruğa konmaz.

Konuşma süresi metin uzunluğundan kesin bilinmez. Son ses ölçülür; 60 saniyeye
sığmıyorsa metin veya doğal duraklar düzenlenir. Avatar sesini hızlandırarak veya
son cümleyi keserek süreyi tamamlama yoluna gidilmez. İlk hedef yaklaşık 55–59
saniyelik anlatımdır; kalan kısa bölüm kapanış içindir.

## Görünüm ve geçişler

9:16 dikey görüntü ve telefonda okunabilir kısa altyazılar kullanılır. Krem ve
lacivert ana renk; pembe/sarı az miktarda vurgu olabilir. Yüz, ağız ve anlatılan
nesne yazıyla örtülmez. Marka adı küçük kalır; ilk iki saniyede doğrudan konuya girilir.

Temel geçiş, görüntüdeki hareket ve nesne benzerliğini izleyen doğal kesmedir.
Gerekli birkaç ara görüntü geçişinde, gelen kesite `transition: "fade"`
eklenerek kısa kararma kullanılabilir; her kesitte tekrarlanmaz. Bu seçenek
yalnız iki ara görüntü arasında, her tarafta dört karelik kararma/açılma yapar;
görüntüleri üst üste bindiren çözülme değildir. Avatar sınırlarında doğrudan
kesme korunur, ses veya ağız hareketi kaydırılmaz. Slayt döndürme, sayfa çevirme
ve gereksiz kamera sarsıntısı yoktur. AI görüntü ve avatar kesitlerinde kısa
temsili görüntü etiketi görünür; gerçek stok/kullanıcı çekimine yanlış AI etiketi konmaz.

## Instagram Edits gerekli mi?

Hayır. Dosya birleştirme ve altyazılar otomasyon içinde yapılabilir. Kullanıcı
isterse bitmiş MP4’ü Edits’e alıp son kapak, müzik veya platforma özel dokunuşları
elle ekleyebilir. Edits için tarayıcı kontrolü veya otomatik API bağlantısı
kurulmuş varsayılmaz. Diğer platforma da yüklenecek videolarda müzik kullanım
hakkı her platform için ayrıca uygun olmalıdır.

## Günlük saat ve teslim

Mevcut günlük zamanlama 09.00 Europe/Istanbul’dur; GitHub yoğunluk nedeniyle
geciktirebilir. Gemini’nin bu promptu okuması tek başına her gün yeni içerik
oluşturacak zamanlanmış görev kurmaz. Yeni konu dosyasının aktif kuyruğa gelmesi
gerekir; hazır plan yoksa sistem yeni tıbbi iddia uydurmaz.

Anahtarlar GitHub Secrets’ta saklanır. Gemini/Claude hesabı şifresi veya oturum
çerezi depoya eklenmez. Canlı üretim için API izinleri, kota ve avatar erişimi
ayrı ayrı doğrulanır; dosyaların depoda bulunması bu hizmetlerin çalıştığını
kanıtlamaz. Eksik medya ve kota sorunları durum raporunda açıkça gösterilir.
