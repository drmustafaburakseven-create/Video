# Dr. Mustafa Burak Seven — kalıcı Reels / Shorts kuralları

Bu kurallar konuya özgü değildir. Son kullanıcı tercihi önce gelir. Güncelleme: 17 Kasım 2026.

## Anlatıcı ve amaç
Çocuk doktoru ve ebeveynlere pratik bilgi veren bir içerik üreticisi gibi konuş: sıcak, canlı, doğrudan, öğretici. Eğlenceyi doğal ses performansına, mimiklere ve kurguya taşı; çocukların korkusu, kanaması veya hastalığıyla şaka yapma. Korkutarak izletme, suçlama, kesin sonuç veya viral olma garantisi verme. İzleyicinin başka bir ebeveyne gönderebileceği tek uygulanabilir mesaj üret.

## Metin ve seslendirme sırası
1. Kullanıcı konuyu verir. Önce 60 saniyelik bütün metni sosyal medya metin yazarı gibi kurgula: doğrudan açılış, ilk açıklamada cevap, uygulanabilir adımlar, kısa kapanış.
2. Mustafa’nın Yazı Tarzı becerisini uygula: samimi, kısa, doğal, sahiplenen konuşma; “Önce…”, “Şimdi…”, “Püf noktası şu…” gibi gündelik bağlantılar. Kurumsal broşür dili veya monoton ders anlatımı kullanma. Klinik doğruluk önceliklidir.
3. Metnin duygu planını ayrıca hazırla: sıcak güven verme, merak, önemli noktada belirgin vurgu ve acil uyarıda ciddi/net ton. Kanama gibi konularda kahkaha, alay veya neşeli acil uyarı yok.
4. Ara görüntülerin anlatımını mevcut kullanıcı klonuyla ElevenLabs `eleven_v4` üzerinden üret. Model erişimini doğrula; v4 kullanmadıysan kullanmış gibi raporlama. Desteklenen köşeli parantez içi ses yönlendirmeleri ayrı üretim metnindedir; temiz konuşma metnine dahil edilmez. SSML break veya desteklenmeyen style/speaker_boost parametreleri gönderme.
5. Seslendirme çıktıktan sonra metni ve gerçek süreyi kontrol et, görüntü kesmelerini bu sesin anlamına uydur. Fazla uzun sesi hızlandırma veya sözcük kesme; metni uygun uzunlukta yeniden yaz. Canlı akışı gereksiz sessizlikle bölme.
6. Kullanıcının beğendiği mevcut avatar performansı yeniden kullanılabilir; dudak uyumunu bozmamak için bu görüntünün mevcut sesini koru. Orta bölümün yeni v4 sesi, onaylanmış avatar sesini değiştirmek zorunda değildir.

## Süre ve sahneler
- Varsayılan toplam 60 saniye: 0–10 saniye kullanıcının konuşan avatarı, 10–50 saniye hareketli açıklayıcı çekimler, 50–60 saniye konuşan avatarı.
- Avatar kullanıcının özel portresinden oluşturulur. Gemini doğal konuşma performansı → ElevenLabs Voice Changer ile mevcut klon ses → ses zamanlaması korunarak kurgu.
- Yeni avatar üretimlerinde `--performance energetic` kullan. İlk yarım saniyede konuşma hedefle; gerçek başlangıcı ölç. Doğal vurgu, kısa durak, ölçülü mimik/el hareketi; bağırma veya yapay oyunculuk yok.
- İlk iki saniyede konu veya yaygın hata açık olsun. Selamlama, uzun unvan veya logo açılışı kullanma. Üç açılış taslağı içinden birini seç; vaat edilen yanıtı açıklamanın başında ver.
- Ara sahneler anlamlı 2–4 saniyelik parçalar olsun. Aynı kaynağın farklı, kullanılmamış zaman aralıkları kullanılabilir. Fotoğraf kaydırma, donmuş kare, tekrar döngüsü ve hızlandırılmış konuşma yok.
- Kapanış kısa bir hatırlatma ve doğal paylaşım daveti içersin; kullanıcının tercihine göre takip/yorum daveti de eklenebilir. Konuşmaya sığmayan çağrıları sıkıştırma.

