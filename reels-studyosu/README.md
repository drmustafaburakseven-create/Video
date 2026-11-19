# Reels Stüdyosu

Her bölüm bir konu ve bir özgün doktor fotoğrafıyla başlar. “Vitamin şurubu sebzenin yerini tutar mı?” videosundan aldığımız örnekler sabit doktor kadrajı, sıcak ışık, krem renkli soru başlığı, altta kısa altyazılar, konu değiştikçe değişen hareketli çekimler ve konuşmadan sonra yumuşak kapanıştır. Eski videonun kareleri ve sesi yeni bölüme girmez.

## Sohbette hızlı başlangıç

Bu depoyu açan Codex sohbetinde `$google-reels-studyosu Konu: Yatarken bir masal daha mı?` yazın. [Beceri](../.agents/skills/google-reels-studyosu/SKILL.md) ilk yanıtta konuşma metnini, ara çekimleri ve Google çekimlerinin repliklerini hazırlar. Yerelde ve GitHub Actions’ta `plan` adımı yalnız Python standart kütüphanesini kullanır.

## Google API ile yeni üretim

Konuyu verdiğinizde önce konuşma tarzınıza uygun kadın sorusu, doktor cevabı, ara anlatım ve kapanış birlikte yazılır. Yeni bölüm profilinin adı `google-api-720p`. Google API özgün portrenizden 10 saniye giriş ve 10 saniye kapanış üretir. ElevenLabs Voice Changer doktorun iki çekimdeki sesini klonunuza dönüştürür. Kadın sorusu ayrı kalır. Aradaki 40 saniyede aynı klonla anlatım ve her biri 5–10 saniye süren hareketli stok çekimleri kullanılır.

Yatay 1280×720 iPhone dosyası ile aynı kurgunun dikey Reels/Shorts dosyası ayrı hazırlanır. Ayrıntılı [komut sırası](../.agents/skills/google-reels-studyosu/references/studyo.md), [örnek konuşma](ornek/konusma.txt) ve [platform metinleri](ornek/paylasim.md). Özel medya klasöründe API ile üretim ve seslendirme ücretli olabilir. Plan ve montaj yereldir. Önceden hazırlanmış profilsiz sekiz-on saniyelik kullanıcı klibi paketleri eski kurgu ayarlarıyla açılır.

## GitHub Actions ile özel montaj

Genel depoda yalnız proje kodu, konu ve örnek komutlar okunabilir. Uzaktan montaj için GitHub'da Actions çalışmalı. Ayrıca yerel ortamda ve **Settings → Secrets and variables → Actions** altında aynı güçlü rastgele sır `REELS_MEDIA_KEY` adıyla tanımlanır. Örneğin parola yöneticisinde 48 karakterlik rastgele değer oluşturabilirsiniz. Bu değer sohbete, komuta veya Git'e yazılmaz. Google ve ElevenLabs anahtarları runner'a gönderilmez.

1. Özel girdi klasörünün dışında `python reels-studyosu/paket.py kilitle girdi CALISMA girdi.gpg` çalıştırın. Yalnız gereken dosyalar şifrelenir.
2. GitHub'da `reels-uyku-rutini` etiketiyle oluşturduğunuz Release'e yalnız `girdi.gpg` ekleyin. Komut satırından eşdeğeri: `gh release create reels-uyku-rutini girdi.gpg --title "Uyku rutini" --notes "Şifreli montaj girdisi"`. Yeni sürüm için yeni etiket kullanın.
3. **Actions → Reels Stüdyosu → Run workflow** ekranında `montaj` ve `uyku-rutini` seçin. Runner paketi açar, iki MP4'ü oluşturur ve yalnız şifreli sonucu yedi günlük artifact olarak verir.
4. İndirilen artifact ZIP'ini açın. `python reels-studyosu/paket.py ac sonuc sonuc.gpg TESLIM` ile yeni bir klasöre çıkarın. Actions veya secret ayarına erişilemediğinde aynı özel girdilerle yerel montaj komutu çalışır. Gereken değişiklik yalnız yazı veya kurguysa aynı ses ve klipleri kullanın.
