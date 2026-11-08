# Studio V3 — konu + insan seçimi görseller + EMA seslendirme

Studio, eski otomatik hattın (M0–M39) yanına kurulmuş **yarı otomatik** bir üretim akışıdır.
Amaç tek: izleyiciyi tutan, kurgusu düzgün tarih Shorts'u. Eski hat silinmedi;
`python -m app telegram-poll` ile hâlâ çalışır (aynı bot token'ını aynı anda yalnızca biri dinleyebilir).

## Akış

```
(opsiyonel) kendi fotoğrafların ─► 📥 görsel havuzu (açıklama = fotoğrafta ne var)
      │
/yeni <konu>  ─► LLM metni + sahne/görsel listesi yazar (Groq → Gemini yedek)
      │           havuzdaki fotoğraflar g1..gN olur, hikâye onların etrafında kurulur
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
| Altyazı toplam süreye harf sayısıyla dağıtılıyor, İngilizce stopword vurgusu | Her satır ayrı seslendiriliyor (satır senkronu kesin). Kelime zamanları **EMA Lightning'in kendisinden** geliyor (sesi üreten kare planından, 40 ms hassasiyet) ve bilinen metne hizalanıyor (`app/studio/align.py`). EMA dışı bir yedek ses kullanılırsa **faster-whisper** gerçek sesten zaman çıkarıyor; o da yoksa hece ağırlığı. O anki kelime sarı |
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
| `STUDIO_GITHUB_REF` | `main` | Workflow'un çalışacağı branch |
| `STUDIO_TTS` | `ema,fish` | Sırayla denenecek TTS'ler: `ema`, `fish`, `piper` |
| `STUDIO_PIPER_MODEL_DIR` | | Piper (sherpa-onnx) model klasörü — son çare |
| `STUDIO_EMA_SPEED` | `1.0` | EMA konuşma hızı (0.25–4) |
| `STUDIO_EMA_SEED` | `0` | Aynı seed = yeniden render'da aynı ses; `-1` = her seferinde farklı |
| `STUDIO_EMA_DEVICE` | `auto` | `auto` · `cpu` · `cuda` |
| `STUDIO_LLM` | `groq,gemini` | Metin yazarı sırası |
| `STUDIO_GEMINI_MODEL` | `gemini-2.5-flash` | |
| `STUDIO_ALIGN_MODEL` | `base` | faster-whisper boyutu; sadece EMA dışı bir ses kullanılınca çalışır. Boş = kapalı, hece tahmini |
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

Render.com: `render.yaml` `python -m app studio-bot` çalıştırır ve
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
| `/yeni <konu>` | Yeni Short. Uzun metin de yapıştırılabilir: ilk satır konu, gerisi kaynak notu. Havuzda fotoğraf varsa metin onlarla kurulur |
| Fotoğraf (açık proje yokken) | 📥 Havuza girer; açıklamaya fotoğrafta ne olduğunu yaz ("Emu askerleri, 1932") |
| Albüm, açıklama `/yeni <konu>` | Fotoğraflar + konu tek seferde: albümün hepsi havuza girer ve metin hemen yazılır |
| Fotoğraf, açıklama `+ …` ya da `havuz …` | Açık proje varken bile fotoğrafı bir sonraki video için havuza koyar |
| `/havuz` · `/havuz temizle` | Havuzdaki fotoğrafları göster / boşalt |
| `/metin` · `/gorseller` · `/durum` | Metni, görsel durumunu, proje durumunu göster |
| `/render` · `/iptal` | |
| `5: yeni cümle` | 5. satırı değiştir (rakamları seslendirme için otomatik yazıya çevirir) |
| `5 -> 3` | 5. satır 3. görseli kullansın |
| `g3: açıklama` | 3. görselin açıklamasını/arama ipucunu değiştir |
| `düzelt: daha gerilimli yap` | Metni bütünüyle yeniden yazdır (gönderilen görseller korunur) |
| 🔁 Baştan yaz | Metni sıfırdan yazdır; senin fotoğrafların yine g1..gN olarak korunur |
| Fotoğraf | Sıradaki boş görsele; açıklamaya `3` yazarsan 3. görsele |

## Modüller

```
app/studio/
  models.py         Project / Line / Visual + JSON ProjectStore
  script_writer.py  kanal kurallı prompt, LLM JSON → Project
  llm.py            Groq + Gemini JSON istemcileri, yedekli
  tts.py            EMA Lightning (ses + kelime zamanları) / Fish Audio / Piper + satır satır ses izi
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

* EMA Lightning (`ema-lightning` 1.1.x, model: huggingface.co/canberkkkkkk/ema-lightning) süreç
  içinde çalışır; ağırlıklar (~34 MB) ilk kullanımda Hugging Face'ten iner ve Actions'ta
  `~/.cache/huggingface` altında önbelleğe alınır. Tek ses vardır (klonlama / duygu yok).
  Model yüklenemez ya da hata verirse zincirdeki sıradaki TTS (Fish → Piper) devreye girer ve
  önizleme mesajında hangi sesin kullanıldığı yazar. CPU'da yaklaşık 6× gerçek zamandan hızlıdır.
* Linux'ta PyPI'deki torch CUDA paketleriyle ~1.5 GB iner; CPU makinede önce
  `pip install torch --index-url https://download.pytorch.org/whl/cpu` kurun (workflow böyle yapar).
* faster-whisper modeli ilk çalıştırmada Hugging Face'ten indirilir (Actions'ta önbelleğe alınır);
  sandbox'ta model indirilemediği için hizalama sahte tanıyıcıyla test edildi. Model yoksa ya da hata
  verirse render durmaz, hece tahminine düşer; önizleme mesajında `🔤 whisper (%)` / `syllable` yazar.
* Eski hattaki `ProviderPerformanceLearning` sağlayıcı yönlendirmesinin (reliability) parçası olduğu
  için kapatılmadı; metrics/learning/recommendation servisleri zaten hiçbir giriş noktasından çağrılmıyor.
* YouTube API yorum sabitlemeye izin vermez; yorum eklenir, sabitlemeyi uygulamadan yap.
  Shorts için özel thumbnail API'de her hesapta kabul edilmeyebilir; uyarı olarak bildirilir.
* Her gizli yükleme YouTube kotasından ~1600 birim harcar (günlük 10.000).
