# Dr. Mustafa Burak Seven — kalıcı Reels / Shorts kuralları

Bu kurallar konuya özgü değildir. Son kullanıcı tercihi önce gelir. Güncelleme: 17 Kasım 2026.

## Anlatıcı ve amaç
Çocuk doktoru ve ebeveynlere pratik bilgi veren bir içerik üreticisi gibi konuş: sıcak, canlı, doğrudan, öğretici. Eğlenceyi doğal ses performansına, mimiklere ve kurguya taşı; çocukların korkusu, kanaması veya hastalığıyla şaka yapma. Korkutarak izletme, suçlama, kesin sonuç veya viral olma garantisi verme. İzleyicinin başka bir ebeveyne gönderebileceği tek uygulanabilir mesaj üret.

## Editör planı önce gelir
Ses satın almadan veya görüntü üretmeden önce her cümle için gösterilecek eylemi yaz: kim, nerede, ne yapıyor, neyi anlamayı sağlıyor? Yalnızca “çocuk”, “doktor”, “telefon” anahtar kelimeleri eşleştiği için stok seçme. Mutfakta zamanlayıcı veya ilgisiz muayene gibi bağlam dışı çekimler kullanılmaz.

Uygulama anlatımında aynı kişi/ortam/giysi ve işlemin devamlılığı korunur. Her görüntünün anlatılan cümleyle ilişkisi açık olmalıdır. Doğru uygulama gösterimi, süre tutma ve yardım isteme ayrı sahneler olarak planlanır. Yeni ses ölçüldükten sonra kesmeler gerçek kelime zamanlarına göre ayarlanır. Uygun stok yoksa bunu açık belirt ve eksik eylemi gerçekçi canlandırmayla tamamla; yapay çekimi gerçek stok diye tanıtma.

## Metin ve seslendirme sırası
1. Kullanıcı konuyu verir. Önce 60 saniyelik bütün metni sosyal medya metin yazarı gibi kurgula: doğrudan açılış, ilk açıklamada cevap, uygulanabilir adımlar, kısa kapanış.
2. Mustafa’nın Yazı Tarzı becerisini uygula: samimi, kısa, doğal, sahiplenen konuşma; “Önce…”, “Şimdi…”, “Püf noktası şu…” gibi gündelik bağlantılar. Kurumsal broşür dili veya monoton ders anlatımı kullanma. Klinik doğruluk önceliklidir.
3. Ara anlatımın tonu karşındaki aileye konuşan doğal bir çocuk doktoru gibi tutarlı olmalı: sıcak, güven veren, ölçülü. Cümle başına farklı duygu rolü, spiker tonu, büyük harfli sert vurgu, aşırı coşku veya robotik okuma kullanma. Az ve genel ses yönlendirmesi tercih et. Kritik bilgiyi anlaşılır söyle; acil uyarıyı teatralleştirme. Kullanıcının beğendiği metni yalnızca ton için yeniden yazma.
4. Ses üretmeden mevcut kullanıcı klonunun erişilebilir olduğunu doğrula. Eski kimlik bulunamıyorsa hesabın kendi klonlarını listele; aynı isim ve sahipliği doğrulanan güncel kaydı kullan, belirsizlikte rastgele ses seçme. Ara görüntülerin anlatımını mevcut kullanıcı klonuyla ElevenLabs `eleven_v4` üzerinden üret. Model erişimini doğrula; v4 kullanmadıysan kullanmış gibi raporlama. Desteklenen köşeli parantez içi ses yönlendirmeleri ayrı üretim metnindedir; temiz konuşma metnine dahil edilmez. SSML break veya desteklenmeyen style/speaker_boost parametreleri gönderme.
5. Seslendirme çıktıktan sonra metni ve gerçek süreyi kontrol et, görüntü kesmelerini bu sesin anlamına uydur. Fazla uzun sesi hızlandırma veya sözcük kesme; metni uygun uzunlukta yeniden yaz. Canlı akışı gereksiz sessizlikle bölme; yapay duraklar ekleyerek performansı parça parça birleştirme. Öncelik tek, doğal akan ses kaydıdır.
6. Kullanıcının beğendiği mevcut avatar performansı yeniden kullanılabilir; dudak uyumunu bozmamak için bu görüntünün mevcut sesini koru. Orta bölümün yeni v4 sesi, onaylanmış avatar sesini değiştirmek zorunda değildir.

