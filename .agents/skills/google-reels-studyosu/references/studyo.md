# Konudan teslim dosyalarına

[Video deposunun](https://github.com/drmustafaburakseven-create/Video) kökünde çalış. Yeni konuyu hazırlarken örnekteki alanları kullan. Her bölüm için ayrı bir özel klasör aç.

```bash
BOLUM=video-output/uyku-rutini
mkdir -p "$BOLUM"
cp -n reels-studyosu/konular/uyku-rutini.json "$BOLUM/bolum.json"
python3 reels-studyosu/studyo.py plan "$BOLUM/bolum.json" "$BOLUM/plan"
```

1. Konu geldiğinde ilk iş konuşma metnidir. Tüm replikleri aynı konuda yaz ve çekim metinlerini bu metinden üret. Planın `profile` alanı `google-api-720p` olsun. `stock_seconds` içindeki her süre 5–10 saniye, toplam 40 olmalı. Her süre için aynı sırada bir stok tarifi, arama sorgusu ve kart metni gir. Çekim değişikliğini anlatımdaki anlam değişimine bağla.
2. Fotoğraftan Google API ile iki taze klip üret. Aşağıdaki ikinci argümana kullanıcının istediği özgün portreyi ver. Yeni çekimlerde AI Studio üzerinden doğrulanmış Gemini Omni 1.1 Flash kullanılır. Yeni bölüm JSON dosyasında `aspect_ratio` alanına `9:16` yaz. İki istek 720p, 9:16 ve onar saniyedir. Kullanıcıdan Google’da oturum açıp çekim hazırlaması beklenmez. Google'ın model ve faturalandırma erişimi kullanılan projeye bağlıdır. API anahtarı `GEMINI_API_KEY` ortam değişkeninden okunur. Aynı bölüm dizininde tekrar başlatınca kayıtlı işlem kimliği kullanılır. Hatalı çıktı ya da belirsiz ödeme için kendiliğinden yeni ücretli iş başlatma.

   ```bash
   .venv/bin/python reels-studyosu/studyo.py google "$BOLUM" automation/private/avatar-reference-current.jpg
   ```

3. `giris.mp4` ve `cikis.mp4` dosyalarını dinleyip izle. `zamanlar.json` içinde `question`, `answer`, `outro` alanlarına saniye cinsinden gerçek başlangıç ve bitişleri yaz. Her klip sıfırdan başlar. Son replik en geç 8,5 saniyede biter. Kadın ve doktor üst üste konuşmuşsa o bölümü doğru sesle dönüştürmek için önce çekimi düzelt.
4. `stok-ara` ile adayları getir. Lisansını, klinik doğruluğu ve kadrajını kontrol ettiğin kimlikleri sırayla `secimler.json` içine yazıp `stok-al` ile indir. Kendi lisanslı arşivinden kullanıyorsan çekimleri `stok-1.mp4` ve devamı olarak koy. Kurgudaki süre boyunca gerçek hareket olmalı.
5. `ELEVENLABS_API_KEY` ve `DOKTOR_VOICE_ID` ile `ses` adımını çalıştır. Kamera arkasındaki kadının sorusunu korur. Girişte ve kapanışta doktorun gerçek konuşma aralıklarına Voice Changer uygular. Yeni bölümlerde stok anlatımı için ElevenLabs `eleven_v4` ve Türkçe dilini kullan. Bölüm JSON’unda `body` alanı temiz metindir. `body_performance` alanında aynı metne duygunun değiştiği yerlere kısa oyunculuk yönergeleri ekle. Soruyu merakla, izlem önerisini sıcak, acil başvuru eşiğini sakin ve net söyle. Bu yönergeler altyazı dışında kalır. Yeniden çalıştırırken makbuz klasörünü koru.

   ```bash
   .venv/bin/python reels-studyosu/studyo.py ses "$BOLUM"
   .venv/bin/python reels-studyosu/studyo.py montaj "$BOLUM" "$BOLUM/teslim"
   ```

6. Dikey `Video-Telefon.mp4`, dikey `Video-1080p.mp4` ve `paylasim.md` dosyalarını teslim et. Her ikisi 60 saniye, 30 fps. Son sözcüğü, yazıların okunaklılığını, Google dudak senkronunu ve telefona uygun kopyanın açıldığını doğrula.
