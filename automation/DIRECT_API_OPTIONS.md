# Fal olmadan konuşan avatar seçenekleri

17 Kasım 2026 kontrolü. Kullanıcının hedefi kendi fotoğrafı ve kendi sesiyle
günlük bir video; ek bütçe en fazla 4.000 TL/ay. Fal zorunlu değildir.
Kullanıcının seçilen ikinci fotoğrafı özel klasörde hazırdır; yeniden yüklenmesi
gerekmez. Fotoğraf Git deposunda paylaşılmaz.

## Mevcut hesaplarla Gemini + ElevenLabs

Alternatif sıra şöyledir:

1. Gemini, kullanıcının fotoğrafından kısa bir konuşmalı video üretir.
2. Videonun konuşması ElevenLabs **Voice Changer** ile Mustafa B. Seven klon
   sesine dönüştürülür.
3. Dönüştürülmüş sesin süresi ve dudak uyumu kontrol edilir, ardından kurguya alınır.

Bu yöntem, önceden hazırlanmış ElevenLabs sesini Gemini'ye dudak hareketi için
girdi olarak vermekten farklıdır. Gemini Omni'nin mevcut API'si yüklenen ses
girdilerini/referanslarını kabul etmiyor; referans videonun sesi de yok sayılıyor.
Voice Changer ise özgün konuşma performansının zamanlamasını ve anlatımını
korumayı hedefliyor. Birebir aynı süre, ses benzerliği ve dudak uyumu ancak
üretilen örnek üzerinde doğrulanabilir.

Türkçe destekleyen ElevenLabs modeli `eleven_multilingual_sts_v2`, adresi
`POST /v1/speech-to-speech/{voice_id}`. Standart MP3 çıktı için Pro paket
gerekliliği belgelenmiyor; bu hesabın canlı Voice Changer yetkisi henüz denenmedi.

**Canlı deneme:** Gemini `gemini-omni-1.2-flash` ile kendi portresi ve kısa
Türkçe cümlesi kullanılan tek bir dört saniyelik istek yapıldı. İşlem
`RESOURCE_EXHAUSTED` ile başarısız oldu; video oluşmadı. Yanıt kota ile geçici
sağlayıcı kapasitesini birbirinden ayırmıyor. API anahtarıyla model listesinin
okunabilmesi, video üretim kotasını doğrulamaz. İşlem kimliği yerel journal'da
saklandı; otomatik tekrar yapılmadı. Video çıkmadığı için ses dönüştürme aşaması
başlatılmadı. Bu yol henüz çalışan uçtan uca avatar akışı değildir.

Kaynaklar:

- [Gemini Omni ve sınırlamaları](https://ai.google.dev/gemini-api/docs/omni#limitations)
- [ElevenLabs Voice Changer](https://elevenlabs.io/docs/overview/capabilities/voice-changer)
- [Ses dönüştürme API'si](https://elevenlabs.io/docs/api-reference/speech-to-speech/convert)

## Seedance 2.5 doğrudan API

Resmî BytePlus belgelerinde doğrudan API erişimi mevcut:

- Model: `dreamina-seedance-2-5-260628`.
- Adres: `POST https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks`.
- Yetkilendirme: BytePlus ModelArk API anahtarı; uygulamada `ARK_API_KEY` olarak tutulabilir.
- Klip süresi: 4–30 saniye. Görüntü ve `reference_audio` rolünde ses referansı destekleniyor.

Gerçek kişiye ait yüz fotoğrafını doğrudan ham dosya olarak gönderme yöntemi
desteklenmiyor. Resmî **Portrait Asset** sürecinde kişinin doğrulanması ve
onayından sonra fotoğraf/ses varlık kütüphanesine kaydediliyor; üretimde
`asset://...` kimliği kullanılıyor. Bu süreç kullanıcının hesabında tamamlanmalı.

Model aktivasyonu için belgede alternatifler var: 30 USD üzeri bakiye, en az
30 USD tutarlı ilgili Savings Plan veya kullanılabilir kaynak paketi. Bu,
herkese zorunlu aylık 30 USD abonelik olduğu anlamına gelmez. Güncel saniye
fiyatı güvenilir biçimde çıkarılamadığı için burada toplam maliyet vaat edilmiyor.

Ses referansı desteği, mevcut ElevenLabs kaydının birebir aynı zamanlamayla
korunacağı garantisi değildir. Önce kısa bir örnekte Türkçe konuşma, yüz ve
dudak uyumu kontrol edilmeli. Gemini anahtarı bu serviste kullanılamaz.
Bu ortamda BytePlus anahtarı veya doğrulanmış portre varlık kimliği bulunmuyor;
Seedance'a fotoğraf yüklenmedi ve ücretli üretim isteği gönderilmedi.

Kaynaklar:

- [Seedance ürün sayfası](https://www.byteplus.com/en/product/seedance)
- [Video oluşturma API'si](https://docs.byteplus.com/en/docs/ModelArk/create-video-generation-task-api)
- [Portre doğrulama ve varlık rehberi](https://docs.byteplus.com/en/docs/ModelArk/seedance-portrait-asset-guide)
- [Seedance 2.5 rehberi](https://docs.byteplus.com/en/docs/ModelArk/seedance-2-5)
- [Fiyatlandırma](https://docs.byteplus.com/en/docs/ModelArk/model-pricing)

## Diğer doğrudan yollar

ElevenLabs Aurora API mevcut, ancak bu hesaptaki aktif Creator planı video
API'sinde `402 / Pro plan or above` yanıtı veriyor. Bu engel Voice Changer ile
aynı özellik veya aynı paket şartı olarak yorumlanmamalı.

Creatify Aurora'nın kendi API'si de fotoğraf ve mevcut sesi kabul ediyor;
resmî API Starter fiyatı 99 USD/ay. Son doğrulanan kurla yaklaşık 4.989 TL,
vergiler hariç; 4.000 TL ek bütçeye uygun bir yeni abonelik olarak önerilmiyor.
Kaynaklar: [Aurora API](https://docs.creatify.ai/api-documentation/aurora/aurora.md),
[API fiyatı](https://docs.creatify.ai/billing.md).

Bu araştırmada yeni hesap açılmadı, kredi veya abonelik satın alınmadı.
Mevcut 60 saniyelik hareketli stok önizlemesi ve özgün ElevenLabs ses kaydı
korunuyor; bu önizleme hâlâ konuşan avatar içermiyor.
