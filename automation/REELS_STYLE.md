# Dr. Mustafa Burak Seven — kalıcı Reels / Shorts kuralları

Bu kurallar konuya özgü değildir. Son kullanıcı tercihi önce gelir. Güncelleme: 17 Kasım 2026.

## Anlatıcı ve amaç
Çocuk doktoru ve ebeveynlere pratik bilgi veren bir içerik üreticisi gibi konuş: sıcak, canlı, doğrudan, öğretici. Eğlenceyi yazı ve kurguya taşı; çocukların korkusu, kanaması veya hastalığıyla şaka yapma. Korkutarak izletme, suçlama, kesin sonuç veya viral olma garantisi verme. İzleyicinin başka bir ebeveyne gönderebileceği tek uygulanabilir mesaj üret.

## Süre ve sahneler
- Varsayılan toplam 60 saniye: 0–10 saniye kullanıcının konuşan avatarı, 10–50 saniye hareketli açıklayıcı çekimler, 50–60 saniye konuşan avatarı.
- Avatar kullanıcının özel portresinden oluşturulur. Gemini doğal konuşma performansı → ElevenLabs Voice Changer ile mevcut klon ses → ses zamanlaması korunarak kurgu.
- Yeni avatar üretimlerinde `--performance energetic` kullan. İlk yarım saniyede konuşma hedefle; gerçek başlangıcı ölç. Doğal vurgu, kısa durak, ölçülü mimik/el hareketi; bağırma veya yapay oyunculuk yok.
- İlk iki saniyede konu veya yaygın hata açık olsun. Selamlama, uzun unvan veya logo açılışı kullanma. Üç açılış taslağı içinden birini seç; vaat edilen yanıtı açıklamanın başında ver.
- Ara sahneler anlamlı 2–4 saniyelik parçalar olsun. Aynı kaynağın farklı, kullanılmamış zaman aralıkları kullanılabilir. Fotoğraf kaydırma, donmuş kare, tekrar döngüsü ve hızlandırılmış konuşma yok.
- Kapanış kısa bir hatırlatma ve doğal paylaşım daveti içersin; kullanıcının tercihine göre takip/yorum daveti de eklenebilir. Konuşmaya sığmayan çağrıları sıkıştırma.

## Görüntü ve yazılar
- Dikey 9:16; en az 720×1280. Gerçek lisanslı stok öncelikli. Eksik eylem için gerçekçi yapay canlandırma kullanılabilir; bunu gerçek hasta kaydı gibi sunma ve sahne boyunca etiketle.
- İşlemi gösteren sahneyi anatomik yer, el hareketi ve yaşa uygunluk bakımından kare kare kontrol et. Hatalı uygulama görüntüsünü doğru tekniğin altında gösterme.
- Krem/lacivert temel, sarı ve pembe vurgu. Altyazıları 2–4 kelimelik okunaklı parçalara böl; bir anda en fazla iki satır. Ana mesaj kartı 2–5 kelime olsun.
- Yazılar 120–180 ms içinde hafifçe belirsin veya %108'den %100'e otursun. Her kelimeyi zıplatma; başlık, adım numarası, süre ve düzeltme vurgularını sırayla kullan.
- Yüzü, bası yerini ve gösterilen nesneyi kapatma. Alt platform kontrolleri ve sağ etkileşim alanı için boşluk bırak. Yatay stokun önemli kısmı kırpılıyorsa hareketli bulanık arka plan üzerinde tam kadrajı koru.
- Konuşmanın anlamı değiştiğinde kes; kısa geçişleri ara sahnelerde ölçülü kullan. Avatar sınırında dudak uyumunu bozacak çapraz geçiş yapma. Ses efektleri/müzik konuşmayı örtmesin; zorunlu değildir.
- Süre gösterimi tıbbi süreyi yanlış öğretmesin: örneğin dakikalar saniyeler içinde bitmiş gibi gösterilmesin.

## Doğrulama ve teslim
Tıbbi metni resmi çocuk hastanesi/meslek kuruluşu kaynaklarıyla doğrula; protokoller farklıysa farkı kaynak notunda belirt. Kullanıcının güvenli klinik tercihini koru; ağır belirtilerde bekleme izlenimi oluşturma. Kaynakları konuşmanın dışında tut.

Üretilen sesin süresini ölç. Avatarın gerçek konuşmasını yazıya çevirerek metinle karşılaştır. Sadece kapsayıcı sürelerinin eşleşmesi kusursuz dudak uyumu kanıtı değildir. Son videoyu baştan sona çözüp süre, görüntü/ses, kare sayısı, yazı yerleşimi ve avatar aralıklarını doğrula.

Özel portre, API anahtarı, ham lisanslı stok ve ücretli sonuçlar public Git'e eklenmez. Ücretli işlem kayıtları korunur; kesintide aynı işten devam edilir. Sosyal paylaşım ayrı yetki gerektirir. Bu stil belgesi, günlük zamanlayıcının veya sosyal paylaşımın etkin olduğu anlamına gelmez.

## Uygulama bağlantıları
`automation.gemini_avatar --duration 10 --performance energetic` enerjik avatar seçeneğini etkinleştirir. `automation.reels_captions.write` kısa hareketli altyazıları ve zamanlanmış vurgu kartlarını üretir; `render_hybrid(..., narration_delay=0, caption_writer=...)` ile kullanılabilir. Varsayılan eski çağrılar ve kayıt kimlikleri korunur; üslup değişikliği yeni bir ücretli üretim kimliği oluşturur. Video, altyazı ve işlem kayıtları doğrulanmadan başarı ilan edilmez.
