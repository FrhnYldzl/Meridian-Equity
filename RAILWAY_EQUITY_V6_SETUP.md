# Equity V6.0 Railway Setup Kılavuzu

Bu doküman **YENİ** Railway project (V6.0 equity dashboard) için adım adım rehber.
Mevcut **`devine-laughter`** (V5.7 production) ayarlarına **HİÇ DOKUNULMAZ**.

## 0. Strangler Fig Stratejisi

```
devine-laughter (V5.7)              meridian-equity-v6 (YENİ — V6.0)
├── Branch: main                    ├── Branch: claude/v5.8-abstract-bases
├── Build: Dockerfile               ├── Build: Dockerfile.equity
├── Config: railway.json            ├── Config: railway.equity.json
├── Entry: main:app                 ├── Entry: equity_preview_app:app
├── ENV: ALPACA_API_KEY (eski)      ├── ENV: aynı + V6.0 env'leri
└── URL: ??? (söyle, listeleyeyim)  └── URL: yeni domain
   ↓                                   ↓
Production canlı kalır              Yan yana V6.0 test ortamı
```

## 1. Railway Project Settings

### Source
- **Repository:** `FrhnYldzl/trading-agent`
- **Branch:** **`claude/v5.8-abstract-bases`** ← KRİTİK, `main` DEĞİL
- **Root Directory:** `/` (boş)

### Build (Settings → Build)
- **Builder:** `Dockerfile`
- **Dockerfile Path:** **`Dockerfile.equity`** ← KRİTİK
- (Build Command ve Start Command boş)