## Görüntü ve yazılar
- Dikey 9:16; en az 720×1280. Gerçek lisanslı stok öncelikli. Eksik eylem için gerçekçi yapay canlandırma kullanılabilir; bunu gerçek hasta kaydı gibi sunma; kaynak ve yapay üretim bilgisini ayrı üretim kayıtlarında koru.
- İşlemi gösteren sahneyi anatomik yer, el hareketi ve yaşa uygunluk bakımından kare kare kontrol et. Hatalı uygulama görüntüsünü doğru tekniğin altında gösterme.
- Son kullanıcı tercihi: video tamamen yazısızdır. Altyazı, üst isim/unvan, “Yapay zekâ ile oluşturulmuştur” yazısı, başlık, vurgu kartı ve ek zamanlayıcı grafiği yakılmaz. Temiz görüntü, ses ve hareketli kurgu teslim edilir.
- Kaynak, yapay üretim kaydı ve isteğe bağlı erişilebilirlik altyazısı ayrı dosyalarda tutulabilir; bunlar MP4'e altyazı akışı olarak da eklenmez. Bu tercih üretim kaynağını değiştirmez veya gerçek hasta çekimi iddiası yaratmaz.
- Kullanıcı ileride yazı isterse krem/lacivert, sarı/pembe vurgulara dönülebilir. Yüz ve gösterilen uygulama kapatılmaz; platform güvenli boşlukları korunur.
- Yatay stokun önemli kısmı kırpılıyorsa hareketli bulanık arka plan üzerinde tam kadrajı koru.
- Konuşmanın anlamı değiştiğinde kes; kısa geçişleri ara sahnelerde ölçülü kullan. Avatar sınırında dudak uyumunu bozacak çapraz geçiş yapma. Ses efektleri/müzik konuşmayı örtmesin; zorunlu değildir.
- Süre gösterimi tıbbi süreyi yanlış öğretmesin: örneğin dakikalar saniyeler içinde bitmiş gibi gösterilmesin.

## Doğrulama ve teslim
Tıbbi metni resmi çocuk hastanesi/meslek kuruluşu kaynaklarıyla doğrula; protokoller farklıysa farkı kaynak notunda belirt. Kullanıcının güvenli klinik tercihini koru; ağır belirtilerde bekleme izlenimi oluşturma. Kaynakları konuşmanın dışında tut.

Üretilen sesin süresini ölç. Avatarın gerçek konuşmasını yazıya çevirerek metinle karşılaştır. Sadece kapsayıcı sürelerinin eşleşmesi kusursuz dudak uyumu kanıtı değildir. Son videoyu baştan sona çözüp süre, görüntü/ses, kare sayısı, yazı yerleşimi ve avatar aralıklarını doğrula.

Özel portre, API anahtarı, ham lisanslı stok ve ücretli sonuçlar public Git'e eklenmez. Ücretli işlem kayıtları korunur; kesintide aynı işten devam edilir. Sosyal paylaşım ayrı yetki gerektirir. Bu stil belgesi, günlük zamanlayıcının veya sosyal paylaşımın etkin olduğu anlamına gelmez.

## Uygulama bağlantıları
`automation.gemini_avatar --duration 10 --performance energetic` enerjik avatar seçeneğini etkinleştirir. `render_hybrid(..., narration_delay=0, overlays=False)` yazısız çıktı üretir. `automation.reels_captions.write` yalnız kullanıcı yeniden yazılı sürüm istediğinde kullanılır. Varsayılan eski çağrılar ve kayıt kimlikleri korunur; üslup değişikliği yeni bir ücretli üretim kimliği oluşturur. Video, altyazı ve işlem kayıtları doğrulanmadan başarı ilan edilmez.
