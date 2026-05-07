# CRYPTO HANDOFF — Meridian Capital Crypto Module

> **Bu dosyanın amacı:** `trading-agent-equity-v6` repo'su artık SADECE equity'ye odaklanıyor. Crypto modülünü ayrı bir Claude Code session'ında kaldığı yerden devam ettirmek için ihtiyacın olan TÜM bilgi burada.
>
> **Hedef kullanım:** Yeni session aç → bu dokümanı yapıştır → Claude bu dokümanla başlasın.

---

## 1. ÖZET — Şu an nerede kaldık?

### Crypto'nun son sağlam noktası
- **V5.10 final** + V5.10-η.3 hotfix'leri
- Branch: `claude/v5.8-abstract-bases` (origin'de var)
- Commit: `f3b73e9` (V6.0-β.3 nuclear fix dahil)
- Production: Railway "**devine-laughter**" servisi (ayrı project)
- URL pattern: `web-production-bdc50.up.railway.app` (kontrol et, değişebilir)

### Equity tarafı (bu repo'da kalan)
- **V6.0-ε** (Pro Full + 10 panel + EquityBrain + prompt caching)
- Branch: `main` ve `equity/v6.0` (ikisi de senkron)
- Production: Railway "**trading-agent-production-51c6**"
- URL: `trading-agent-production-51c6.up.railway.app`

### Yedek
- **Tag `v5.7-final-archive`** → V5.7 production snapshot (devine-laughter base)
- Geri dönmek için: `git checkout v5.7-final-archive`

---

## 2. CRYPTO V5.10'da NE VARDI?

V5.10'da crypto modülü **devine-laughter Railway**'inde paper trade canlıda çalışıyordu. Mimari özetleri:

### 2.1 Çekirdek dosyalar (V5.7 tabanı)
```
server/
├── main.py                         # FastAPI uvicorn entry
├── claude_brain.py                 # Multi-step reasoning (Anthropic Claude)
├── regime_detector.py              # 4-component quant regime (BTC odaklı)
├── risk_manager.py                 # ATR-based stop, sektör cap, flash crash
├── scheduler.py                    # Adaptive scan (active/quiet)
├── market_scanner.py               # Core 15 coin universe + indicators
├── news_sentiment.py               # CryptoCompare + sentiment
├── anomaly_detector.py             # Flash crash + suspicious moves
├── gemini_auditor.py               # Gemini Flash-Lite second opinion
├── trade_journal.py / _v2.py       # SQLite seyir defteri
└── broker/
    ├── crypto.py                   # Alpaca crypto + bracket orders
    └── equity.py                   # (Crypto session'ında ignore)
```

### 2.2 V5.8 abstract base'leri (paylaşılan iskelet)
```
server/core/
├── asset_class.py                  # AssetClass.CRYPTO / EQUITY enum
├── base_brain.py                   # Brain interface
├── base_broker.py                  # Broker interface
├── base_regime.py                  # Regime interface
├── base_risk.py                    # Risk interface
└── base_scheduler.py               # Scheduler interface
```

### 2.3 V5.10 crypto-specific eklemeler
| Versiyon | Eklenen şey |
|---|---|
| V5.10-ε | Trade Journal (SQLite seyir defteri) — sektör/asset group + journal endpoints |
| V5.10-ε.1 | Persistent journal — Railway Volume `/app/data/` |
| V5.10-δ | Gemini Auditor council mode (her brain kararını Gemini ikinci görüş) |
| V5.10 final | Real Alpaca orders + close lifecycle + news + anomaly entegre |
| V5.10.1 | Alpaca order status whitelist (max positions gate fix) |
| V5.10.2 | Asset group lookup + HTML cache busting |
| V5.10.3 | renderBrain async fix (blank dashboard) |
| V5.10.4 | Hero "Open Positions" sayacı |
| V5.10-η.3 | Gate intra-run counting + brain lazy api key resolution |

### 2.4 Crypto dashboard
- `server/static/index.html` (eski crypto dashboard, **ORANGE theme** `#f7931a`)
- 12 view SPA: Overview, Markets, Charts, AI Brain, Auto-Execute, Journal, Regime, Positions, Orders, Risk, Account, Settings
- Hero stat'lar: BTC dominance, Total open positions, Portfolio value, P/L
- **DİKKAT:** Equity (V6.0-γ) bu dashboard'u green-tema ile **kopyaladı** (referans için bakabilirsin: `server/static/equity/index.html`)

### 2.5 Universe (Core 15 crypto)
```python
WATCHLIST = ["BTC/USD", "ETH/USD", "SOL/USD", "MATIC/USD", "AVAX/USD",
             "LINK/USD", "DOT/USD", "ADA/USD", "ATOM/USD", "UNI/USD",
             "AAVE/USD", "DOGE/USD", "SHIB/USD", "LTC/USD", "BCH/USD"]
```
+ Extended (BNB, XRP, TRX, NEAR, FTM, vs.) — `market_scanner.py`'da broad scan ile.

### 2.6 V5.7 → V5.10 köşe taşları
- **Bracket orders**: Alpaca crypto'da native değil → manual stop-loss + take-profit threading
- **24/7 scheduler**: Adaptive (active/quiet) — equity'den farklı, hiç kapanmaz
- **PDT yok**: Crypto'da pattern day trade kuralı yok, sektör cap %30
- **Flash crash detector**: 5dk'da %5+ düşüş → emergency_halt
- **Gemini auditor**: Sadece confidence 5-8 audit → ucuz tutmak için tiered

---

## 3. V6.0'a NEYİ TAŞIDIK (equity tarafı)?

Equity için yaptıklarımız crypto için de **birebir uygulanabilir** — şablon olarak kullan:

### 3.1 V6.0-α (foundation)
- `server/equity/journal.py` → crypto için `server/crypto/journal.py` clone (asset_class='crypto')
- `server/equity/audit_impl.py` → crypto için aynı, sadece checklist değişir
- `server/equity/auto_executor.py` → 10-aşama pipeline + 6 gate + phased live (PHASE_PROFILES dict)

### 3.2 V6.0-β (preview app)
- `server/equity_preview_app.py` → crypto için `server/crypto_preview_app.py`
  - V5.7 modüllerini wrapper class'larla sar (`_BrainWrapper`, `_RegimeWrapper`, vb.)
  - Endpoints: `/api/crypto/health`, `/api/crypto/brain`, `/api/crypto/journal`, vs.
  - Static dir: `server/static/crypto/index.html` (orange theme)

### 3.3 V6.0-γ (dashboard)
- Equity dashboard kopyala → renkleri orange'a (#f7931a) geri çevir
- Brand: "MERIDIAN CAPITAL — CRYPTO TERMINAL"
- Logo: M → ₿
- Endpoints: `/api/equity/*` → `/api/crypto/*`

### 3.4 V6.0-δ (cost optimization) ⭐ ÖNEMLİ
**Equity'de ne yaptık:**
- `server/equity/brain_impl.py` → `EquityBrain(BaseBrain)` class
- **Anthropic prompt caching** (ephemeral, 5dk TTL) — static system prompt cache
- **Sonnet 4.5 default** (Opus yerine, %85-90 tasarruf routine call'larda)
- API key resolution: `EQUITY_ANTHROPIC_API_KEY` → `ANTHROPIC_API_KEY` → `sk-ant-` prefix scan
- Telemetry: `/api/equity/brain-usage` (cache hit %, USD cost, savings %)

**Crypto için aynısını yap:**
- `server/crypto/brain_impl.py` → `CryptoBrain(BaseBrain)` class
- `CRYPTO_SYSTEM_PROMPT` static (BTC dominance, funding rate, on-chain, 24/7 bağlam)
- Sonnet 4.5 + prompt caching aynı şekilde
- API key: `CRYPTO_ANTHROPIC_API_KEY` → fallback aynı zincir

### 3.5 V6.0-ε (Pro Full — 10 panel)
**Equity'de hangi panel'leri yaptık:**
1. Sector Heatmap
2. Earnings Calendar (best-effort, news heuristic)
3. Multi-Timeframe Analysis (1Day/4H/1H/15M)
4. Correlation Matrix (pure Python Pearson)
5. Win Rate Trend (haftalık journal)
6. Risk Dashboard (concentration + alerts)
7. Gap Scanner
8. News Timeline (24h sentiment)
9. AI Confidence Stats
10. Trade Replay (event lifecycle)

**Crypto'ya çevir (mantıklı uyarlamalar):**
1. **Asset-class Heatmap** (DeFi/L1/Meme/Stablecoin/Exchange tokens)
2. **Token Unlock Calendar** (Earnings yerine — Cryptorank/Token.unlocks API)
3. MTF aynen — 1Day/4H/1H/15M (crypto 24/7'de bile geçerli)
4. Correlation Matrix — BTC ile her coin'in korelasyonu (BTC-relative beta)
5. Win Rate Trend aynen
6. Risk Dashboard — sektör yerine asset_group (DeFi/L1/Meme)
7. **Funding Rate / Liquidation Map** (Gap Scanner yerine — futures imkanı varsa)
8. News Timeline aynen — CryptoCompare news endpoint
9. AI Confidence Stats aynen
10. Trade Replay aynen

**Pure Python kalsın** — numpy/pandas/yfinance gerek yok. Equity tarafı bunu kanıtladı.

---

## 4. CRYPTO RESUMPTION — Hızlı başlama planı

### Adım 1: Temiz crypto repo'su
```bash
# Mevcut equity-v6 repo'yu klonla, ayrı klasöre çek
git clone https://github.com/FrhnYldzl/trading-agent.git ~/trading-agent-crypto-v6
cd ~/trading-agent-crypto-v6

# V5.7 base'inden start (crypto kodu hâlâ orada V5.10 ile birlikte)
git checkout claude/v5.8-abstract-bases

# Yeni branch — crypto V6.0
git checkout -b crypto/v6.0
```

### Adım 2: Equity referansı çek
Equity v6.0 commitlerini cherry-pick veya manuel kopyala:
- `server/equity/__init__.py` → `server/crypto/__init__.py` template
- `server/equity/journal.py` → `server/crypto/journal.py` (asset_class='crypto')
- `server/equity/auto_executor.py` → adapt for crypto (PDT yok, 24/7 active)
- `server/equity/brain_impl.py` → `server/crypto/brain_impl.py` (CRYPTO_SYSTEM_PROMPT)
- `server/equity/pro_panels.py` → `server/crypto/pro_panels.py` (yukarıda 4.5'te listelenen 10 panel)
- `server/equity_preview_app.py` → `server/crypto_preview_app.py`
- `server/static/equity/index.html` → `server/static/crypto/index.html` (orange theme)

### Adım 3: Railway servis oluştur
- Dashboard'da new project: `trading-agent-crypto-v6` (veya devine-laughter'ı bu branch'e yönlendir)
- Branch: `crypto/v6.0`
- Env vars:
  - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper crypto endpoint için)
  - `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
  - `ANTHROPIC_API_KEY` (veya `CRYPTO_ANTHROPIC_API_KEY`)
  - `EQUITY_GEMINI_API_KEY` opsiyonel
  - `LEGACY_V57_MODE=false` (V5.10 modüllerini değil V6.0 crypto'yu yükle)

### Adım 4: Volume mount (journal persistence)
- Railway service → Settings → Volumes → mount path: `/app/data`
- Journal otomatik bu path'i bulur (`crypto_journal.db`)

### Adım 5: Doğrulama
```
GET /api/crypto/health         → version: "6.0-ε" (or whatever you bump)
GET /api/crypto/pro/index      → 10 panel kataloğu
GET /api/crypto/brain          → Claude AI çalışıyor mu
GET /api/crypto/brain-usage    → prompt caching aktif mi
```

---

## 5. KAYITLI BİLGİLER (yeni session'a yapıştır)

Yeni session'da Claude'a şu özeti ver:

```
Önceki session'dan devir:
- Repo: github.com/FrhnYldzl/trading-agent
- Mevcut durum: equity V6.0-ε main'de canlı
- Crypto için: claude/v5.8-abstract-bases branch'i V5.10 production base
- Yapılacak: Equity'nin V6.0-α..ε commitlerini crypto için template kullan
- Hedef: Crypto V6.0-ε (Pro Full + 10 panel + EquityBrain pattern)
- Cost optimization: Sonnet 4.5 + prompt caching (ephemeral)
- Prod URL: web-production-bdc50.up.railway.app (devine-laughter, kontrol et)

Lütfen CRYPTO_HANDOFF.md'yi oku (repo root'unda) ve oradaki adımlardan devam et.
```

---

## 6. RİSK NOTU

⚠️ **`devine-laughter` Railway servisi** şu an `main` branch'inden deploy alıyor olabilir. Bu artık V6.0-ε equity-only. Crypto'yu bozmamak için:

**ACİL ÇÖZÜM** (devine-laughter'ı V5.7'de tutmak için):
- Railway → devine-laughter service → Variables → `LEGACY_V57_MODE=true` ekle
- Veya: Branch'i `v5.7-final-archive` tag'inden oluşturulmuş yeni bir branch'e ayarla
  ```bash
  git branch v5.7-stable v5.7-final-archive
  git push origin v5.7-stable
  # Railway → devine-laughter → Source → Branch: v5.7-stable
  ```

**TAVSİYE EDİLEN ÇÖZÜM** (yeni session'da yap):
- Crypto modülünü kendi repo'suna ayrıştır (`trading-agent-crypto-v6`)
- devine-laughter'ı oraya yönlendir
- Bu repo (trading-agent) sadece equity için kalsın

---

## 7. EQUITY V6.0-ε — Burada bitti

Equity tarafında tamamlanmış olanlar:
- ✅ V6.0-α: journal + audit + auto_executor (10-aşama pipeline + 6 gate + phased live)
- ✅ V6.0-β: equity_preview_app (FastAPI standalone)
- ✅ V6.0-γ: Green Bloomberg dashboard (12-view SPA)
- ✅ V6.0-δ: EquityBrain — Sonnet 4.5 + prompt caching (~%85 tasarruf)
- ✅ V6.0-ε: 10 Pro panel (sector heatmap, MTF, correlation, win rate, risk, gap, news, AI confidence, replay, earnings)

Henüz yapılmamış (equity için):
- ⏳ V6.0-ζ: API key gen + Python/JS client library + Webhooks
- ⏳ V6.0-η: Phased live transition (Phase 1→4, kill switch, daily summary email)
- ⏳ V6.0-θ: V5.7 trade_journal → V6.0 equity_journal migration

---

## 8. İLETİŞİM NOKTASI

Sorularınız olursa veya devir aldığında takıldığında:
- Bu dokümanı + git log'u referans al
- Equity'nin commit message'ları çok detaylı yazılmış (her commit'in açıklaması var)
- Özellikle `3134996` "V6.0 Equity-Only Branch" commit message'ı equity ayrıştırma stratejisini anlatıyor

İyi şanslar — crypto V6.0-ε'yu bitirdiğinde tekrar burada buluşalım. 🚀

---

*Doküman tarihi: 2026-05-07*
*Equity son commit: cf5596a*
*Crypto base: f3b73e9 (claude/v5.8-abstract-bases)*
*V5.7 archive tag: v5.7-final-archive*