## Süre ve sahneler
- Varsayılan toplam 60 saniye: 0–10 saniye kullanıcının konuşan avatarı, 10–50 saniye hareketli açıklayıcı çekimler, 50–60 saniye konuşan avatarı.
- Avatar kullanıcının özel portresinden oluşturulur. Gemini doğal konuşma performansı → ElevenLabs Voice Changer ile mevcut klon ses → ses zamanlaması korunarak kurgu.
- Son kullanıcı tercihi: yeni avatar üretimlerinde `--performance conversational` kullan. Aileyle muayenede kendiliğinden konuşuyormuş gibi sıcak ve ölçülü anlat; canlılığı zorlanmış mimikten değil konudan ve doğal konuşmadan al. İlk yarım saniyede konuşma hedefle; gerçek başlangıcı ölç. Eller dinlensin; sürekli kaş kaldırma, ritmik baş sallama, sabit gülümseme, işaret etme, ağız hareketini büyütme ve sunucu oyunculuğu isteme. Yüzün doğal dokusunu koru. `energetic` yalnız kullanıcı yeniden özellikle istediğinde kullanılır.
- İlk iki saniyede konu veya yaygın hata açık olsun. Selamlama, uzun unvan veya logo açılışı kullanma. Üç açılış taslağı içinden birini seç; vaat edilen yanıtı açıklamanın başında ver.
- Ara sahneler anlamlı 2–4 saniyelik parçalar olsun. Aynı kaynağın farklı, kullanılmamış zaman aralıkları kullanılabilir. Fotoğraf kaydırma, donmuş kare, tekrar döngüsü ve hızlandırılmış konuşma yok.
- Kullanıcının görünmediği 40 saniyelik bölümde en az dört farklı hareketli kaynak ve en az dört anlamlı sahne bulunmalı. Oturuş/eylem, uygulamanın yakın planı, süre takibi ve yardım isteme gibi farklı anlatım görevleri planla. Tek çekimi bölmek, yakınlaştırmak veya açı değiştirmek tek başına bu çeşitlilik şartını karşılamaz. Kesmeyi cümlenin anlamına uydur; yalnız kesme sayısını artırmak için görüntüyü bölme.
- Giriş ve çıkışın onar saniyelik beğenilmiş performansını kesintisiz koru. Kaynak görüntü ile ona ait Voice Changer sesini aynı sıfır noktasında, aynı hızda kullan; sözcük veya hece kesme, ses kaydırma, avatarın üzerine farklı zamanlamalı TTS yerleştirme. Ara anlatım tek doğal kayıttan aksın; görüntü geçişleri konuşmayı kesmesin. Yeni ses kullanılırsa dudak eşleşmesi yeniden kontrol edilmelidir.
- Kapanış kısa bir hatırlatma ve doğal paylaşım daveti içersin; kullanıcının tercihine göre takip/yorum daveti de eklenebilir. Konuşmaya sığmayan çağrıları sıkıştırma.