### Config-as-Code
- **Config Path:** `railway.equity.json`
  - (Crypto'da öğrendiğimiz lesson — Settings'teki Dockerfile path'i config dosyası ezer; yine de set ediyoruz ki ikisi de aynı şeyi söylesin.)

### Deploy → Watch Paths

Equity-only commit crypto'yu rebuild etmesin diye filtre:
```
Dockerfile.equity
railway.equity.json
requirements.txt
server/equity/**
server/core/**
server/equity_preview_app.py
server/static/equity/**
server/main.py
server/claude_brain.py
server/risk_manager.py
server/regime_detector.py
server/scheduler.py
server/gemini_auditor.py
server/news_sentiment.py
server/anomaly_detector.py
server/market_scanner.py
server/config.py
server/config.json
server/broker/**
```

> Not: V6.0 equity, V5.7'nin claude_brain.py / news_sentiment.py / anomaly_detector.py / risk_manager.py / config.py'sini import ediyor (yeni implementasyon yazmadık, mevcudu kullanıyoruz). Bu yüzden o dosyalar değişirse rebuild gerekiyor.

## 2. Volume

Settings → Volumes → **+ New Volume**
- **Name:** `equity-journal-data`
- **Mount path:** `/app/data`
- **Size:** 1GB

Bu V6.0 SQLite journal'ı (`/app/data/equity_journal.db`) Railway redeploy'larını survive eder.

## 3. Environment Variables

### Zorunlu (V5.7'den miras)
```
ALPACA_API_KEY=PK...                     # equity paper API key (mevcut equity ile aynı olabilir)
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
```

### V6.0 AI keys (sen oluşturursun)
```
# Anthropic için yeni "Meridian Equity Terminal" key oluştur, ya da
# mevcut "trade-agent-auto" key'i rename et:
ANTHROPIC_API_KEY=sk-ant-api03-...
# (kod auto-detect var, isim ne olursa olsun sk-ant- prefix'i bulur)

# Gemini için yeni key (ya da crypto'daki Gemini key'ini paylaş):
GEMINI_API_KEY=AIza...
# ya da
EQUITY_GEMINI_API_KEY=AIza...
```

### V6.0 Auto-Execute settings (başlangıçta GÜVENLI)
```
EQUITY_AUTO_EXECUTE=false              # KAPALI başla, manuel "Run Now" ile test
EQUITY_DRY_RUN=true                     # broker simulation (gerçek emir gitmez)
EQUITY_LIVE_MODE=false                  # paper account
EQUITY_LIVE_CONFIRMED=false             # extra confirmation
EQUITY_LIVE_PHASE=0                     # Phase 0 (paper only)
```

### Cost Optimization Paket A (default'lar zaten konservatif)
```
EQUITY_PREFILTER_ENABLED=true
EQUITY_PREFILTER_TOP_N=10
EQUITY_SKIP_FLAT=true
EQUITY_FLAT_THRESHOLD=0.5
EQUITY_REGIME_CACHE_MIN=30
EQUITY_AUDIT_SKIP_BELOW=5
EQUITY_AUDIT_SKIP_ABOVE=8
```

### Cross-module URLs
```
MERIDIAN_EQUITY_URL=https://meridian-equity-v6-production-XXX.up.railway.app
MERIDIAN_CRYPTO_URL=https://web-production-6c294.up.railway.app
MERIDIAN_OPTIONS_URL=
```

⚠ **DİKKAT:** V5.7 production'a **hiçbir env var ekleme**. Yeni V6.0 Railway project'inde bu env'ler set edilir, V5.7'de yok.

## 4. Deploy

Yukarıdaki ayarlar tamamlanınca → "Deploy Latest" tıkla.

### Beklenen build log
```
Initialization (✓)
Build (✓ ~2-3 dk, Docker image)
Deploy > Create container (✓ ~10sn)
Post-deploy (✓ uvicorn başlar)
[EquityAutoExec] startup: {'started': False, 'reason': 'EQUITY_AUTO_EXECUTE=false'}
INFO: Uvicorn running on http://0.0.0.0:8080
```

(Auto-execute=false olduğu için scheduler "started: False" — manuel Run Now ile test edilir.)

### Health check
```
GET /api/equity/health

Beklenen JSON:
{
  "status": "ok",
  "version": "6.0-β",
  "asset_class": "equity",
  "live_mode": false,
  "live_phase": 0,
  "phase_name": "Paper",
  "auditor_enabled": true,
  "journal_persistent": true,   ← Volume mount ile
  "auto_execute_enabled": false,
  "scheduler_running": false,
  "color": "#10b981"
}
```

Eğer `journal_persistent: false` → Volume mount edilmemiş. Settings → Volumes kontrol et.
Eğer `auditor_enabled: false` → GEMINI_API_KEY yok. Variables tab'ında ekle.

## 5. İlk Test

1. URL'e git: `https://meridian-equity-v6-production-XXX.up.railway.app/`
2. Şu an **basit fallback HTML** görmeli ("Backend ✅ — Dashboard V6.0-γ'da geliyor")
3. Endpoint testleri:
   - `/api/equity/health` → 200, JSON
   - `/api/equity/account` → Alpaca paper bakiye
   - `/api/equity/regime` → quant rejim sinyali
   - `/api/equity/brain` → 30-60sn, Claude reasoning
   - `/api/equity/scheduler-status` → gates + phase config

**Manuel pipeline trigger:**
```bash
curl -X POST https://.../api/equity/run-now
```
→ Pipeline çalışır, brain decisions + Gemini audit + gates + dry_run broker. Hiçbir gerçek emir gitmez.

## 6. V6.0-γ Dashboard Geldiğinde

Sonraki commit'te `server/static/equity/index.html` (green-themed Bloomberg dashboard) eklenecek. Watch Paths ve mevcut config tetiklenir, otomatik redeploy. Hard refresh ile görürsün.

## 7. Eski V5.7 Production (devine-laughter)

**HİÇBİR ŞEY YAPMA.** Aynı Branch (`main`), aynı Dockerfile, aynı env'ler. Bot tarama yapmaya, paper trade etmeye devam eder.

V6.0 paper'da en az 14 gün stabil çalıştıktan sonra:
1. V6.0 Phase 1'e geç (paper, V6.0 stabilize)
2. V6.0 Phase 2 (live ultra-conservative — gerçek $50 işlemler)
3. Aşamalı şekilde Phase 3, 4
4. V5.7 production durdurulur, V6.0 ana sistem olur

## 8. Troubleshooting

### "ModuleNotFoundError: equity_preview_app"
→ Branch yanlış. `claude/v5.8-abstract-bases` mı kontrol et.

### "Application failed to respond"
→ Build başarılı ama startup'ta hata. View Logs → traceback'e bak.
Genelde:
- ANTHROPIC_API_KEY missing
- ALPACA_API_KEY missing
- Volume permission

### `auditor_enabled: false` ama key var
→ Env var ismi `AIza` ile başlayan değer içermiyor. Variables tab'ı kontrol.

### Dashboard '/' HTML görünüyor ama endpoints 404
→ FastAPI routing problemi. crypto'da çalıştı, equity'de çalışmama nedeni: import error.
View Logs'ta startup sırasında ImportError var mı bak.
