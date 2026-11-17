# Gemini + ElevenLabs Voice Changer: durum ve devam adımları

Kullanıcının seçtiği yöntem: Gemini kendi fotoğrafından konuşmalı kısa sahneyi
üretir; ElevenLabs bu sahnenin konuşmasını Mustafa B. Seven klon sesine çevirir.
Fal hesabı bu yol için gerekmez. Bu yöntem önceki hazır TTS kaydını Gemini'ye
dudak hareketi kaynağı olarak vermez; videonun üretilen konuşmasını dönüştürür.

## Canlı olarak doğrulananlar

17 Kasım 2026 kontrolü:

- Kullanıcının özgün portresi özel klasörde hazır; yeniden istenmemeli.
- Gemini'nin dört saniyelik fotoğraf+konuşma isteği, belgelenen biçime uygun.
  Mevcut işleme tekrar bakıldı: model çıktısı oluşmadan `RESOURCE_EXHAUSTED`
  ile durmuş. Yanıt, gerçek proje katmanını veya bakiye miktarını göstermiyor.
- Bu kontrolde aynı Gemini üretimi yeniden satın alınmadı. Yeni komut varsayılan
  cümleyle aynı kayıtlı işlemi bulup ücretli POST göndermeden hatayı gösteriyor.
- ElevenLabs **Voice Changer gerçekten çalıştı**: mevcut dört saniyelik kendi
  ses parçası `eleven_multilingual_sts_v2` ile klon sese dönüştürüldü. Çıktı
  4,075102 saniye; fark 0,075102 saniye ve 0,15 saniyelik süre kontrolü geçti.
- Bu ses denemesi bir Gemini videosundan alınmadı; yüz veya dudak uyumunun
  doğrulandığı anlamına gelmez. Henüz konuşan avatar videosu oluşmadı.

## Gemini hatasını ayırmak için gereken tek hesap bilgisi

[Google AI Studio API anahtarları](https://aistudio.google.com/api-keys) veya
[projeler](https://aistudio.google.com/projects) sayfasında, bu API anahtarına
ait projenin **Billing Tier / Plan** bilgisine bakılmalı. Anahtar değeri paylaşılmaz.

- **Free:** Gemini Omni ücretsiz API katmanında desteklenmiyor. Aynı projede
  başka anahtar üretmek çözmez. Google'ın faturalandırma kurulumu tamamlanmalı;
  uygun hesaplarda en az 5 USD ön ödeme adımı olabilir. Kart bilgisi yalnız
  Google'ın kendi sayfasına girilir. Bu işlem burada yapılmadı.
- **Tier 1 veya üzeri:** [Gerçek proje limitleri](https://aistudio.google.com/rate-limit?timeRange=last-28-days)
  içinde `gemini-omni-1.2-flash` kontrol edilmeli. Resmî başlangıç limitleri
  Tier 1 için dakikada 8, günde 40 istek; hesabın etkin limitleri esas alınır.
  Kullanım, harcama sınırı ve geçici sağlayıcı kapasitesi ayrıca incelenmeli.

Gemini uygulama aboneliği, aynı Google hesabındaki API projesinin ücretli video
katmanında olduğunu kanıtlamaz. Model listesinin HTTP200 dönmesi de yeterli değil.
`RESOURCE_EXHAUSTED` tek başına "bakiyeniz bitti" anlamına gelmez; kesin proje
katmanı ve etkin limitler henüz görülemedi.

Resmî açıklamalar:

- [Omni limitleri](https://aistudio.google.com/docs/rate-limits#gemini-omni-flash-rate-limits)
- [Hesap ve proje sorunlarını giderme](https://aistudio.google.com/docs/troubleshooting)
- [Faturalandırma](https://aistudio.google.com/docs/billing)
- [ElevenLabs ses dönüştürme](https://elevenlabs.io/docs/api-reference/speech-to-speech/convert)

## Hazır kısa örnek komutu

Depo kökünde aşağıdaki komut, ilk başarısız kaydı yeniden sorgular; yeni bir
ücretli üretime dönüşmez:

```bash
.venv/bin/python -m automation.gemini_avatar \
  --portrait automation/private/portrait.jpg \
  --speech 'Ek gıdaya hazır mı?' --duration 4
```

Hesapta anlamlı bir değişiklik doğrulandıktan sonra tek yeni deneme açıkça
adlandırılabilir. Örneğin faturalandırma erişimi gerçekten düzeltildiyse:

```bash
.venv/bin/python -m automation.gemini_avatar \
  --portrait automation/private/portrait.jpg \
  --speech 'Ek gıdaya hazır mı?' --duration 4 \
  --attempt billing-fixed-20261117
```

**İkinci komut yeni ücretli istek başlatabilir.** Aynı adı tekrar kullanmak
aynı işlemi sürdürür; rastgele adlarla tekrar tekrar deneme yapılmamalı. Kaydı
silmek gerekmez. Google erişimi düzelmeden bu örnek çalıştırılmadı.

Video gelirse özgün konuşma çıkarılır, sessiz kayıtlar reddedilir, ses kimliği
dönüştürülür ve video kareleri değiştirilmeden yeni ses birleştirilir. Fazla
süre farkında hızlandırma veya kesme yapılmaz; dosyalar inceleme için korunur.
Yüz benzerliği, söylenen Türkçe metin ve dudak uyumu izlenerek değerlendirilmeli.

Bu komut tek kısa denemedir; 60 saniyelik günlük studio akışına otomatik geçiş
değildir. Mevcut 60 saniyelik stok önizleme korunuyor. Başarılı avatar örneği
görülmeden eski Fal/ElevenLabs avatar yolunu yeni yöntemmiş gibi çalıştırmayın.