## Görüntü ve yazılar
- Dikey 9:16; en az 720×1280. Gerçek lisanslı stok öncelikli. Eksik eylem için gerçekçi yapay canlandırma kullanılabilir; bunu gerçek hasta kaydı gibi sunma; kaynak ve yapay üretim bilgisini ayrı üretim kayıtlarında koru.
- İşlemi gösteren sahneyi anatomik yer, el hareketi ve yaşa uygunluk bakımından kare kare kontrol et. Hatalı uygulama görüntüsünü doğru tekniğin altında gösterme.
- Küçük öğretici hareketlerde temas noktası, yön, el/parmak anatomisi, duruş ve hareket boyunca devamlılık ayrı ayrı kontrol edilir. Uygun resmî kaynak ve gerektiğinde kullanıcının onayladığı referans kare → kısa hareket denemesi → uzun çekim sırasını izle. Referans karenin onayı, üretilen her videonun otomatik klinik onayı değildir. Promptun doğru olması, gerçekçi görünüm veya tek bir iyi kare yeterli kanıt sayılmaz.
- Hatalı veya incelemesi bitmemiş klinik çekimleri dosya özetiyle birlikte `*.mp4.clinical-review.json` kaydında `rejected` / `review_required` olarak işaretle. Renderer bu kayıtları engeller. `approved` yalnız gerçekten incelenen aynı dosya baytları için geçerlidir; değişen dosya yeniden incelenir. Yalnız bir aralık kullanılabiliyorsa onu ayrı hareketli dosyaya çıkarıp ayrıca incele; reddedilmiş aslı arşivde tut. Bu koruma tıbbi doğruluk modeli değildir; kaydı olmayan çekimler için görsel inceleme sorumluluğu devam eder.
- Son kullanıcı tercihi: video tamamen yazısızdır. Altyazı, üst isim/unvan, “Yapay zekâ ile oluşturulmuştur” yazısı, başlık, vurgu kartı ve ek zamanlayıcı grafiği yakılmaz. Temiz görüntü, ses ve hareketli kurgu teslim edilir.
- Kaynak, yapay üretim kaydı ve isteğe bağlı erişilebilirlik altyazısı ayrı dosyalarda tutulabilir; bunlar MP4'e altyazı akışı olarak da eklenmez. Bu tercih üretim kaynağını değiştirmez veya gerçek hasta çekimi iddiası yaratmaz.
- Kullanıcı ileride yazı isterse krem/lacivert, sarı/pembe vurgulara dönülebilir. Yüz ve gösterilen uygulama kapatılmaz; platform güvenli boşlukları korunur.
- Yatay stokun önemli kısmı kırpılıyorsa hareketli bulanık arka plan üzerinde tam kadrajı koru.
- Konuşmanın anlamı değiştiğinde kes; kısa geçişleri ara sahnelerde ölçülü kullan. Avatar sınırında dudak uyumunu bozacak çapraz geçiş yapma. Ses efektleri/müzik konuşmayı örtmesin; zorunlu değildir.
- Süre gösterimi tıbbi süreyi yanlış öğretmesin: örneğin dakikalar saniyeler içinde bitmiş gibi gösterilmesin.

## Doğrulama ve teslim
Tıbbi metni resmi çocuk hastanesi/meslek kuruluşu kaynaklarıyla doğrula; protokoller farklıysa farkı kaynak notunda belirt. Kullanıcının güvenli klinik tercihini koru; ağır belirtilerde bekleme izlenimi oluşturma. Kaynakları konuşmanın dışında tut.

Üretilen sesin süresini ölç. Avatarın gerçek konuşmasını yazıya çevirerek metinle karşılaştır. Sadece kapsayıcı sürelerinin eşleşmesi kusursuz dudak uyumu kanıtı değildir. Son videoyu baştan sona çözüp süre, görüntü/ses, kare sayısı, yazı yerleşimi ve avatar aralıklarını doğrula.

Her teslim iPhone Fotoğraflar, Instagram Reels ve YouTube Shorts için dikey MP4 olarak hazırlanır: 9:16, 60 saniye, 720×1280, sabit 24 kare/sn, H.264 Main Level 3.1 / avc1 / yuv420p / BT.709, AAC-LC 48 kHz stereo ve fast-start. `python -m automation.iphone_export KAYNAK.mp4 YENI-HEDEF.mp4` ile ayrı bir kopya çıkar; süreyi, akışları, kare hızını, dosya başlığını ve tam çözümlemeyi doğrula. Altyazı akışı ekleme. Gerçek telefonda açılma veya sosyal platforma yükleme denenmediyse denenmiş gibi raporlama.

Özel portre, API anahtarı, ham lisanslı stok ve ücretli sonuçlar public Git'e eklenmez. Ücretli işlem kayıtları korunur; kesintide aynı işten devam edilir. Sosyal paylaşım ayrı yetki gerektirir. Bu stil belgesi, günlük zamanlayıcının veya sosyal paylaşımın etkin olduğu anlamına gelmez.

## Uygulama bağlantıları
`automation.gemini_avatar --duration 10 --performance conversational` doğal sohbet performansını etkinleştirir. Mustafa’nın Yazı Tarzı ve MBS Reels/Shorts becerilerindeki konuşma dilini güncel kullanıcı tercihleriyle uygula; bu beceriler gerçek bir ses/mimik ölçümü veya kusursuz benzerlik garantisi değildir. `render_hybrid(..., narration_delay=0, overlays=False)` yazısız çıktı üretir. `automation.reels_captions.write` yalnız kullanıcı yeniden yazılı sürüm istediğinde kullanılır. Varsayılan eski çağrılar ve kayıt kimlikleri korunur; üslup değişikliği yeni bir ücretli üretim kimliği oluşturur. Video, altyazı ve işlem kayıtları doğrulanmadan başarı ilan edilmez.
