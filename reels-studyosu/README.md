# Reels Stüdyosu

Her bölüm bir konu ve bir özgün doktor fotoğrafıyla başlar. “Vitamin şurubu sebzenin yerini tutar mı?” videosundan aldığımız örnekler sabit doktor kadrajı, sıcak ışık, krem renkli soru başlığı, altta kısa altyazılar, konu değiştikçe değişen hareketli çekimler ve konuşmadan sonra yumuşak kapanıştır. Eski videonun kareleri ve sesi yeni bölüme girmez.

## Sohbette hızlı başlangıç

Bu depoyu açan Codex sohbetinde `$google-reels-studyosu Konu: Yatarken bir masal daha mı?` yazın. [Beceri](../.agents/skills/google-reels-studyosu/SKILL.md) ilk yanıtta konuşma metnini, dört ara çekimi ve aynı fotoğrafla ayrı ayrı kullanacağınız iki Google komutunu verir. Yerelde ve GitHub Actions’ta `plan` adımı yalnız Python standart kütüphanesini kullanır.

## Sizin yapacağınız üç şey

1. Sohbete tek konu ve kullanmak istediğiniz özgün fotoğrafı gönderin. Metni, kaynakları, iki Google komutunu ve dört ara sahneyi biz hazırlarız.
2. Google Flow veya Gemini hesabınızda aynı fotoğrafı iki kez başlangıç görseli olarak kullanın. **Birinci işlemde giriş, ikincide kapanış** komutunu verin. Her işlemde tek çıktı, dikey görüntü ve Türkçe ses seçin. Kadın konuşurken doktor dinler. Doktor cevap verirken yalnız doktor görünür. İndirmeden önce özellikle ağız hareketini, elleri ve son sözcüğü kontrol edin.
3. İndirilen iki özgün, sesli MP4'ü sohbete ekleyin. Bunları herkese açık bir GitHub issue'suna yüklemeyin. Görsel yazıları, kendi sesinizle anlatımı, stokları, müziği (uygun lisanslı kayıt varsa), ses seviyesini, iki video kopyasını ve paylaşım metinlerini biz hazırlayacağız.

**Örnek konu** “Yatarken bir masal daha mı?” Kadın “Hocam, her gece bir masal daha mı okuyacağız?” diye sorar. Doktor “Son masalı başlamadan seçin” der. Son çekimde “Bu akşam son kitabı birlikte seçin. Sizin evde en sevilen masal hangisi?” der.

[Konuşma metni](ornek/konusma.txt) · [Google giriş komutu](ornek/google-giris.txt) · [Google kapanış komutu](ornek/google-cikis.txt) · [Paylaşım metinleri](ornek/paylasim.md)

## Google için en düşük ek harcama

Mevcut üyeliğinize dahil, **fotoğraftan dikey video ve konuşmalı ses** destekleyen modeller arasından ekranda en düşük kredi göstereni seçin. Varsa Fast seçeneğinin ücretini karşılaştırın. Çıktı adedi 1 olsun. Bir örnek maliyet hesabı: giriş 10 ve kapanış 10 kredi gösteriyorsa bölüm 20 kredidir. Bunlar varsayımsal rakamlardır. İki seçim de kotanıza sığıyorsa ayrıca kredi almanız gerekmez. Kota doluysa yenilenmesini bekleyebilirsiniz. Gerçek ücret ve model erişimi hesabınızdaki ekrana bağlıdır. Google API anahtarı ve otomatik ek kredi satın alma kullanılmaz. ElevenLabs, kullanılan doktor konuşmaları için kendi kotasından düşer. Sonradan yazı veya renk değişikliği yeniden ses ya da görüntü üretimi gerektirmez.

