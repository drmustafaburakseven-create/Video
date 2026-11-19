# Gemini/Flow uygulamasından gelen kliplerle üretim

19 Kasım 2026 tercihi: Kullanıcı giriş ve kapanışı kendi Gemini/Flow hesabında
oluşturur. Codex bu dosyaları inceler, konuşmayı mevcut ElevenLabs klonuyla
dönüştürür, hareketli ara görüntüleri ve anlatımı hazırlayıp son kurguyu yapar.
Bu yol için yeni Google video API çağrısı gerekmez. Gemini/Flow kendi üyelik
sınırlarını, ElevenLabs ise kendi kullanım kotasını uygular.

## Kullanıcının yapacağı üç adım

1. Konu paketindeki `giris-gemini.txt` komutunu Gemini'ye yapıştırın ve son
   **özgün fotoğrafınızı** ekleyin. Oluşan sesli videoyu özgün MP4 olarak indirin.
2. Aynı özgün fotoğrafı yeniden ekleyip `cikis-gemini.txt` ile ikinci videoyu
   oluşturun. İlk yapay videodan alınan kareyi yüz referansı olarak kullanmayın.
3. İki dosyayı buraya yükleyin. Özel GitHub medya deposu erişilebilir olduğunda
   aynı dosyalar `gelen-videolar/KONU_ID/giris.mp4` ve
   `gelen-videolar/KONU_ID/cikis.mp4` konumlarına da yüklenebilir.

`Video` deposu herkese açıktır. Bu depoya yalnız senaryo, prompt ve üretim
kuralları girer; fotoğraf, kişisel klip, ses klonu veya API anahtarı girmez.
19 Kasım'daki ayrı `Video-Medya` özel depo oluşturma isteği GitHub bağlantısının
`createRepository` yetkisi olmadığı için reddedildi. Özel yükleme alanı kurulmuş
değildir. Mevcut kullanılabilir teslim yolu bu sohbete dosya eklemektir.

## Gelen dosyaların incelenmesi

- Orijinal ses korunur; müzik, uygulama içi hızlandırma veya sessize alma yapılmaz.
  Voice Changer için videonun kendi konuşması gerekir. Fotoğraf tek başına gerçek
  ses kaydı değildir. Doktor klonu yalnız doktorun konuşmasına uygulanır.
- Birden çok deneme varsa hepsi farklı dosya adlarıyla korunur. Seçim, yalnızca
  en yeni ada göre değil yüz, el anatomisi, cümle bütünlüğü, doğal performans ve
  ses/dudak incelemesine göre yapılır. Hiçbiri uygunsa onaylanmaz.
- Başlangıç/bitiş, gerçek sözcük zamanları, çözünürlük, kare hızı, ses ve dosya
  özeti ölçülür. Metadata veya doğru prompt tek başına görsel onay sayılmaz.
- Hedef ilk örnekte 10 saniye giriş + 40 saniye ara bölüm + 10 saniye kapanıştır.
  Uygulama yalnız 8 saniye üretiyorsa yeniden ücretli deneme istenmeden dosya
  incelenir; konuşma kesilmemişse ara bölüm süresi yeniden planlanabilir. Klip
  dondurulmaz, döngüye alınmaz ve konuşma hızlandırılmaz.
- Giriş/kapanışın özgün sesi Voice Changer ile dönüştürülür; aynı başlangıç ve
  hız korunur. Ara anlatım tek doğal kayıt olarak hazırlanır. En az dört farklı,
  konuya uygun hareketli kaynak seçilir. Tıbbi hareketler ayrıca incelenir.
- Altyazı, vurgu grafikleri, `@Drmustafaburakseven`, geçişler ve canlı yumuşak
  kapanış son kurguda eklenir. Gemini'den görüntüye yazı üretmesi istenmez.
- Son teslim 60 saniye, 9:16, 1080×1920/30 fps, H.264/AAC, fast-start ve ayrıca
  gerektiğinde küçük telefon kopyasıdır. Reels ve Shorts paylaşım metinleri
  her pakete dahildir. Fiziksel telefon testi yapılmadan yapıldı denmez.

## Otomasyonun sınırı

Bu bir **yarı otomatik** akıştır; Gemini uygulamasında üretim ve MP4'ü aktarma
adımı kullanıcıdadır. Prompt dosyalarının varlığı, videonun üretilmiş veya
günlük üç videoluk otomasyonun canlı olduğu anlamına gelmez. Bir klip eksikse
eski avatarla doldurulmaz ve Google API'ye kendiliğinden geçilmez.

Hazır kurgu `automation.ready_reel` tarafından tüketilen `warm-ready-v1`
paketine, gerçek ses/görüntü incelemesinden sonra dönüştürülür. Konu paketindeki
`request.json` bu tamamlanmış paket **değildir**; yalnız beklenen girdileri ve
konuşmayı tanımlar. Eksik klip, ses veya inceleme `awaiting_user_clips` olarak
kalır. Otomatik sosyal paylaşım yapılmaz.
