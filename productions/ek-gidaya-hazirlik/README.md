# Ek gıdaya hazırlık

Yaklaşık 6 aylık bebeklerin ebeveynleri için, Türkçe anlatımlı bir dikey kısa video.

- **İzle:** [Ek-Gidaya-Hazirlik.mp4](Ek-Gidaya-Hazirlik.mp4)
- 1080 × 1920, 9:16, 30 kare/sn; yaklaşık 44 saniye.
- Üç hazır oluş işareti, ilk denemede bebeğin isteğine saygı ve süt beslenmesinin sürmesi.
- Türkçe standart sentetik anlatıcı: Microsoft Edge `tr-TR-AhmetNeural`. Doktorun ses klonu değildir.
- Üç yapay zekâ fotoğrafı, yumuşak kamera hareketi ve ölçülmüş kelime zamanlarına göre altyazılar. Bunlar gerçek hasta görüntüleri veya gerçek video çekimi değildir; temsili görüntü etiketi videoda bulunur.
- Müzik, hasta verisi, API anahtarı veya sosyal medya yayını içermez.

## Yeniden üretme

Depo kökünde:

```bash
uv sync --frozen --no-dev --no-install-project
uv run --no-sync --no-project .venv/bin/python productions/ek-gidaya-hazirlik/render.py
```

FFmpeg ve ffprobe sistemde bulunmalıdır. Mevcut ses dosyası ve kelime zamanları tekrar kullanılır; yeni ses için Edge TTS internet bağlantısı gerekir. Kare tasarımı Pillow/FFmpeg, son ses ve altyazı birleştirmesi bu deponun `app.services.video.generate_video` işleviyle yapılır. Ana uygulama değiştirilmemiştir.

`render.py --stage prepare`, `--stage render` ve `--stage finish` aşamaları ayrı da çalıştırılabilir. Geçici görseller `build/` altında tutulur. `narration.txt`, `captions.srt` ve `timeline.json` düzenleme referanslarıdır; ana içerik `render.py` içindeki `SCENES` listesindedir. Metin değişirse eski ses ve zaman dosyaları yeniden kullanılmamalıdır.

## İçerik ve kaynak

Ana mesaj: Ek gıdaya geçişte yaklaşık altıncı ayla birlikte baş kontrolü, el–göz–ağız uyumu ve yutabilme birlikte değerlendirilir. İlk tekliflerde zorlanmaz, anne sütü veya formül mama sürer.

7 Kasım 2026 tarihinde kontrol edilen resmî kaynaklar:

- [NHS — Your baby's first solid foods](https://www.nhs.uk/baby/weaning-and-feeding/babys-first-solid-foods/)
- [NHS — How to start weaning your baby](https://www.nhs.uk/best-start-in-life/baby/weaning/how-to-start-weaning-your-baby/)

Bu kısa içerik zamanında doğmuş, genel gelişimi olağan bebekler için genel bilgilendirmedir. Prematürite veya yutma/gelişim sorunu varsa başlangıç bireysel değerlendirilir.

## Görsel üretim kaydı

Yerleşik görsel üretimiyle üç ayrı kare oluşturuldu. Ortak yönerge: doğal pencere ışığı, krem/pastel renkler, yaklaşık altı aylık kurgusal bebek; dik oturuş, sabit baş, görünür emniyet kemeri ve hemen yanında yetişkin; yazı/logo yok.

1. `assets/seated.png`: baş ve gövde kontrolünü gösteren orta genişlikte kadraj, yemek/kaşık yok.
2. `assets/coordination.png`: bebeğin kendi elindeki boş yumuşak kaşığa bakması ve ağzına yaklaştırması.
3. `assets/spoon.png`: yetişkinin az miktarda püreli kaşığı açık ağzın önünde tutup bebeğin isteğini beklemesi.

Kaşık görüntüsü el–göz–ağız uyumunu örnekler; tek bir fotoğraf hazır oluşu veya yutma güvenliğini kanıtlamaz.

## Açılış seçimleri

1. Günlük durum: “Elini ağzına götürüyor. Ek gıdaya hazır mı?”
2. Yanlış çıkarımı düzeltme: “Elini emmesi, ek gıdaya hazır olduğunu tek başına göstermez.”
3. Merak sorusu: “Ek gıdaya hazır mı?”

Üçüncü seçenek kullanıldı: kısa sorunun yanıtı hemen sonraki cümlede üç hazır oluş işaretiyle verilir. Ölçülmüş sahne zamanları `timeline.json` içindedir.
