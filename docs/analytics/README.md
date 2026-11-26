# Kanal analiz raporları

`channel-analytics.yml` iş akışı kanalın tam analiz görüntüsünü (video listesi, günlük
metrikler, Shorts/uzun video ayrımı, video başına metrikler, trafik kaynakları, abone
durumu, cihaz, ülke, yaş/cinsiyet ve son 40 videonun saniye saniye izleyici tutma
eğrisi) çeker.

**Repo herkese açık olduğu için rapor şifrelenerek commit edilir.** Dosya AES-256 ile,
AES anahtarı `report_key.pub.pem` (RSA-4096) ile şifrelenir. Açan özel anahtar repoda
değildir.

## Bir kerelik kurulum (kanal sahibi)

1. Google Cloud Console → **APIs & Services → Library** → **YouTube Analytics API**'yi
   etkinleştir (YouTube Data API v3 zaten açık).
2. **OAuth consent screen** → uygulama "Testing" modundaysa **Publish app** (yoksa token
   7 günde düşer).
3. Kendi bilgisayarında: `python scripts/youtube_refresh_token.py` → onay ekranında
   **YouTube Analytics** iznini de onayla → çıkan token'ı GitHub'da
   **Settings → Secrets and variables → Actions → `YOUTUBE_REFRESH_TOKEN`** olarak güncelle.

## Rapor almak

`docs/analytics/request.json` dosyasını değiştirip push etmek iş akışını tetikler:

```json
{"days": 90, "retention": 40, "note": "herhangi bir değişiklik tetikler"}
```

Rapor `docs/analytics/reports/<zaman>/` altına `report.json.enc` + `key.enc` olarak gelir.
