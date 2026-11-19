# Çalışma düzeni

Bu beceri tek başına yeni sohbette konuşma metnini ve iki Google komutunu üretir. Dosya tabanlı kurgu için proje [Video](https://github.com/drmustafaburakseven-create/Video) ve içindeki [Reels Stüdyosu](https://github.com/drmustafaburakseven-create/Video/tree/main/reels-studyosu) kullanılır. Komutları depo kökünde çalıştır. Aşağıdaki özel klasör uyku rutini örneğinindir. Her konu ve sürüm için ayrı klasör kullan.

```bash
BOLUM=video-output/uyku-rutini
mkdir -p "$BOLUM"
cp -n reels-studyosu/konular/uyku-rutini.json "$BOLUM/bolum.json"
python3 reels-studyosu/studyo.py plan "$BOLUM/bolum.json" "$BOLUM/plan"
```

Yeni konuda örnek JSON'un alanlarını kullan. Başlık, kanca, soru, ilk cevap, gövde, kapanış, dört kısa kart, dört çekim, dört stok arama ifadesi, kaynaklar ve iki platformun ayrı metinlerini doldur. Plan adımı Python standart kütüphanesiyle çalışır. Sohbette önce plan klasöründeki konuşma ve iki Google komutunu göster.

1. Kullanıcının aynı özgün fotoğraftan aldığı sesli Google kliplerini özel bölüm klasörüne `giris.mp4` ve `cikis.mp4` olarak al. Hedef iki kez 10 saniyedir. Montaj yazılımı 8–10 saniyelik çekimleri de kabul eder. Bu durumda gerçek zaman çizelgesindeki farklılığı bildir.
2. Google kliplerini dinleyerek `zamanlar.json` içine `question`, `answer` ve `outro` için saniye cinsinden ölçülmüş başlangıç ve bitiş çiftlerini yaz. Her klibin sayacı sıfırdan başlar. Kapanışta son sözcükten sonra en az 1,5 saniye bırak. Şablondaki saniyeleri tahmin olarak kullanma.
3. Dört farklı lisanslı hareketli çekimi bölüm klasörüne `stok-1.mp4` … `stok-4.mp4` olarak koy. Her kaynak en az 11 saniye olsun. Pexels kullanılacaksa `stok-ara` adımı adayları getirir. Seçilen dört kimliği sırayla `secimler.json` içine yaz ve `stok-al` adımını çalıştır.
4. Doktor sesini üretme istendiğinde, yerleşik Python ortamıyla aşağıdaki adımları çalıştır. `ses` adımı ElevenLabs kotası kullanabilir. Hazır ve kontrol edilmiş sesler ile hizalama dosyası varsa doğrudan montaja geç. Kimlik bilgilerini ve ham kişisel medyayı özel çalışma alanında sakla.

   ```bash
   .venv/bin/python reels-studyosu/studyo.py ses "$BOLUM"
   .venv/bin/python reels-studyosu/studyo.py montaj "$BOLUM" "$BOLUM/teslim"
   ```

5. `Video-1080p.mp4`, `Video-Telefon.mp4` ve `paylasim.md` dosyalarını kontrol et. Telefon kopyasında H.264, yuv420p, AAC, hızlı açılma ve tam süreyi doğrula. Ses ve ağız uyumunu, ara sahnelerdeki öğretici hareketleri ve son 1,5 saniyeyi izle. Teslim bağlantısını gerçekten var olan dosyadan oluştur. Platforma yükleme ayrı işlemdir.
