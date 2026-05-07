# 🪙 CRYPTO HANDOFF — Meridian Capital Crypto Module

> **Bu nedir?** `trading-agent` repo'su artık equity-pure (V6.0-ε). Crypto modülünü ayrı bir Claude Code session'ında **sıfır bağlam kaybıyla** devam ettirmek için tasarlanmış kapsamlı transfer dokümanı.
>
> **Kullanım:** Yeni Claude Code session aç → "5. NEW SESSION PROMPT" bölümündeki **prompt'u olduğu gibi yapıştır** → Claude bu doküman üzerinden çalışmaya başlar.

---

## 1. ⚡ TL;DR — 30 saniye

| Soru | Cevap |
|---|---|
| Şu an equity nerede? | `main` branch'te V6.0-ε, Railway `trading-agent-production-51c6` |
| V5.7 production yedeği? | Tag `v5.7-final-archive` (Railway `devine-laughter` base) |
| Crypto V5.10 production? | Hâlâ devine-laughter'da koşuyor (multi-asset legacy) |
| Crypto V5.10 source code? | `claude/v5.8-abstract-bases` branch (this repo, hiç dokunulmadı) |
| Crypto V6.0 nereden başlanacak? | Equity V6.0-α..ε pattern'ini template olarak kullan |
| Hedef | Crypto V6.0-ε (Pro Full + 10 panel + prompt caching + Sonnet 4.5) |
| İdeal son durum | `trading-agent-crypto-v6/` ayrı repo, devine-laughter oraya bağlı |

---

## 2. 🗺 Repo Haritası

### Bu repo (`trading-agent`) — equity'ye adanmış
```
main / equity/v6.0  ──► V6.0-ε equity-only
                       ├─ server/equity/        (V6.0 full impl)
                       ├─ server/equity_preview_app.py
                       ├─ server/static/equity/index.html (green theme)
                       └─ Railway: trading-agent-production-51c6
                       
v5.7-final-archive  ──► V5.7 production snapshot (TAG, branch değil)
                       └─ Railway: devine-laughter (eğer korunacaksa)
                       
claude/v5.8-abstract-bases ──► CRYPTO V5.10 KAYNAK KOD
                       ├─ Tüm crypto modülleri (V5.7 + V5.10 hotfix'leri)
                       ├─ V5.8 abstract base'leri (core/)
                       └─ Mixed crypto+equity (eski multi-asset durumu)
```

### Önemli commit referansları
| Commit | Branch | Anlamı |
|---|---|---|
| `f3b73e9` | claude/v5.8-abstract-bases | **Crypto V5.10 son durumu** (V6.0-β.3 hotfix dahil) |
| `0c6af16` | claude/v5.8-abstract-bases | V5.10 final: Real Alpaca orders + close lifecycle |
| `7e78a6f` | claude/v5.8-abstract-bases | V5.10-δ: Gemini Auditor council mode |
| `39beb63` | claude/v5.8-abstract-bases | V5.10-ε: Trade Journal SQLite |
| `cde205d` | claude/v5.8-abstract-bases | V5.10-ε.1: Persistent journal (Railway Volume) |
| `3134996` | main | **Equity-only ayrıştırma** noktası (referans için) |
| `cca00b2` | main | EquityBrain — prompt caching pattern |
| `cc47b26` | main | 10 Pro panels (template olarak kopyala) |

---

## 3. 📋 Crypto V5.10 Inventory

