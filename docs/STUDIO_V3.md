# Studio V3 — konu + insan seçimi görseller + EMA seslendirme

Studio, eski otomatik hattın (M0–M39) yanına kurulmuş **yarı otomatik** bir üretim akışıdır.
Amaç tek: izleyiciyi tutan, kurgusu düzgün tarih Shorts'u. Eski hat silinmedi;
`python -m app telegram-poll` ile hâlâ çalışır (aynı bot token'ını aynı anda yalnızca biri dinleyebilir).

## Akış

```
/yeni <konu>  ─► LLM metni + sahne/görsel listesi yazar (Groq → Gemini yedek)
      │           düzenle: "5: yeni cümle" · "5 -> 3" · "g3: açıklama" · "düzelt: istek"
      ▼
✅ Metni onayla
      │
      ▼
Görseller: fotoğrafları sırayla gönder (ya da açıklamaya numara yaz: "3")
      │    eksikler için 🔎 → Wikimedia'dan 3 aday, dokunarak seç
      ▼
🎬 Render ─► local: bot alt süreç başlatır   |   github: workflow_dispatch (studio-render.yml)
      │       EMA Lightning (yedek: Fish Audio, Piper) → kurgu → müzik/efekt → mp4 + 2 thumbnail
      │       YouTube'a GİZLİ yükler (etiketler, thumbnail, açıklama + görsel kaynakları)
      ▼
Telegram'a önizleme + başlık/açıklama/etiket/yorum
      │
      ▼
🚀 Yayınla → herkese açık + yorum   ·   🔁 Yeniden render   ·   🗑 İptal (gizli videoyu siler)
```

## Neden böyle

| Eski hattaki sorun | Studio çözümü |
| --- | --- |
| `zoompan` tam piksele yuvarlıyor → titreme, 1080'e kırpılmış görsele zoom → bulanıklık | Her kare OpenCV `warpAffine` ile alt-piksel hassasiyetinde, orijinal çözünürlükten çiziliyor |
| Yatay arşiv fotoğrafları ortadan 9:16 kırpılıyor | Yatay görseller "kart" düzeninde (bulanık arka plan + çerçeve), dikeyler tam ekran; yüz tespiti ile odak |
| Altyazı toplam süreye harf sayısıyla dağıtılıyor, İngilizce stopword vurgusu | Her satır ayrı seslendiriliyor (satır senkronu kesin); kelime zamanları **faster-whisper** ile gerçek sesten alınıp bilinen metne hizalanıyor (`app/studio/align.py`), eşleşmeyen kelimeler hece ağırlığıyla dolduruluyor; o anki kelime sarı |
| M10–M13 optimizasyon/deney/karar katmanları video kalitesi oturmadan üretimi yönlendiriyor | `LEGACY_INTELLIGENCE_ENABLED=false` (varsayılan): eski hatta karar, konu seçimi, deney ve optimizasyon override'ları yok sayılıyor. Studio bu katmanları hiç kullanmıyor |
| Docker'da Arial yok | Poppins (OFL) repoda: `app/studio/assets/fonts` |
| Pexels modern stok, Wikimedia gürültülü, üstüne doğrulayıcı katmanları | Görseli insan verir; eksikler için aday gösterilir, insan seçer |
| Kurgu dili yok | Kesmede zoom-punch + flash + whoosh, sepia/altın/soğuk grade, grain, vinyet, üst bağlam etiketi, dev "kart" anı, loop'lu kapanış, prosedürel (telifsiz) müzik + otomatik ducking, -14 LUFS |

## Kurulum

### Ortam değişkenleri (mevcutlara ek)

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `STUDIO_RENDER_MODE` | `local` | `github`: render'ı GitHub Actions'ta yap (Render.com free/starter için önerilir) |
| `STUDIO_GITHUB_REPO` | | `emrtasknn/youtube-shorts-bot-v2` |
| `STUDIO_GITHUB_TOKEN` | | Fine-grained PAT, bu repoda **Actions: Read and write** |
| `STUDIO_GITHUB_REF` | `studio-v3` | Workflow'un çalışacağı branch (merge sonrası `main`) |
| `STUDIO_TTS` | `ema,fish` | Sırayla denenecek TTS'ler: `ema`, `fish`, `piper` |
| `STUDIO_PIPER_MODEL_DIR` | | Piper (sherpa-onnx) model klasörü — son çare |
| `STUDIO_LLM` | `groq,gemini` | Metin yazarı sırası |
| `STUDIO_GEMINI_MODEL` | `gemini-2.5-flash` | |
| `STUDIO_ALIGN_MODEL` | `base` | faster-whisper boyutu (kelime hizalama); boş = kapalı, sadece hece tahmini |
| `LEGACY_INTELLIGENCE_ENABLED` | `false` | Eski hattın M10–M13 override katmanlarını yeniden açar |
| `STUDIO_DIR` | `storage/studio` | Proje JSON'ları ve render çıktıları |

Mevcut `TELEGRAM_*`, `YOUTUBE_*`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `FISH_AUDIO_API_KEY` aynen kullanılır.
`TELEGRAM_ADMIN_USER_ID` doluysa bot sadece o kullanıcıya cevap verir.

### GitHub Actions (önerilen render yeri)

Repo → Settings → Secrets and variables → Actions:

* Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `YOUTUBE_CLIENT_ID`,
  `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `FISH_AUDIO_API_KEY` (yedek TTS)
* Variable (opsiyonel): `STUDIO_TTS` (örn. `ema,fish`)

Workflow: `.github/workflows/studio-render.yml`. Elle de tetiklenebilir; `project` girdisi
`app.studio.jobs.encode_payload(project)` çıktısıdır. Render sonrası mp4 3 gün artifact olarak saklanır.

### Bot

```bash
pip install -e ".[studio]"          # bot + render
pip install -e ".[studio,ema]"      # + EMA Lightning (torch CPU ile)
pip install -e ".[studio,ema,align]" # + faster-whisper kelime hizalama
python -m app studio-bot
```

Render.com: `render.yaml` bu branch'te `python -m app studio-bot` çalıştırır ve
`STUDIO_RENDER_MODE=github` kullanır. Proje dosyaları worker diskinde tutulur; yeniden
deploy olursa açık projeler kaybolur (yayınlanmış videolar etkilenmez).

### Komut satırı

```bash
python -m app studio-script "Emu Savaşı"                     # LLM metin testi
python -m app studio-render --project-file p.json --no-upload --no-notify --tts piper
```

## Telegram komutları

| Komut | |
| --- | --- |
| `/yeni <konu>` | Yeni Short. Uzun metin de yapıştırılabilir: ilk satır konu, gerisi kaynak notu |
| `/metin` · `/gorseller` · `/durum` | Metni, görsel durumunu, proje durumunu göster |
| `/render` · `/iptal` | |
| `5: yeni cümle` | 5. satırı değiştir (rakamları seslendirme için otomatik yazıya çevirir) |
| `5 -> 3` | 5. satır 3. görseli kullansın |
| `g3: açıklama` | 3. görselin açıklamasını/arama ipucunu değiştir |
| `düzelt: daha gerilimli yap` | Metni bütünüyle yeniden yazdır (gönderilen görseller korunur) |
| Fotoğraf | Sıradaki boş görsele; açıklamaya `3` yazarsan 3. görsele |

## Modüller

```
app/studio/
  models.py         Project / Line / Visual + JSON ProjectStore
  script_writer.py  kanal kurallı prompt, LLM JSON → Project
  llm.py            Groq + Gemini JSON istemcileri, yedekli
  tts.py            EMA Lightning / Fish Audio / Piper + satır satır ses izi
  align.py          faster-whisper kelime zaman damgaları → bilinen metne bulanık hizalama
  text.py           Türkçe sayı okuma, büyük harf, hece ağırlığı, altyazı parçalama
  visual_search.py  Wikimedia Commons aday araması
  render/planner.py satır zamanlaması → planlar (kamera hareketleri, kart anları)
  render/engine.py  kare çizici + plan başına ffmpeg
  render/audio.py   prosedürel müzik, efektler, ducking'li miks
  render/thumbnail.py dikey + yatay kapak
  render/pipeline.py uçtan uca render
  jobs.py           render + gizli yükleme + Telegram önizleme (local ve Actions ortak)
  publisher.py      YouTube: gizli yükle, etiket/thumbnail, yayınla, sil
  bot.py            Telegram akışı
```

## Bilinen sınırlar

* EMA Lightning bu branch hazırlanırken sandbox'ta kurulamadığı için **gerçek ortamda ilk
  çalıştırmada doğrulanmalı**; hata verirse zincirdeki sıradaki TTS (Fish → Piper) devreye girer
  ve önizleme mesajında hangi sesin kullanıldığı yazar.
* faster-whisper modeli ilk çalıştırmada Hugging Face'ten indirilir (Actions'ta önbelleğe alınır);
  sandbox'ta model indirilemediği için hizalama sahte tanıyıcıyla test edildi. Model yoksa ya da hata
  verirse render durmaz, hece tahminine düşer; önizleme mesajında `🔤 whisper (%)` / `syllable` yazar.
* Eski hattaki `ProviderPerformanceLearning` sağlayıcı yönlendirmesinin (reliability) parçası olduğu
  için kapatılmadı; metrics/learning/recommendation servisleri zaten hiçbir giriş noktasından çağrılmıyor.
* YouTube API yorum sabitlemeye izin vermez; yorum eklenir, sabitlemeyi uygulamadan yap.
  Shorts için özel thumbnail API'de her hesapta kabul edilmeyebilir; uyarı olarak bildirilir.
* Her gizli yükleme YouTube kotasından ~1600 birim harcar (günlük 10.000).