[Google kredi kullanımı](https://support.google.com/googleone/answer/16287445?hl=tr) · [Google Flow ile video oluşturma](https://support.google.com/labs/answer/16353334?hl=tr)

## Kurgu ve iş dağılımı

| Aşama | Kim yapar | Sonuç |
|---|---|---|
| Tek konu + fotoğraf | Siz, sohbette | Bu bölümün konusu ve kimlik referansı |
| Senaryo ve sağlık bilgisi | Codex | Gerçek kaynaklarla kontrol edilen soru, cevap, üç pratik öneri, kapanış, sahne listesi ve iki platformun metinleri |
| Plan | Stüdyo / Actions | Konuşma metni, Google'a verilecek iki komut ve paylaşım dosyası |
| İki kamera sahnesi | Siz, Google hesabınızda | Aynı özgün fotoğraftan iki sesli MP4 |
| Ses ve stok | Codex ve yerel hazırlık komutları | Kadın sesi korunur. Yalnız doktor replikleri Voice Changer'a gider. Ara anlatım doktorun ElevenLabs sesiyle bir kez okunur. Dört lisanslı hareketli çekim seçilir |
| Montaj | Actions veya aynı yerel komut | 60 saniye, 1080×1920 / 30 fps ana MP4, 720×1280 telefon MP4, Reels ve Shorts metinleri |
| Son kontrol | Codex | Yüz, el, Türkçe replikler, ses enerjisi, altyazı konumu ve kapanış izlenir. Platformlara yükleme kullanıcıdadır |

10 saniyelik kliplerle akış 10 + 40 + 10'dur. Google 8 saniye sunarsa **8 saniye giriş + 44 saniye ara görüntü + 8 saniye kapanış** kullanılır. Ara anlatım yine 10. saniyede başlar. İki geçişteki fazladan zamanı canlı stok ve varsa müzik doldurur. Kapanışta son sözün ardından en az 1,5 saniye kalır. Üç video gerekiyorsa üç farklı konu için aynı akış yürütülür. İş akışını konu başına başlatmak, onaysız günlük üretim masrafını önler.

## Uygulama

Aşağıdaki işlemler yapım tarafınındır. Python 3.11+, FFmpeg (libass/libx264), DejaVu Sans, GnuPG ve depodaki Python bağımlılıkları kullanılır. Komutları deponun kökünden çalıştırın.

1. Yeni konu için Codex, örnekteki yapıyla `reels-studyosu/konular/<konu>.json` dosyasını yazar. Tıbbi kaynaklar, platform metinleri ve doğal konuşma metni konuya özel yazılır. Özgün fotoğraf yalnız Google'a verilir.
2. `python reels-studyosu/studyo.py plan reels-studyosu/konular/uyku-rutini.json CALISMA/plan` komutuyla metinleri çıkarın. Aynı komut GitHub Actions'ta **Reels Stüdyosu → Run workflow → plan** olarak sunulur.
3. Git dışında özel bir çalışma klasörüne konu dosyasını `bolum.json` adıyla, iki klibi de `giris.mp4` ve `cikis.mp4` adlarıyla koyun. Videoları dinleyip gerçek konuşma ve durak sınırlarını saniye cinsinden `zamanlar.json` dosyasına yazın. Şema örneği: `{"question":[0.2,3.2],"answer":[3.45,7.65],"outro":[0.25,6.35]}`. Her iki klibin saati ayrı ayrı sıfırdan başlar. Kadının sesi ile doktorun repliği birbirine karışmışsa o kaydı kullanmayın.
4. `PEXELS_API_KEY` ile `python reels-studyosu/studyo.py stok-ara CALISMA` dört sahne için adayları getirir. Codex her sahneye uygun bir adayı seçer, dört kimliği sırayla `secimler.json` dizisine koyar ve `stok-al CALISMA` ile indirir. Kaynak ve lisans özel klasördeki katalogda kalır. Alternatif olarak dört lisanslı yerel çekimi `stok-1.mp4` … `stok-4.mp4` adlarıyla hazırlayın. Her çekim en az 11 saniye olsun. Görseli tıbbi doğruluk ve dikey kırpım açısından inceleyin.
5. Yerelde `ELEVENLABS_API_KEY` ve `DOKTOR_VOICE_ID` tanımlıyken `python reels-studyosu/studyo.py ses CALISMA` yalnız doktoru dönüştürür ve zamanlı ara anlatımı üretir. Ücretli yanıtlar özel `makbuzlar` klasöründe saklanır. Aynı girdiyle tekrar çalıştırmak makbuzu kullanır. Sonuç dinlenir. Hazır seslerde aynı zamanlı `giris.wav`, `cikis.wav`, `anlatim.wav` ve ElevenLabs karakter zamanlarını içeren `hizalama.json` verilebilir. Müzik için isteğe bağlı lisanslı `muzik.wav` eklenir.
6. `python reels-studyosu/studyo.py montaj CALISMA TESLIM` ile ücretli servise bağlanmadan montajı yapın. Süre, kare ve ses uyumu kontrol edilir. Telefon dosyası baştan sona çözülür. `TESLIM` altında iki MP4 ve kaynakları da içeren `paylasim.md` bulunur.

## GitHub Actions ile özel montaj

Genel depoda yalnız proje kodu, konu ve örnek komutlar okunabilir. Uzaktan montaj için GitHub'da Actions çalışmalı. Ayrıca yerel ortamda ve **Settings → Secrets and variables → Actions** altında aynı güçlü rastgele sır `REELS_MEDIA_KEY` adıyla tanımlanır. Örneğin parola yöneticisinde 48 karakterlik rastgele değer oluşturabilirsiniz. Bu değer sohbete, komuta veya Git'e yazılmaz. Google ve ElevenLabs anahtarları runner'a gönderilmez.

1. Özel girdi klasörünün dışında `python reels-studyosu/paket.py kilitle girdi CALISMA girdi.gpg` çalıştırın. Yalnız gereken dosyalar şifrelenir.
2. GitHub'da `reels-uyku-rutini` etiketiyle oluşturduğunuz Release'e yalnız `girdi.gpg` ekleyin. Komut satırından eşdeğeri: `gh release create reels-uyku-rutini girdi.gpg --title "Uyku rutini" --notes "Şifreli montaj girdisi"`. Yeni sürüm için yeni etiket kullanın.
3. **Actions → Reels Stüdyosu → Run workflow** ekranında `montaj` ve `uyku-rutini` seçin. Runner paketi açar, iki MP4'ü oluşturur ve yalnız şifreli sonucu yedi günlük artifact olarak verir.
4. İndirilen artifact ZIP'ini açın. `python reels-studyosu/paket.py ac sonuc sonuc.gpg TESLIM` ile yeni bir klasöre çıkarın. Actions veya secret ayarına erişilemediğinde aynı özel girdilerle 6. adımdaki yerel montaj çalışır. Gereken değişiklik yalnız yazı veya kurguysa aynı ses ve klipleri kullanın.
