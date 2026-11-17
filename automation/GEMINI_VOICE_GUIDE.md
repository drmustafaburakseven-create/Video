# Gemini + ElevenLabs Voice Changer: çalışan örnek

17 Kasım 2026: Kullanıcının yükleme yaptığını bildirmesinden sonra tek, açıkça
adlandırılmış yeni deneme gönderildi. **Gemini video üretimi ve ElevenLabs ses
dönüşümü başarıyla tamamlandı.** Fal kullanılmadı.

## Hazır dosyalar

- Kısa konuşan avatar: `video-output/Mustafa-Konusan-Avatar-4sn.mp4`.
- Tam video: `video-output/Ek-Gida-Mustafa-Avatarli-60sn.mp4`.
- Kurgu ve doğrulama kayıtları: `video-output/ek-gida-gemini-avatar-60s/`.

Bu dosyalar özel çalışma alanındadır; public Git deposuna video veya portre
kopyalanmadı. Göreli dosya yolları GitHub üzerinde indirme bağlantısı değildir.

Tam video 60 saniye, 720×1280 ve 1.440 kare: **4 saniye konuşan avatar +
56 saniye tekrarsız hareketli stok**. Açılışta “Ek gıdaya hazır mı?” denir;
önceki uzun ilk soru bütünüyle çıkarılır, kalan özgün ElevenLabs anlatımı korunur.
Ses hızlandırılmaz. Avatar görüntüsü ve konuşması aynı anda başlar; eski
250 milisaniyelik anlatım gecikmesi bu kurguya uygulanmaz.

## Yapılan kontroller

- Gemini'nin özgün konuşması ve dönüştürülen konuşma ayrı ayrı yazıya çevrildi;
  ikisi de tam olarak “Ek gıdaya hazır mı?” sonucunu verdi.
- Kelime başlangıç zamanları eşleşti; bitiş zamanları en fazla 40 ms farklıydı.
- Dönüştürülen MP3'ün ölçülen kapsayıcı süresi 4,075102 saniye; çözülen PCM
  yaklaşık 4,040272 saniye. Kodlama payı yüzünden bu ölçüler aynı değildir.
- Temsili karelerde belirgin yüz bozulması görülmedi. Algısal ses benzerliği
  ve sürekli dudak uyumunun son değerlendirmesi kullanıcıya aittir.
- Tam 60 saniyelik dosya FFmpeg ile baştan sona çözüldü. Sentetik avatar etiketi
  yalnız avatarın bulunduğu ilk dört saniyede gösterilir.
- Sosyal medyada otomatik yayın veya günlük sunucu dağıtımı yapılmadı.

## Aynı başarılı işlemi yeniden kullanma

```bash
.venv/bin/python -m automation.gemini_avatar \
  --portrait automation/private/portrait.jpg \
  --speech 'Ek gıdaya hazır mı?' --duration 4 \
  --attempt billing-funded-20261117
```

Aynı fotoğraf, cümle, süre, model ve deneme adı kayıtlı sonucu kullanır.
İşlem kayıtları `video-output/journal/` altında korunmalıdır. Yeni deneme adı,
metin, fotoğraf veya model yeni ücretli üretim oluşturabilir; aynı sorun için
rastgele adlarla tekrar tekrar istek gönderilmemelidir.

İlk başarısız isteğin kaydı da korunuyor. `--attempt` olmadan eski dört saniyelik
cümle çalıştırılırsa o eski `RESOURCE_EXHAUSTED` sonucu görülür; bu, son başarılı
isteğin yeniden başarısız olduğu anlamına gelmez.

## Önceki hatanın durumu

Eski istek model çıktısı oluşmadan `RESOURCE_EXHAUSTED` ile duruyordu. İstek biçimi
resmî belgeyle uyumluydu. Kullanıcının hesap yüklemesi sonrasındaki yeni deneme
çalıştı. Kesin proje katmanı ve yüklenen tutar API yanıtından öğrenilmediği için
"hesap kesin Tier 1 oldu" veya eski hatanın ayrıntılı fatura nedeni ileri sürülmüyor.

Omni ücretsiz API katmanında desteklenmiyor. İleride erişim sorunu olursa aynı
projeye yeni anahtar üretmek yerine etkin proje limitleri ve faturalandırma
kontrol edilir. Model listesinin HTTP200 dönmesi video erişimini kanıtlamaz.

- [Omni limitleri](https://aistudio.google.com/docs/rate-limits#gemini-omni-flash-rate-limits)
- [Proje sorunlarını giderme](https://aistudio.google.com/docs/troubleshooting)
- [ElevenLabs ses dönüştürme](https://elevenlabs.io/docs/api-reference/speech-to-speech/convert)

Bu komut kısa avatarı üretir. 60 saniyelik çalışan örnek, kayıtlı anlatım ve
incelenmiş stoklarla ayrıca birleştirildi; günlük studio'nun eski Fal/ElevenLabs
avatar yolunun yeni yöntemle otomatik olarak değiştiği varsayılmamalıdır.