### 3.1 Çekirdek modüller (`server/`)
| Dosya | Satır | Görev |
|---|---|---|
| `main.py` (V5.7 orijinal) | ~600 | FastAPI app, multi-asset endpoints |
| `claude_brain.py` | ~700 | Claude AI multi-step reasoning (BTC odaklı) |
| `regime_detector.py` | ~250 | 4-component quant regime (BTC dominance + ETH ratio + macro) |
| `risk_manager.py` | ~400 | ATR stop, sektör cap %30, flash crash detector |
| `scheduler.py` | ~150 | Adaptive scan (active 5dk / quiet 15dk) |
| `market_scanner.py` | ~500 | Core 15 + Extended evren, OHLCV + indicators |
| `news_sentiment.py` | ~300 | CryptoCompare news + sentiment scoring |
| `anomaly_detector.py` | ~200 | Flash crash + suspicious volume spikes |
| `gemini_auditor.py` | ~250 | Gemini Flash-Lite second opinion (tiered) |
| `trade_journal.py` / `_v2.py` | ~400 | SQLite seyir defteri |
| `broker/crypto.py` | ~350 | **Alpaca crypto + manual bracket threading** |
| `broker/equity.py` | ~350 | Equity broker (artık equity-v6'da kullanılıyor) |

### 3.2 V5.8 abstract base'leri (`server/core/`)
```python
core/
├── asset_class.py      # AssetClass.CRYPTO / EQUITY enum
├── base_brain.py       # BaseBrain ABC (run_brain, review_past_trades)
├── base_broker.py      # BaseBroker ABC (place_order, get_positions, ...)
├── base_regime.py      # BaseRegime ABC (detect, asset_class)
├── base_risk.py        # BaseRisk ABC (dynamic_position_size, ...)
└── base_scheduler.py   # BaseScheduler ABC (detect_scan_mode, ...)
```
Bu dosyalar zaten her iki branch'te de var, yeniden yazma gerekmez.

### 3.3 V5.10 changelog (claude/v5.8-abstract-bases üzerinde)
| Versiyon | Eklenen şey |
|---|---|
| V5.10 final | Real Alpaca orders + bracket threading + close lifecycle |
| V5.10.1 | Order status whitelist (max positions gate fix) |
| V5.10.2 | Asset group lookup (slash/no-slash compat) + HTML cache busting |
| V5.10.3 ⚠ | renderBrain async fix — blank dashboard CRITICAL hotfix |
| V5.10.4 | Hero "Open Positions" sayacı |
| V5.10-δ | Gemini Auditor council mode (her brain → Gemini ikinci görüş) |
| V5.10-ε | Trade Journal SQLite (sektör/asset_group + endpoints) |
| V5.10-ε.1 | Persistent journal — Railway Volume `/app/data/` |
| V5.10-η.2 | Brain API key diagnostic + `/api/env-debug` endpoint |
| V5.10-η.3 | Gate intra-run counting + brain lazy api key resolution |

### 3.4 Crypto-specific eşsiz nüanslar
- **24/7 piyasa**: scheduler hiç durmaz (active/quiet adaptive)
- **PDT yok**: pattern day trade kuralı geçerli değil
- **Bracket orders manual**: Alpaca crypto'da native değil, threading ile yapıyoruz
- **Sektör cap %30**: equity'ye benzer ama asset_group enum farklı (DeFi/L1/Meme/Stable/Exchange)
- **Flash crash threshold**: 5dk'da %5+ düşüş → emergency_halt
- **Dashboard theme**: Orange `#f7931a` (Bitcoin), logo `₿`

### 3.5 Crypto universe (Core 15)
```python
WATCHLIST = ["BTC/USD", "ETH/USD", "SOL/USD", "MATIC/USD", "AVAX/USD",
             "LINK/USD", "DOT/USD", "ADA/USD", "ATOM/USD", "UNI/USD",
             "AAVE/USD", "DOGE/USD", "SHIB/USD", "LTC/USD", "BCH/USD"]
# Extended: BNB, XRP, TRX, NEAR, FTM, ARB, OP, INJ, RUNE, TIA, vs.
```

---

## 4. 🏗 Equity V6.0 Pattern — Crypto için Template

Equity için V6.0-α'dan ε'ya kadar yapılanların **birebir kopyalanabilir** karşılıkları:

### 4.1 Dizin yapısı (yeni crypto repo'sunda)
```
trading-agent-crypto-v6/
├── Dockerfile                          # Equity ile aynı, CMD: uvicorn main:app
├── railway.json                        # Equity ile aynı
├── requirements.txt                    # Aynı + ek crypto SDK gerekirse
├── .env.example                        
├── server/
│   ├── main.py                         # Shim: LEGACY → archive, default → crypto_preview_app
│   ├── main_v510_archive.py           # V5.10 main.py orijinal (LEGACY_V510_MODE için)
│   ├── crypto_preview_app.py          # Yeni FastAPI app (equity_preview_app klonu)
│   ├── core/                           # Aynı abstract base'ler
│   ├── crypto/
│   │   ├── __init__.py                 # Tüm exports
│   │   ├── journal.py                  # equity/journal.py klonu, asset_class='crypto'
│   │   ├── audit_impl.py               # equity/audit_impl.py klonu, crypto checklist
│   │   ├── auto_executor.py            # equity/auto_executor.py klonu, PDT yok, 24/7
│   │   ├── brain_impl.py               # equity/brain_impl.py klonu, CRYPTO_SYSTEM_PROMPT
│   │   └── pro_panels.py               # equity/pro_panels.py klonu, crypto adaptasyonları
│   ├── broker/
│   │   ├── __init__.py
│   │   └── crypto.py                   # claude/v5.8 branch'inden al
│   ├── claude_brain.py                 # V5.10 legacy fallback
│   ├── regime_detector.py              
│   ├── risk_manager.py                 
│   ├── scheduler.py                    
│   ├── market_scanner.py               # WATCHLIST = crypto core 15
│   ├── news_sentiment.py               
│   ├── anomaly_detector.py             
│   ├── gemini_auditor.py               
│   ├── trade_journal.py / _v2.py       # legacy, V6.0 journal aktif
│   ├── config.py
│   └── static/
│       └── crypto/
│           └── index.html              # static/equity/index.html klonu, orange theme
└── CRYPTO_HANDOFF_HISTORY.md          # bu dosya, "tamamlandı" işaretli
```

### 4.2 `crypto_preview_app.py` skeleton (equity_preview_app.py'tan)
```python
"""
crypto_preview_app.py — V6.0 Standalone FastAPI for Meridian Crypto.
"""
import os, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv("../.env")

# V5.10 modülleri (DOKUNULMAZ)
from broker.crypto import CryptoBroker
from claude_brain import run_brain as legacy_run_brain
from regime_detector import detect_regime as legacy_detect_regime
from risk_manager import RiskManager
from market_scanner import get_market_data, WATCHLIST
from news_sentiment import get_market_sentiment, get_ticker_sentiment
from anomaly_detector import detect_anomalies as legacy_detect_anomalies
from gemini_auditor import (
    audit_decisions as legacy_audit_decisions,
    get_last_audit, is_enabled as gemini_enabled,
)
import scheduler as legacy_sched
from config import ASSET_GROUP_MAP  # crypto'da bu kullanılıyor (sector yerine)

# V6.0 yeni modüller
from crypto import (
    CryptoJournal,
    CryptoAuditor,
    CryptoAutoExecutor,
    CryptoBrain,
    PHASE_PROFILES,
    pro_panels,
)

app = FastAPI(title="Meridian Capital — Crypto V6.0", version="6.0-ε")

_broker = CryptoBroker()  # paper hardcoded
_journal = CryptoJournal()
_auditor = CryptoAuditor()
_brain = CryptoBrain()

# ... (equity_preview_app.py'taki tüm endpoint'leri /api/crypto/* prefix'iyle kopyala)
# ... (Pro panels endpoint'lerini /api/crypto/pro/* prefix'iyle ekle)
```

### 4.3 `crypto/brain_impl.py` skeleton (equity'den)

Equity'deki `EQUITY_SYSTEM_PROMPT`'u crypto için değiştir:

```python
"""crypto/brain_impl.py — V6.0-δ: Cost-optimized Claude AI brain."""

CRYPTO_SYSTEM_PROMPT = """You are the Chief Trading Officer of an autonomous AI hedge fund 
managing a US crypto (Alpaca crypto) portfolio. 24/7 markets — no PDT, no overnight risk.

## STRATEGY FRAMEWORK

### Strategy Selection (regime-based, BTC-driven):
- **BULL** (BTC uptrend + altseason): MOMENTUM (gap & go on alts)
- **NEUTRAL**: SELECTIVE (only top momentum_score, %50 size)  
- **BEAR**: DEFENSIVE (BTC/ETH only, hold >60% USDC)

### Crypto-specific Multi-step:
1. BTC trend? (dominance, BTC/USD price action)
2. Asset group? (DeFi/L1/Meme — meme'da volatility extra cap)
3. Funding rate? (overheated longs = avoid)
4. Volume confirmation (binance vs coinbase ref)
5. Catalyst? (token unlock, governance vote, listing)

## RISK RULES (ABSOLUTE)
1. NEVER >2% per trade
2. NO overnight crypto exposure on bear regime weekend
3. Max 30% per asset_group (DeFi 30%, L1 30%, Meme 15% sub-cap)
4. Flash crash detection — 5dk %5+ → halt
5. Stables (USDC/USDT) için pozisyon açma

## RESPONSE FORMAT (JSON only)
{
  "regime": "bull|bear|neutral",
  "active_strategy": "momentum|selective|defensive",
  "decisions": [
    {"ticker":"BTC/USD", "action":"long|short|close|hold", "confidence":1-10,
     "asset_group":"L1|DeFi|Meme|Stable|Exchange",
     "reasoning":"...", "entry_zone":"...", "stop_loss":"...", "take_profit":"...",
     "position_size_pct":2.0, "urgency":"high|med|low"}
  ],
  "market_summary":"...", "portfolio_note":"...", "watchlist_alerts":[]
}
"""

class CryptoBrain(BaseBrain):
    DEFAULT_MODEL = os.getenv("CRYPTO_BRAIN_MODEL", "claude-sonnet-4-5-20250929")
    
    def __init__(self, model=None):
        # API key resolution: CRYPTO_ANTHROPIC_API_KEY → ANTHROPIC_API_KEY → sk-ant- scan
        ...
    
    @property
    def asset_class(self): return AssetClass.CRYPTO
    
    def run_brain(self, market_data, portfolio, recent_trades=None,
                  regime=None, sentiment=None, learning_context=None,
                  auto_execute=False):
        # User message dynamic, system message cacheable
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=[{"type":"text","text":CRYPTO_SYSTEM_PROMPT,"cache_control":{"type":"ephemeral"}}],
            messages=[{"role":"user","content": user_message}],
        )
        # ... (equity_preview_app'taki run_brain ile aynı pattern)
```

### 4.4 `crypto/pro_panels.py` adaptasyonları

| # | Equity panel | Crypto karşılığı | Değişiklik |
|---|---|---|---|
| 1 | Sector Heatmap | **Asset-Group Heatmap** | `sector_map` → `asset_group_map` (DeFi/L1/Meme/Stable) |
| 2 | Earnings Calendar | **Token Unlock Calendar** | News heuristic veya CryptoRank API |
| 3 | MTF Analysis | MTF aynen (24/7'de bile geçerli) | Endpoint paramı `?symbol=BTC/USD` |
| 4 | Correlation Matrix | **BTC-Beta Matrix** | Her coin'in BTC ile korelasyonu (anchor) |
| 5 | Win Rate Trend | Aynen | Asset_group breakdown ek olarak |
| 6 | Risk Dashboard | Aynen | sector → asset_group |
| 7 | Gap Scanner | **Funding Rate / Open Interest** | Futures kullanılırsa |
| 8 | News Timeline | Aynen | CryptoCompare endpoint |
| 9 | AI Confidence Stats | Aynen (template kopyala) | Hiçbir değişiklik gerekmiyor |
| 10 | Trade Replay | Aynen | Hiçbir değişiklik gerekmiyor |

**Pure Python kalsın** — equity bunu kanıtladı. numpy/pandas/yfinance gerek yok.

### 4.5 Dashboard adaptasyonu
`server/static/crypto/index.html` (`server/static/equity/index.html`'dan klonla):

```bash
# Bir kerede sed ile renk + endpoint + brand değiştir
sed -e 's|--equity:|--crypto:|g' \
    -e 's|#10b981|#f7931a|g' \
    -e 's|#34d399|#fb923c|g' \
    -e 's|/api/equity/|/api/crypto/|g' \
    -e 's|MERIDIAN CAPITAL — EQUITY|MERIDIAN CAPITAL — CRYPTO|g' \
    -e 's|>SPY<|>BTC<|g' \
    -e 's|Equity Module|Crypto Module|g' \
    server/static/equity/index.html > server/static/crypto/index.html
```

Ek değişiklikler (manuel):
- Logo `M` → `₿`
- Footer "Pro Full · 10 Bloomberg-grade panels"
- Sembol input default: `NVDA` → `BTC/USD`

---

## 5. 🚀 NEW SESSION PROMPT — Olduğu gibi yapıştır

```
Meridian Capital — Crypto V6.0 başlatıyoruz. Hedef: V6.0-ε crypto-only deploy.

REPO: github.com/FrhnYldzl/trading-agent
KAYNAK BRANCH: claude/v5.8-abstract-bases (V5.10 production code burada)
HEDEF: trading-agent-crypto-v6 ayrı repo (veya bu repo'da crypto/v6.0 branch)

İLK İŞ: CRYPTO_HANDOFF.md'yi oku (main branch'teki). Bölüm 4 ve 6'da:
  - Equity V6.0 pattern'i (template)
  - 5-step resumption planı (copy-paste komutlar)

SONRA SIRAYLA YAP:
  α) crypto/journal + audit_impl + auto_executor (equity klonu, asset_class='crypto', PDT YOK)
  β) crypto_preview_app.py (FastAPI, /api/crypto/* endpoints)
  γ) static/crypto/index.html (equity orange theme'a sed ile)
  δ) crypto/brain_impl.py (CRYPTO_SYSTEM_PROMPT + Sonnet 4.5 + prompt caching)
  ε) crypto/pro_panels.py (10 panel, crypto adaptasyonları — bölüm 4.4'teki tablo)

DEĞİŞMEYECEKLER:
  - Sonnet 4.5 default
  - Anthropic prompt caching (ephemeral, 5dk TTL)
  - Pure Python (numpy/pandas/yfinance YOK)
  - Bracket orders manual (Alpaca crypto'da native değil)
  - Volume mount /app/data (journal persistence)

KRİTİK NÜANSLAR (CRYPTO):
  - 24/7 piyasa (scheduler hiç durmaz)
  - PDT YOK (auto_executor gate'inde kaldır)
  - Sektör → asset_group (DeFi/L1/Meme/Stable/Exchange)
  - Meme tokens için sub-cap %15
  - Flash crash 5dk %5+ → halt

DEPLOYMENT:
  - Railway: yeni servis VEYA devine-laughter'ı yönlendir
  - Branch: crypto/v6.0
  - Env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, ANTHROPIC_API_KEY
  - LEGACY_V510_MODE=false (V6.0 default)

DOĞRULAMA:
  GET /api/crypto/health         → version: "6.0-ε"
  GET /api/crypto/brain          → Sonnet 4.5 + caching
  GET /api/crypto/brain-usage    → cache hit ratio + USD savings
  GET /api/crypto/pro/index      → 10 panel kataloğu
  GET /                          → orange dashboard

V5.10 production (devine-laughter) HÂLÂ DOKUNMA. 
Tag v5.7-final-archive ve claude/v5.8-abstract-bases korunsun.

Başla.
```

---

## 6. ⚙️ Resumption — Adım Adım Komutlar

### Adım 1: Crypto repo'sunu hazırla
```bash
# Seçenek A: Aynı repo'da crypto/v6.0 branch
git clone https://github.com/FrhnYldzl/trading-agent.git
cd trading-agent
git checkout -b crypto/v6.0 claude/v5.8-abstract-bases

# Seçenek B: Tamamen ayrı repo (ÖNERİLEN)
git clone https://github.com/FrhnYldzl/trading-agent.git ../trading-agent-crypto-v6
cd ../trading-agent-crypto-v6
git checkout claude/v5.8-abstract-bases
git checkout -b main  # ya da crypto/v6.0
# Yeni GitHub repo oluştur, push:
gh repo create trading-agent-crypto --public --source=. --push
```

### Adım 2: Equity referans dosyalarını çek (template olarak)

Equity main branch'inden şu dosyaları indir, crypto adaptasyonlarını yap:

```bash
# Equity'den çek
git fetch origin main
git show origin/main:server/equity/__init__.py > /tmp/equity_init.py
git show origin/main:server/equity/journal.py > /tmp/equity_journal.py
git show origin/main:server/equity/audit_impl.py > /tmp/equity_audit.py
git show origin/main:server/equity/auto_executor.py > /tmp/equity_executor.py
git show origin/main:server/equity/brain_impl.py > /tmp/equity_brain.py
git show origin/main:server/equity/pro_panels.py > /tmp/equity_panels.py
git show origin/main:server/equity_preview_app.py > /tmp/equity_app.py
git show origin/main:server/static/equity/index.html > /tmp/equity_dashboard.html

# Crypto'ya kopyala + dönüştür
mkdir -p server/crypto server/static/crypto

sed 's/equity/crypto/g; s/EquityBrain/CryptoBrain/g; s/EquityJournal/CryptoJournal/g; s/EquityAuditor/CryptoAuditor/g; s/EquityAutoExecutor/CryptoAutoExecutor/g' \
    /tmp/equity_brain.py > server/crypto/brain_impl.py
# ... (her dosya için benzer sed)
```

### Adım 3: CRYPTO_SYSTEM_PROMPT'u yaz
`server/crypto/brain_impl.py` içinde bölüm 4.3'teki prompt'u kullan.

### Adım 4: Auto-executor'da PDT'yi kaldır
`server/crypto/auto_executor.py`'da:
- `PDT_DAY_TRADES_REMAINING` gate'ini sil
- 24/7 active session: `is_active_session() return True` (her zaman)
- `MAX_SECTOR_PCT` → `MAX_ASSET_GROUP_PCT`

### Adım 5: Railway deploy
```bash
git add -A
git commit -m "Crypto V6.0-α: Foundation from equity template"
git push origin main

# Railway dashboard:
# 1. New project → "Deploy from GitHub" → trading-agent-crypto
# 2. Branch: main
# 3. Variables:
#    ALPACA_API_KEY=<paper key>
#    ALPACA_SECRET_KEY=<paper secret>
#    ALPACA_BASE_URL=https://paper-api.alpaca.markets
#    ANTHROPIC_API_KEY=<sk-ant-...>
# 4. Volumes → mount: /app/data (journal persistence)
```

### Adım 6: Doğrula
```bash
curl https://YOUR-CRYPTO-RAILWAY.up.railway.app/api/crypto/health
# → {"status":"ok","version":"6.0-ε","asset_class":"crypto",...}

curl https://YOUR-CRYPTO-RAILWAY.up.railway.app/api/crypto/pro/index
# → 10 panel kataloğu

# Dashboard
open https://YOUR-CRYPTO-RAILWAY.up.railway.app/#/pro
```

---

## 7. 💰 Cost Optimization Math (gerçek sayılar)

Equity V6.0-δ'da kanıtlanan tasarruflar (Sonnet 4.5 + prompt caching):

### Senaryo: 1 saat boyunca 5 dakikada bir brain call (12 call/saat)
| Konfig | İlk call | Sonraki 11 call | Toplam | Aylık (24/7) |
|---|---|---|---|---|
| **V5.7 (Opus, no cache)** | $0.050 | $0.050 × 11 | $0.60 | $432 |
| **V6.0-δ (Sonnet 4.5 + caching)** | $0.020 | $0.005 × 11 | $0.075 | $54 |
| **Tasarruf** | -60% | -90% | **-87.5%** | **$378/ay** |

### Crypto için aynı tasarrufu garantilemek
1. `CryptoBrain.__init__` → model default `claude-sonnet-4-5-20250929`
2. `run_brain` → system prompt'u `cache_control: {"type":"ephemeral"}` ile gönder
3. Static prompt **bütünüyle** sistem mesajında olsun (risk rules + framework + format spec)
4. Dynamic data (market_data, portfolio) sadece user mesajında, fresh
5. `/api/crypto/brain-usage` endpoint'iyle cache hit ratio'yu izle

---

## 8. 🔧 Troubleshooting

### Yaygın sorunlar (equity sürecinden öğrenilenler)

#### Problem 1: Railway "cd executable not found"
**Neden:** Procfile auto-detect, `cd server && uvicorn` çalıştırmaya çalışıyor.
**Çözüm:** Procfile'ı sil, sadece Dockerfile + railway.json kalsın.

#### Problem 2: Brain enabled=false (API key bulamıyor)
**Neden:** Env var ismi farklı (örn. `CRYPTO_ANTHROPIC_API_KEY` aranıyor ama `ANTHROPIC_API_KEY` set).
**Çözüm:** `_resolve_api_key` chain: `CRYPTO_ANTHROPIC_API_KEY → ANTHROPIC_API_KEY → sk-ant- prefix scan`.

#### Problem 3: "max positions gate" tetiklenmiyor
**Neden:** Alpaca crypto status değerleri `"new"`, `"accepted"` (Alpaca equity'de farklı).
**Çözüm:** Whitelist yerine **rejected statuses negative whitelist**:
```python
if status not in ("rejected", "canceled", "expired", "filled"):
    pending_executions.append(...)
```

#### Problem 4: Asset group "Unknown"
**Neden:** Alpaca crypto symbols slash-less olarak dönüyor (`BTCUSD`), map slash-form'da (`BTC/USD`).
**Çözüm:** `get_asset_group(symbol)` her iki form'u da dene.

#### Problem 5: renderBrain blank dashboard
**Neden:** Async/await syntax non-async function'da.
**Çözüm:** `async function renderBrain(r)` — async olarak işaretle.

### Lessons learned (equity'den)
1. **Branch isolation kritik** — V5.7 prod ASLA bozulmasın
2. **Smoke test her commit öncesi** — `python -c "import equity_preview_app"` (mock env'lerle)
3. **Endpoint catalog güncel tut** — equity_preview_app'ın docstring'i 27 endpoint listeliyor
4. **Cache TTL'leri farklı tut** — health 30s, brain 60s, news 600s, earnings 900s
5. **Pure Python performance OK** — Pearson korelasyonu pandas olmadan da hızlı

---

## 9. ✅ Verification Checklist

Crypto V6.0-ε bittiğinde aşağıdaki listeyi tek tek check'le:

### Backend
- [ ] `from crypto import CryptoBrain, CryptoJournal, CryptoAuditor, CryptoAutoExecutor` import ediyor
- [ ] `from crypto import pro_panels` 10 fonksiyon içeriyor
- [ ] `CryptoBrain.run_brain` döndüğünde `_usage` dict'inde `cache_creation_input_tokens` ve `cache_read_input_tokens` var
- [ ] Auto-executor PDT gate'i içermiyor
- [ ] Auto-executor `is_active_session() == True` (24/7)

### Endpoints
- [ ] `GET /api/crypto/health` → `version: "6.0-ε"`, `asset_class: "crypto"`
- [ ] `GET /api/crypto/brain` → JSON, `_usage` dolu
- [ ] `GET /api/crypto/brain-usage` → cache hit % > 0 (ikinci çağrıdan sonra)
- [ ] `GET /api/crypto/pro/index` → 10 panel listeli
- [ ] `GET /api/crypto/pro/sector-heatmap` (asset-group heatmap olarak çalışıyor)
- [ ] `GET /api/crypto/pro/correlation-matrix` → matrix dolu
- [ ] `GET /api/crypto/pro/risk-dashboard` → asset_group concentration alarms
- [ ] `GET /api/crypto/journal` → SQLite çalışıyor
- [ ] `GET /api/crypto/journal/performance` → asset_group breakdown var

### Dashboard
- [ ] `/` → orange theme (#f7931a)
- [ ] Brand: "MERIDIAN CAPITAL — CRYPTO TERMINAL"
- [ ] Logo: ₿
- [ ] `/#/pro` → 10 panel görünür yükleniyor
- [ ] Sembol input default: `BTC/USD`
- [ ] Footer: "Meridian Crypto V6.0-ε · Pro Full · 10 Bloomberg-grade panels"

### Production (Railway)
- [ ] Servis branch: crypto/v6.0 (veya main)
- [ ] Auto-deploy: ON
- [ ] Volume mount: `/app/data` (journal persistence)
- [ ] Env vars set: ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, ANTHROPIC_API_KEY
- [ ] Build successful
- [ ] /health endpoint 200 OK
- [ ] V5.10 production (devine-laughter) hâlâ V5.10 (BOZULMADI)

---

## 10. 📞 Reference & Support

### Equity Production (referans gözlemi için)
- URL: https://trading-agent-production-51c6.up.railway.app
- Endpoints: `/api/equity/health`, `/api/equity/pro/index`, `/api/equity/brain-usage`
- Code: github.com/FrhnYldzl/trading-agent (main branch, V6.0-ε)
- Çalışıyorsa crypto da aynı pattern'i kullanabilir.

### Tag arşivleri (geri dönüş için)
- `v5.7-final-archive` — V5.7 production snapshot

### Branch arşivleri
- `claude/v5.8-abstract-bases` — V5.10 crypto + V5.8 abstracts (mixed)
- `claude/happy-bell` — eski V5.x deneyleri
- `claude/vibrant-bhaskara` — eski V5.x deneyleri

### Sorular için
1. Bu dokümanı + `git log --oneline claude/v5.8-abstract-bases` üzerinden çalış
2. Equity commit message'ları çok detaylı — özellikle:
   - `3134996` — equity ayrıştırma stratejisi
   - `cca00b2` — prompt caching nasıl uygulandı
   - `cc47b26` — 10 Pro panel mimarisi
3. Equity preview app'ın docstring'i (`equity_preview_app.py` üst kısmı) tüm endpoint kataloğunu içeriyor

---

## 🏁 Bitti İşareti

Crypto V6.0-ε bitince bu dokümanın en altına şunu ekle:

```markdown
## ✅ COMPLETED — YYYY-MM-DD
- Repo: trading-agent-crypto-v6 (veya crypto/v6.0 branch)
- Production URL: https://...
- Last commit: <hash>
- Cost savings achieved: %XX (V5.10 → V6.0-δ baseline)
- Pro panels live: 10/10
- V5.10 production unaffected: ✓
```

Sonra bu dokümanı `CRYPTO_HANDOFF_HISTORY.md` olarak rename et — gelecek nesil reference olarak kalsın.

---

*Doküman versiyonu: 2.0 (kusursuz)*
*Son güncelleme: 2026-05-07*
*Equity son commit: 7957e82 (CRYPTO_HANDOFF.md ekleme)*
*Crypto base commit: f3b73e9 (claude/v5.8-abstract-bases)*
*V5.7 archive tag: v5.7-final-archive*

🚀 İyi şanslar — crypto V6.0-ε'yu bitirdiğinde tekrar buluşalım.
