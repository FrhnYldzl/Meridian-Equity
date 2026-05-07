"""
equity_preview_app.py — V6.0 Standalone FastAPI app for Meridian Equity.

Mevcut V5.7 main.py'a HİÇ DOKUNMAZ. Ayrı Railway project (meridian-equity-v6)
ile deploy edilir. V5.7 'devine-laughter' production hâlâ koşar.

Çalıştır:
    uvicorn equity_preview_app:app --host 0.0.0.0 --port 8001

Endpoint katalog (Meridian Equity V6.0):
    GET  /                              → HTML dashboard (green theme)
    GET  /api/equity/health             → Server status + diagnostic
    GET  /api/equity/universe           → Core 15 + Extended NDX 100
    GET  /api/equity/account            → Alpaca hesap durumu
    GET  /api/equity/market-data        → Core 15 OHLCV + indikatörler
    GET  /api/equity/extended-data      → Extended evren
    GET  /api/equity/regime             → Quant regime (SPY-benchmark)
    GET  /api/equity/positions          → Açık pozisyonlar
    GET  /api/equity/orders             → Bekleyen emirler
    GET  /api/equity/scheduler          → V5.6 adaptive mode
    GET  /api/equity/risk-config        → Kalibre risk parametreleri
    GET  /api/equity/brain              → Claude AI multi-step reasoning (V6.0-δ caching)
    GET  /api/equity/brain-usage        → Prompt cache hit/miss + cost telemetry
    GET  /api/equity/audit              → Son Gemini audit
    GET  /api/equity/news               → Sentiment + headlines
    GET  /api/equity/anomalies          → Anomaly detection
    GET  /api/equity/scheduler-status   → Auto-executor + 6 gate state
    POST /api/equity/run-now            → Manual pipeline trigger
    GET  /api/equity/journal            → SQLite event log
    GET  /api/equity/journal/performance → Aggregate stats (sektör breakdown)
    GET  /api/equity/journal/run/{id}   → Tek run timeline
    GET  /api/equity/journal/open-trades → Açık trade'ler
    GET  /api/equity/symbol-summary/{symbol}
    GET  /api/equity/bars/{symbol}      → OHLCV bars (chart için)
    GET  /api/equity/overview-charts    → SPY + my positions tek istek
    GET  /api/equity/env-debug          → Diagnostic (env var mask'leri)
    GET  /api/equity/live-config        → Live phase + safety state
    GET  /api/modules                   → Cross-module switcher

V6.0-ε Pro Panels (10 panel — Pro Full):
    GET  /api/equity/pro/index                  → Panel kataloğu
    GET  /api/equity/pro/sector-heatmap         → Sektör heatmap
    GET  /api/equity/pro/earnings-calendar      → Earnings timeline
    GET  /api/equity/pro/mtf/{symbol}           → Multi-timeframe analysis
    GET  /api/equity/pro/correlation-matrix     → Cross-symbol correlation
    GET  /api/equity/pro/win-rate-trend         → Haftalık win rate
    GET  /api/equity/pro/risk-dashboard         → Pozisyon risk metrikleri
    GET  /api/equity/pro/gap-scanner            → Gap + volume scanner
    GET  /api/equity/pro/news-timeline          → News headline timeline
    GET  /api/equity/pro/ai-confidence-stats    → Brain confidence dağılımı
    GET  /api/equity/pro/trade-replay           → Trade event replay
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# .env (lokal dev için)
load_dotenv("../.env")

# V5.7 mevcut modülleri (DOKUNULMUYOR — sadece IMPORT ile kullanıyoruz)
from broker.equity import EquityBroker
from claude_brain import run_brain as legacy_run_brain
from regime_detector import detect_regime as legacy_detect_regime
from risk_manager import RiskManager
from market_scanner import (
    get_market_data, WATCHLIST,
    is_market_open, is_premarket,
)
from news_sentiment import get_market_sentiment, get_ticker_sentiment
from anomaly_detector import detect_anomalies as legacy_detect_anomalies
from gemini_auditor import audit_decisions as legacy_audit_decisions, get_last_audit, is_enabled as gemini_enabled
import scheduler as legacy_sched
from config import SECTOR_MAP
from universe import EXTENDED_SECTOR_MAP, get_extended_universe

# V6.0-ε.6: Birleşik sektör haritası — Core 15 + NDX-100 + SP500 leaders + Crypto-related (~180)
# Core SECTOR_MAP override'lar ana, EXTENDED ek olarak ekle (Core öncelikli).
_MERGED_SECTOR_MAP = {**EXTENDED_SECTOR_MAP, **SECTOR_MAP}

# V6.0 yeni modüller (full impl)
from equity import (
    EquityJournal,
    EquityAuditor,
    EquityAutoExecutor,
    EquityBrain,
    PHASE_PROFILES,
    pro_panels,
)

app = FastAPI(title="Meridian Capital — Equity V6.0", version="6.0-ε.5")


# ─────────────────────────────────────────────────────────────────
# Globals + cache
# ─────────────────────────────────────────────────────────────────

# Broker — V5.7'nin EquityBroker'ı (paper hard-coded), yine kullanıyoruz
# Live transition V6.0-η fazında EquityBroker'a paper=False parametresi eklenecek
_broker_dry_run = (os.getenv("EQUITY_DRY_RUN", "true").lower()
                   in ("true", "1", "yes"))
_broker = EquityBroker()  # paper=True hardcoded mevcut, paralelde dokunulmuyor

# V6.0 instances
_journal = EquityJournal()
_auditor = EquityAuditor()  # Gemini Flash-Lite + tiered audit

# Regime + risk for orchestrator (V5.7 fonksiyonlarını sarmalıyoruz)
class _RegimeWrapper:
    @property
    def asset_class(self): return "equity"
    def detect(self, market_data: dict) -> dict:
        return legacy_detect_regime(market_data)

class _RiskWrapper:
    def __init__(self, max_risk_pct=None):
        self._impl = RiskManager(max_risk_pct=max_risk_pct)
    def dynamic_position_size(self, **kwargs):
        return self._impl.dynamic_position_size(**kwargs)
    def calculate_stop_loss(self, *a, **kw): return self._impl.calculate_stop_loss(*a, **kw)
    def calculate_take_profit(self, *a, **kw): return self._impl.calculate_take_profit(*a, **kw)
    def atr_stop_loss(self, *a, **kw): return self._impl.atr_stop_loss(*a, **kw)
    def atr_take_profit(self, *a, **kw): return self._impl.atr_take_profit(*a, **kw)
    def check_flash_crash(self, *a, **kw): return self._impl.check_flash_crash(*a, **kw)
    def check_sector_exposure(self, *a, **kw): return self._impl.check_sector_exposure(*a, **kw)
    def portfolio_risk_check(self, *a, **kw): return self._impl.portfolio_risk_check(*a, **kw)
    def calculate_risk_metrics(self, *a, **kw): return self._impl.calculate_risk_metrics(*a, **kw)

class _SchedulerWrapper:
    @property
    def asset_class(self): return "equity"
    def detect_scan_mode(self):
        return legacy_sched._detect_scan_mode()
    def is_active_session(self):
        try: return bool(is_market_open() or is_premarket())
        except: return False

# V6.0-δ: _BrainWrapper kaldırıldı — EquityBrain (prompt caching + Sonnet 4.5)
# legacy_run_brain hâlâ import'lu (fallback için) ama kullanılmıyor.
# EquityBrain BaseBrain ABC implementasyonu, V5.7 dict formatı ile birebir uyumlu.

_regime = _RegimeWrapper()
_risk = _RiskWrapper()
_scheduler_helper = _SchedulerWrapper()

# V6.0-δ Cost-optimized brain — EQUITY_BRAIN_MODEL env var ile model değiştirilebilir.
# API key resolution: EQUITY_ANTHROPIC_API_KEY → ANTHROPIC_API_KEY → sk-ant- scan.
_brain = EquityBrain()
print(f"[EquityBrain] model={_brain.model} | enabled={_brain.enabled} | key_source={_brain.api_key_source}")

# Prompt cache + cost telemetry (in-memory rolling)
_brain_usage_log: list = []
_BRAIN_USAGE_MAX = 100

# V6.0-ε: AI confidence stats için brain karar log'u
_brain_decisions_log: list = []
_BRAIN_DECISIONS_MAX = 50

def _record_brain_usage(usage: dict, cached: bool = False):
    """Cost telemetry — son N çağrı sakla, rolling."""
    if not usage:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cached_response": cached,
        **usage,
    }
    _brain_usage_log.append(entry)
    if len(_brain_usage_log) > _BRAIN_USAGE_MAX:
        del _brain_usage_log[: len(_brain_usage_log) - _BRAIN_USAGE_MAX]


def _record_brain_decisions(result: dict):
    """V6.0-ε: Decisions snapshot — confidence stats için."""
    if not isinstance(result, dict):
        return
    decisions = result.get("decisions") or []
    if not decisions:
        return
    entry = {
        "ts": result.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "regime": result.get("regime"),
        "active_strategy": result.get("active_strategy"),
        "decisions": decisions,
    }
    _brain_decisions_log.append(entry)
    if len(_brain_decisions_log) > _BRAIN_DECISIONS_MAX:
        del _brain_decisions_log[: len(_brain_decisions_log) - _BRAIN_DECISIONS_MAX]

# Cache layer — 30sn TTL
_cache: dict = {}
DEFAULT_TTL = 30

def _cache_get(key: str, ttl: int = DEFAULT_TTL):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["data"]
    return None

def _cache_set(key: str, data):
    _cache[key] = {"ts": time.time(), "data": data}


# V6.0-ε.4: Shared Alpaca data client (module-level, parallel-safe singleton)
_alpaca_data_client = None
_alpaca_data_client_lock = None  # init lazy


def _get_alpaca_data_client():
    """Singleton Alpaca historical data client — paralel bars fetch için."""
    global _alpaca_data_client
    if _alpaca_data_client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        _alpaca_data_client = StockHistoricalDataClient(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_SECRET_KEY"),
        )
    return _alpaca_data_client


# Pre-compiled timeframe map (module load'da bir kere)
def _build_tf_map():
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    return {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "4Hour": TimeFrame(4, TimeFrameUnit.Hour),
        "1Day": TimeFrame.Day,
        "1Week": TimeFrame.Week,
    }


_ALPACA_TF_MAP = _build_tf_map()


def _fetch_md_cached(lookback_days: int = 90):
    """V5.7 get_market_data'i cache layer ile sarmalıyor."""
    key = f"md:equity:{lookback_days}"
    hit = _cache_get(key)
    if hit is not None:
        return hit
    data = get_market_data()
    _cache_set(key, data)
    return data


def _fetch_extended_md(lookback_days: int = 90):
    """Extended scan (V5.7 broad scan zaten get_market_data içinde)."""
    return _fetch_md_cached(lookback_days)


# V6.0-ε.6: Lazy single-symbol metrics for extended stocks (NDX/SP500 leaders)
def _compute_extended_metrics(symbol: str) -> dict:
    """Core WATCHLIST'te olmayan extended sembol için bars'tan basit indikatörler hesapla.

    180sn cache. 60 günlük günlük bars üzerinden RSI/EMA/ATR%/52W high-low.
    """
    cache_key = f"ext_metrics:{symbol}"
    hit = _cache_get(cache_key, ttl=180)
    if hit is not None:
        return hit

    try:
        result = bars(symbol, timeframe="1Day", days=90)
        bar_list = result.get("bars", [])
        if len(bar_list) < 20:
            return {"error": "insufficient_bars", "bar_count": len(bar_list)}

        closes = [b["c"] for b in bar_list]
        highs = [b["h"] for b in bar_list]
        lows = [b["l"] for b in bar_list]
        volumes = [b["v"] for b in bar_list]

        last = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else last
        change_pct = round((last - prev) / prev * 100, 2) if prev else 0

        # EMA helper
        def _ema(vals: list, period: int):
            if len(vals) < period: return None
            k = 2 / (period + 1)
            ema = sum(vals[:period]) / period
            for v in vals[period:]:
                ema = v * k + ema * (1 - k)
            return round(ema, 2)

        ema9 = _ema(closes, 9)
        ema21 = _ema(closes, 21)
        ema50 = _ema(closes, 50)

        # Trend (3-EMA structure)
        if ema9 and ema21 and ema50:
            if ema9 > ema21 > ema50:
                trend = "strong_uptrend"
            elif ema9 < ema21 < ema50:
                trend = "strong_downtrend"
            elif ema9 > ema21:
                trend = "uptrend"
            elif ema9 < ema21:
                trend = "downtrend"
            else:
                trend = "sideways"
        else:
            trend = "unknown"

        # RSI 14
        rsi = None
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, len(closes)):
                d = closes[i] - closes[i-1]
                gains.append(max(d, 0))
                losses.append(max(-d, 0))
            avg_g = sum(gains[-14:]) / 14
            avg_l = sum(losses[-14:]) / 14
            if avg_l == 0:
                rsi = 100.0
            else:
                rs = avg_g / avg_l
                rsi = round(100 - 100/(1+rs), 1)

        # ATR%
        atr_pct = None
        if len(bar_list) >= 14:
            trs = []
            for i in range(1, len(bar_list)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]),
                )
                trs.append(tr)
            atr = sum(trs[-14:]) / 14
            atr_pct = round(atr / last * 100, 2) if last else None

        # Volume ratio (last 5 vs avg 30)
        vol_ratio = None
        if len(volumes) >= 30:
            recent = sum(volumes[-5:]) / 5
            baseline = sum(volumes[-30:-5]) / 25
            vol_ratio = round(recent / baseline, 2) if baseline else None

        # MACD (12-26-9)
        macd_cross = "none"
        if len(closes) >= 30:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            if ema12 and ema26:
                # Önceki değerlerle karşılaştırarak son cross'u bul
                # Basit: son 5 candle'da cross olmuşsa rapor
                ema12_prev = _ema(closes[:-1], 12)
                ema26_prev = _ema(closes[:-1], 26)
                if ema12_prev and ema26_prev:
                    if ema12 > ema26 and ema12_prev <= ema26_prev:
                        macd_cross = "bullish"
                    elif ema12 < ema26 and ema12_prev >= ema26_prev:
                        macd_cross = "bearish"

        high_52w = round(max(highs), 2)
        low_52w = round(min(lows), 2)

        # Bollinger Bands (20-period, 2 std)
        bb_upper = bb_lower = bb_pos = None
        if len(closes) >= 20:
            recent = closes[-20:]
            mean = sum(recent) / 20
            variance = sum((x - mean) ** 2 for x in recent) / 20
            std = variance ** 0.5
            bb_upper = round(mean + 2 * std, 2)
            bb_lower = round(mean - 2 * std, 2)
            if bb_upper > bb_lower:
                bb_pos = round((last - bb_lower) / (bb_upper - bb_lower), 2)

        # Momentum score (basit: change_pct + trend bonus)
        momentum = 50
        if change_pct: momentum += int(change_pct * 5)
        if trend == "strong_uptrend": momentum += 20
        elif trend == "uptrend": momentum += 10
        elif trend == "strong_downtrend": momentum -= 20
        elif trend == "downtrend": momentum -= 10
        momentum = max(0, min(100, momentum))

        out = {
            "price": last,
            "change_pct": change_pct,
            "rsi14": rsi,
            "atr_pct": atr_pct,
            "trend": trend,
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "momentum_score": momentum,
            "volume_ratio": vol_ratio,
            "macd_cross": macd_cross,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_pos": bb_pos,
            "_source": "extended_lazy_compute",
        }
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        return {"error": str(e), "_source": "extended_compute_failed"}


# ─────────────────────────────────────────────────────────────────
# V6.0 News + Anomaly callable wrappers (auto_executor için)
# ─────────────────────────────────────────────────────────────────

def _equity_news_fetcher(tickers: list) -> dict:
    """V5.7 news_sentiment'i V6.0 brain formatına çevir."""
    try:
        market_sent = get_market_sentiment(tickers if tickers else WATCHLIST)
        result = {}
        for sym in tickers or WATCHLIST:
            try:
                t_sent = get_ticker_sentiment(sym) if sym in (tickers or []) else None
                if t_sent:
                    result[sym] = {
                        "score": t_sent.get("sentiment_score", 0),
                        "summary": t_sent.get("summary", ""),
                        "headlines_count": len(t_sent.get("articles", [])),
                    }
            except Exception:
                continue
        return result
    except Exception:
        return {}


def _equity_anomaly_detector(market_data: dict) -> dict:
    """V5.7 anomaly_detector'i auto_executor formatına uyarla."""
    try:
        legacy_result = legacy_detect_anomalies(market_data)
        # Legacy ile V6.0 format farklıysa adapt
        if isinstance(legacy_result, dict) and "anomalies" in legacy_result:
            return legacy_result
        return {
            "anomalies": legacy_result if isinstance(legacy_result, list) else [],
            "emergency_halt": False,
            "summary": "Legacy anomaly check",
        }
    except Exception as e:
        return {"anomalies": [], "emergency_halt": False, "summary": f"err: {e}"}


# ─────────────────────────────────────────────────────────────────
# Auto-Executor instance (V6.0-α)
# ─────────────────────────────────────────────────────────────────

_auto_executor = EquityAutoExecutor(
    broker=_broker,
    brain=_brain,
    regime=_regime,
    risk=_risk,
    scheduler_helper=_scheduler_helper,
    data_fetcher=lambda: _fetch_md_cached(90),
    universe=WATCHLIST,
    sector_map=SECTOR_MAP,
    cache_get=_cache_get,
    cache_set=_cache_set,
    journal=_journal,
    auditor=_auditor,
    news_fetcher=_equity_news_fetcher,
    anomaly_detector=_equity_anomaly_detector,
)


@app.on_event("startup")
def _startup():
    """V6.0 startup hook."""
    res = _auto_executor.start_scheduler()
    print(f"[EquityAutoExec] startup: {res}")


@app.on_event("shutdown")
def _shutdown():
    _auto_executor.stop_scheduler()


# ═════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═════════════════════════════════════════════════════════════════

# ─── Cross-module ────────────────────────────────────────────────

@app.get("/api/modules")
def modules():
    # equity/v6.0 branch — sadece equity modülü (crypto bu repodan ayrıştı)
    return {
        "current": "equity",
        "modules": [
            {
                "id": "equity", "label": "Equity", "icon": "M",
                "color": "#10b981",
                "url": os.getenv("MERIDIAN_EQUITY_URL", "http://127.0.0.1:8001"),
                "active": True, "current": True,
            },
        ],
    }


# ─── Health & Diagnostic ─────────────────────────────────────────

@app.get("/api/equity/health")
def health():
    journal_path = _journal.db_path
    journal_persistent = (
        "/app/data" in journal_path
        or os.getenv("EQUITY_JOURNAL_DB_PATH") is not None
    )
    return {
        "status": "ok",
        "module": "equity",
        "version": "6.0-ε.5",
        "asset_class": "equity",
        "dry_run": _broker_dry_run,
        "paper": True,  # V6.0-η'da live mode env var ile değişecek
        "live_mode": _auto_executor.live_mode,
        "live_phase": _auto_executor.live_phase,
        "phase_name": PHASE_PROFILES.get(_auto_executor.live_phase, {}).get("name"),
        "brain_enabled": _brain.enabled,
        "brain_model": _brain.model,
        "brain_api_key_source": _brain.api_key_source,
        "brain_caching": "ephemeral (5min TTL)",  # V6.0-δ
        "auditor_enabled": _auditor.enabled,
        "auditor_api_key_source": _auditor.api_key_source,
        "auditor_model": _auditor.model,
        "journal_db_path": journal_path,
        "journal_persistent": journal_persistent,
        "auto_execute_enabled": _auto_executor.enabled,
        "scheduler_running": bool(_auto_executor._scheduler and _auto_executor._scheduler.running),
        "color": "#10b981",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/equity/env-debug")
def env_debug():
    """Diagnostic — env var isimleri ve değer öncüleri (mask'li)."""
    out = []
    for k, v in os.environ.items():
        if not isinstance(v, str):
            continue
        if v.startswith("sk-ant-"):
            preview = "sk-ant-...(found)"
        elif v.startswith("AIza"):
            preview = "AIza...(found)"
        elif v.startswith("PK"):
            preview = v[:4] + "..."
        elif len(v) > 40:
            preview = "(long, hidden)"
        elif "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
            preview = "(sensitive, hidden)"
        else:
            preview = v[:50]
        out.append({"name": k, "preview": preview})
    out.sort(key=lambda x: x["name"])
    return {
        "env_var_count": len(out),
        "anthropic_key_present": any(
            v.startswith("sk-ant-") for v in os.environ.values()
            if isinstance(v, str)
        ),
        "gemini_key_present": any(
            v.startswith("AIza") for v in os.environ.values()
            if isinstance(v, str)
        ),
        "vars": out,
    }


# ─── Universe & Account ──────────────────────────────────────────

@app.get("/api/equity/universe")
def universe():
    """V6.0-ε.6: Core 15 (auto-execute scan) + Extended ~180 (Charts/Markets dropdown).

    Auto-executor sadece WATCHLIST taraması yapar (~1500 ekran/saat ≈ Core 15).
    Charts ve Markets view'ları extended listesine erişir (NDX-100 + SP500 leaders).
    """
    core_list = list(WATCHLIST)
    extended_list = get_extended_universe()  # ~180 sembol, alfabetik
    # Sektör breakdown (UI için)
    sector_buckets: dict[str, list] = {}
    for sym in extended_list:
        sec = _MERGED_SECTOR_MAP.get(sym, "Unknown")
        sector_buckets.setdefault(sec, []).append(sym)
    sector_summary = {
        sec: {"count": len(syms), "tickers": syms[:5]}  # ilk 5 sample
        for sec, syms in sorted(sector_buckets.items(), key=lambda x: -len(x[1]))
    }
    return {
        "core": core_list,
        "extended": extended_list,
        "sector_map": _MERGED_SECTOR_MAP,
        "asset_groups": _MERGED_SECTOR_MAP,  # backward-compat alias
        "core_count": len(core_list),
        "extended_count": len(extended_list),
        "sector_count": len(sector_buckets),
        "sector_breakdown": sector_summary,
        "asset_class": "equity",
        "note": (
            "Core scan WATCHLIST'i auto-executor için (15 hisse). "
            "Extended ~180 hisse Charts/Markets dropdown ve symbol-summary için. "
            "Brain maliyeti tüm 180 değil, sadece scan sonrası filtre edilen smart prefilter "
            "üzerinden gider."
        ),
    }


@app.get("/api/equity/account")
def account():
    try:
        return _broker.get_account_status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/equity/positions")
def positions():
    try:
        all_positions = _broker.client.get_all_positions()
        result = []
        for p in all_positions:
            ac = str(p.asset_class).lower() if p.asset_class else ""
            if "us_equity" not in ac and ac != "":
                continue
            # V6.0-ε.2: clean side enum
            side_raw = str(p.side) if p.side else ""
            side_clean = side_raw.split(".")[-1].lower()
            result.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": side_clean,        # "long" / "short"
                "side_raw": side_raw,
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "sector": SECTOR_MAP.get(p.symbol, "Unknown"),
            })
        return {"positions": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e), "positions": [], "count": 0}


@app.get("/api/equity/orders")
def pending_orders():
    return {"orders": _broker.get_pending_orders()}


# ─── Market Data ──────────────────────────────────────────────────

@app.get("/api/equity/market-data")
def market_data():
    return _fetch_md_cached(90)


@app.get("/api/equity/extended-data")
def extended_data():
    return _fetch_extended_md(90)


@app.get("/api/equity/regime")
def regime():
    md = _fetch_md_cached(90)
    rkey = "regime:equity"
    hit = _cache_get(rkey, ttl=120)
    if hit is not None:
        return hit
    result = _regime.detect(md)
    _cache_set(rkey, result)
    return result


# ─── Bars (chart için) ────────────────────────────────────────────

@app.get("/api/equity/bars/{symbol}")
def bars(symbol: str, timeframe: str = "1Day", days: int = 30):
    """OHLCV bars for charting. 60sn cache."""
    cache_key = f"bars:eq:{symbol}:{timeframe}:{days}"
    hit = _cache_get(cache_key, ttl=60)
    if hit is not None:
        return hit

    # V6.0-ε.4: shared client instance + tf_map module-scoped (paralel fetch için kritik)
    client = _get_alpaca_data_client()
    tf = _ALPACA_TF_MAP.get(timeframe, _ALPACA_TF_MAP["1Day"])

    try:
        from alpaca.data.requests import StockBarsRequest
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=tf,
            start=start, end=end, feed="iex",
        )
        bars_data = client.get_stock_bars(req)
        ticker_bars = bars_data[symbol]
        out = [
            {"t": b.timestamp.isoformat(), "o": float(b.open), "h": float(b.high),
             "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
            for b in ticker_bars
        ]
        result = {"symbol": symbol, "timeframe": timeframe, "days": days,
                  "bars": out, "count": len(out)}
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "bars": [], "count": 0}


@app.get("/api/equity/overview-charts")
def overview_charts(timeframe: str = "1Day", days: int = 30):
    """SPY (benchmark) + her açık pozisyon için bars — tek istek."""
    cache_key = f"ovc:eq:{timeframe}:{days}"
    hit = _cache_get(cache_key, ttl=30)
    if hit is not None:
        return hit

    out = {"benchmark": None, "btc": None, "positions": []}

    # ─── V6.0-ε.4: Parallel bars fetch (5s → ~500ms) ───
    # Önce sembol listesini topla (SPY + her açık pozisyon)
    pos_meta: list[dict] = []
    try:
        all_positions = _broker.client.get_all_positions()
        for p in all_positions:
            ac = str(p.asset_class).lower() if p.asset_class else ""
            if "us_equity" not in ac and ac != "":
                continue
            side_raw = str(p.side) if p.side else ""
            side_clean = side_raw.split(".")[-1].lower()
            sym = p.symbol
            sector = SECTOR_MAP.get(sym, "Unknown")
            pos_meta.append({
                "symbol": sym,
                "sector": sector,
                "asset_group": sector,
                "position": {
                    "qty": float(p.qty),
                    "side": side_clean,
                    "side_raw": side_raw,
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price) if p.current_price else None,
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc),
                },
            })
    except Exception as e:
        out["error"] = f"positions fetch: {e}"

    symbols_to_fetch = ["SPY"] + [pm["symbol"] for pm in pos_meta]

    # ThreadPoolExecutor ile paralel — Alpaca SDK sync, IO-bound, threading uygun
    with ThreadPoolExecutor(max_workers=min(len(symbols_to_fetch), 12)) as ex:
        bar_results = dict(zip(
            symbols_to_fetch,
            ex.map(lambda s: bars(s, timeframe=timeframe, days=days), symbols_to_fetch)
        ))

    # SPY benchmark
    spy = bar_results.get("SPY", {})
    benchmark = {
        "symbol": "SPY",
        "bars": spy.get("bars", []),
        "sector": "ETF",
    }
    out["benchmark"] = benchmark
    out["btc"] = benchmark  # backward-compat

    # Pozisyon kartları
    for pm in pos_meta:
        b = bar_results.get(pm["symbol"], {})
        out["positions"].append({
            "symbol": pm["symbol"],
            "bars": b.get("bars", []),
            "sector": pm["sector"],
            "asset_group": pm["asset_group"],
            "position": pm["position"],
        })

    out["timeframe"] = timeframe
    out["days"] = days
    out["count"] = 1 + len(out["positions"])
    out["fetch_strategy"] = "parallel_threadpool"
    _cache_set(cache_key, out)
    return out


@app.get("/api/equity/symbol-summary/{symbol}")
def symbol_summary(symbol: str):
    """Tek sembol özeti — chart sayfası için. V6.0-ε.5 expanded metrics."""
    sym = symbol.upper()
    md = _fetch_md_cached(90)
    coin = md.get(sym, {}) if not md.get(sym, {}).get("error") else {}
    # V6.0-ε.6: extended map ile sektör lookup (~180 sembol için)
    sector = _MERGED_SECTOR_MAP.get(sym, "Unknown")

    # V6.0-ε.6: Extended symbol için lazy compute (Core değilse)
    if not coin and sym in _MERGED_SECTOR_MAP:
        coin = _compute_extended_metrics(sym)

    # Position lookup — V6.0-ε.5: side enum cleanup + structured payload
    position = None
    try:
        all_positions = _broker.client.get_all_positions()
        for p in all_positions:
            if p.symbol == sym:
                side_raw = str(p.side) if p.side else ""
                position = {
                    "qty": float(p.qty),
                    "side": side_raw.split(".")[-1].lower(),  # clean
                    "side_raw": side_raw,
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price) if p.current_price else None,
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc),
                    "asset_class": str(p.asset_class) if p.asset_class else "us_equity",
                }
                break
    except Exception:
        position = None

    # Bollinger Bands ve volume tahmini (market_data'da varsa al)
    bb_upper = coin.get("bb_upper")
    bb_lower = coin.get("bb_lower")
    bb_pos = coin.get("bb_pos")
    macd_hist = coin.get("macd_hist")
    macd_signal = coin.get("macd_signal")

    # Trend signal — multi-factor (güven veren)
    trend = coin.get("trend", "unknown")
    rsi = coin.get("rsi14") or 50
    macd_cross = coin.get("macd_cross", "none")
    vol_ratio = coin.get("volume_ratio") or 0
    signal_score = 0
    signal_reasons = []
    if trend in ("strong_uptrend", "uptrend"):
        signal_score += 2 if trend == "strong_uptrend" else 1
        signal_reasons.append(f"Trend: {trend}")
    elif trend in ("strong_downtrend", "downtrend"):
        signal_score -= 2 if trend == "strong_downtrend" else 1
        signal_reasons.append(f"Trend: {trend}")
    if macd_cross == "bullish":
        signal_score += 1
        signal_reasons.append("MACD bullish cross")
    elif macd_cross == "bearish":
        signal_score -= 1
        signal_reasons.append("MACD bearish cross")
    if 40 <= rsi <= 65:
        signal_score += 1
        signal_reasons.append(f"RSI sweet spot ({rsi:.0f})")
    elif rsi > 75:
        signal_score -= 1
        signal_reasons.append(f"RSI overbought ({rsi:.0f})")
    elif rsi < 30:
        signal_score += 1
        signal_reasons.append(f"RSI oversold ({rsi:.0f})")
    if vol_ratio > 1.5:
        signal_score += 1
        signal_reasons.append(f"Vol ×{vol_ratio:.1f}")

    if signal_score >= 3:
        signal = "STRONG_BUY"
    elif signal_score >= 1:
        signal = "BUY"
    elif signal_score <= -3:
        signal = "STRONG_SELL"
    elif signal_score <= -1:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    return {
        "symbol": sym,
        "sector": sector,
        "asset_group": sector,  # backward-compat alias for old JS bindings
        "market": {
            "price": coin.get("price"),
            "change_pct": coin.get("change_pct"),
            "rsi14": coin.get("rsi14"),
            "atr_pct": coin.get("atr_pct"),
            "trend": trend,
            "ema9": coin.get("ema9"),
            "ema21": coin.get("ema21"),
            "ema50": coin.get("ema50"),
            "momentum_score": coin.get("momentum_score"),
            "volume_ratio": coin.get("volume_ratio"),
            "macd_cross": macd_cross,
            "macd_hist": macd_hist,
            "macd_signal": macd_signal,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_pos": bb_pos,
            "high_52w": coin.get("high_52w"),
            "low_52w": coin.get("low_52w"),
        },
        "signal": {
            "label": signal,
            "score": signal_score,
            "reasons": signal_reasons,
        },
        "position": position,
        "has_position": position is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Brain & Audit ───────────────────────────────────────────────

@app.get("/api/equity/brain")
def brain_decisions(fresh: bool = False):
    """Claude AI multi-step reasoning.

    V6.0-ε.4: 300sn endpoint cache (TTL Anthropic prompt caching ile aynı).
    Manuel fresh için ?fresh=true.
    Cache hit halinde zero API call.
    """
    cache_key = "brain:equity"
    if not fresh:
        hit = _cache_get(cache_key, ttl=300)  # 5dk — Anthropic ephemeral cache TTL ile aligned
        if hit is not None:
            # Cache hit — telemetry'ye yansıt (token=0)
            _record_brain_usage({"input_tokens": 0, "output_tokens": 0,
                                 "cache_creation_input_tokens": 0,
                                 "cache_read_input_tokens": 0,
                                 "model": _brain.model, "served_from": "endpoint_cache"},
                                cached=True)
            return hit

    md = _fetch_md_cached(90)
    regime = _regime.detect(md)

    try:
        acct = _broker.client.get_account()
        positions_raw = _broker.client.get_all_positions()
        positions = [
            {
                "ticker": p.symbol,
                "qty": float(p.qty),
                "avg_entry": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "unrealized_pl": float(p.unrealized_pl),
                "sector": SECTOR_MAP.get(p.symbol, "Unknown"),
            }
            for p in positions_raw
            if not p.asset_class or "us_equity" in str(p.asset_class).lower()
        ]
        portfolio = {
            "cash": float(acct.cash),
            "equity": float(acct.equity),
            "positions": positions,
        }
    except Exception as e:
        portfolio = {"cash": 0, "equity": 0, "positions": [], "error": str(e)}

    result = _brain.run_brain(
        market_data=md, portfolio=portfolio,
        recent_trades=[], regime=regime,
    )

    # V6.0-δ: usage telemetry (Anthropic prompt caching metrikleri)
    if isinstance(result, dict) and "_usage" in result:
        usage = dict(result["_usage"])
        usage["model"] = _brain.model
        _record_brain_usage(usage, cached=False)

    # V6.0-ε: decisions log → confidence stats panel
    _record_brain_decisions(result)

    _cache_set(cache_key, result)
    return result


@app.get("/api/equity/brain-usage")
def brain_usage():
    """V6.0-δ: Prompt cache hit/miss + token cost telemetry.

    Cache hit %s, ortalama tokens/call, ve maliyet projeksiyonu.
    """
    if not _brain_usage_log:
        return {
            "model": _brain.model,
            "calls": 0,
            "cache_hit_rate": 0,
            "totals": {},
            "recent": [],
            "note": "Henüz brain çağrısı yapılmadı.",
        }

    total = len(_brain_usage_log)
    cached = sum(1 for x in _brain_usage_log if x.get("cached_response"))
    fresh_calls = [x for x in _brain_usage_log if not x.get("cached_response")]

    sum_input = sum(x.get("input_tokens", 0) for x in fresh_calls)
    sum_output = sum(x.get("output_tokens", 0) for x in fresh_calls)
    sum_cache_create = sum(
        x.get("cache_creation_input_tokens", 0) for x in fresh_calls
    )
    sum_cache_read = sum(
        x.get("cache_read_input_tokens", 0) for x in fresh_calls
    )

    cache_token_total = sum_cache_create + sum_cache_read
    prompt_cache_hit_rate = (
        sum_cache_read / cache_token_total * 100 if cache_token_total else 0
    )

    # Sonnet 4.5 fiyatlandırması (USD/MTok)
    PRICE = {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,  # 1.25x base input
        "cache_read": 0.30,    # 0.1x base input
    }
    cost_input = sum_input * PRICE["input"] / 1_000_000
    cost_output = sum_output * PRICE["output"] / 1_000_000
    cost_cache_write = sum_cache_create * PRICE["cache_write"] / 1_000_000
    cost_cache_read = sum_cache_read * PRICE["cache_read"] / 1_000_000
    cost_total = cost_input + cost_output + cost_cache_write + cost_cache_read

    # Eğer cache hiç kullanılmasaydı (proxy: cache_read = fresh input)
    cost_no_cache_input = (sum_input + sum_cache_read) * PRICE["input"] / 1_000_000
    cost_no_cache = cost_no_cache_input + cost_output
    saved = max(cost_no_cache - cost_total, 0)
    saved_pct = (saved / cost_no_cache * 100) if cost_no_cache else 0

    return {
        "model": _brain.model,
        "calls": total,
        "endpoint_cache_hits": cached,
        "endpoint_cache_hit_rate_pct": round(cached / total * 100, 1),
        "fresh_api_calls": len(fresh_calls),
        "totals": {
            "input_tokens": sum_input,
            "output_tokens": sum_output,
            "cache_creation_input_tokens": sum_cache_create,
            "cache_read_input_tokens": sum_cache_read,
        },
        "prompt_cache_hit_rate_pct": round(prompt_cache_hit_rate, 1),
        "cost_usd": {
            "fresh_input": round(cost_input, 4),
            "output": round(cost_output, 4),
            "cache_write": round(cost_cache_write, 4),
            "cache_read": round(cost_cache_read, 4),
            "total": round(cost_total, 4),
            "if_no_cache": round(cost_no_cache, 4),
            "saved": round(saved, 4),
            "saved_pct": round(saved_pct, 1),
        },
        "recent": _brain_usage_log[-20:],
        "note": (
            f"Prompt caching ({_brain.model}) — endpoint cache hit %{round(cached/total*100,1)}, "
            f"prompt cache read %{round(prompt_cache_hit_rate,1)}, "
            f"toplam tasarruf ~%{round(saved_pct,1)}."
        ),
    }


@app.get("/api/equity/audit")
def audit_status():
    return _auditor.get_last_audit()


# ─── News & Anomaly ──────────────────────────────────────────────

@app.get("/api/equity/news")
def news_endpoint(force: bool = False):
    """Equity news + sentiment (V5.7 news_sentiment'tan)."""
    cache_key = "news:equity"
    if not force:
        hit = _cache_get(cache_key, ttl=600)
        if hit is not None:
            return hit
    try:
        result = get_market_sentiment(WATCHLIST)
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/equity/anomalies")
def anomalies_endpoint():
    """Anomaly detection (V5.7 anomaly_detector'dan)."""
    md = _fetch_md_cached(90)
    return _equity_anomaly_detector(md)


# ─── Auto-Execute ────────────────────────────────────────────────

@app.get("/api/equity/scheduler")
def scheduler_endpoint():
    mode, interval = _scheduler_helper.detect_scan_mode()
    return {
        "mode": mode,
        "interval_minutes": interval,
        "is_active_session": _scheduler_helper.is_active_session(),
        "asset_class": "equity",
        "note": "Equity hours: market 9:30-16 ET, pre 4-9:30, after 16-20.",
    }


@app.get("/api/equity/scheduler-status")
def scheduler_status():
    return _auto_executor.get_status()


@app.post("/api/equity/run-now")
def run_now():
    """Manuel pipeline trigger."""
    return _auto_executor.run_once(force=True)


@app.get("/api/equity/risk-config")
def risk_config():
    return {
        "max_risk_pct": 0.02,                    # equity standart %2
        "max_sector_pct": _auto_executor.gates.get("MAX_SECTOR_PCT", 30),
        "default_atr_multiplier": 2.0,           # ATR-based stop loss multiplier
        "default_stop_pct": 0.02,                # fallback stop pct (%2)
        "default_take_profit_atr_multiplier": 3.0,  # ATR-based TP (1:1.5 R/R minimum)
        "asset_groups": list(set(SECTOR_MAP.values())),
        "sector_count": len(set(SECTOR_MAP.values())),
        "max_open_positions": _auto_executor.gates.get("MAX_OPEN_POSITIONS", 5),
        "min_confidence": _auto_executor.gates.get("MIN_CONFIDENCE", 6),
        "symbol_cooldown_hours": _auto_executor.gates.get("SYMBOL_COOLDOWN_HOURS", 4),
        "asset_class": "equity",
        "note": "Equity convention: max %2 risk per trade, max %30 sektör concentration, ATR×2 stop, ATR×3 TP.",
    }


@app.get("/api/equity/live-config")
def live_config():
    """V6.0-η: Live trading phase + safety state."""
    return {
        "live_mode": _auto_executor.live_mode,
        "live_confirmed": _auto_executor.live_confirmed,
        "live_phase": _auto_executor.live_phase,
        "phase_profile": PHASE_PROFILES.get(_auto_executor.live_phase, {}),
        "all_phases": PHASE_PROFILES,
        "two_factor_check": (
            "PASS" if (_auto_executor.live_mode and _auto_executor.live_confirmed)
            else "FORCED_PAPER (LIVE_MODE+LIVE_CONFIRMED ikisi de gerekli)"
        ),
    }


# ─── Journal ─────────────────────────────────────────────────────

@app.get("/api/equity/journal")
def journal_recent(limit: int = 100, event_type: str = None,
                   symbol: str = None, live_only: bool = False):
    return {
        "entries": _journal.get_recent(
            limit=limit, event_type=event_type,
            symbol=symbol, live_only=live_only,
        ),
        "filters": {
            "limit": limit, "event_type": event_type,
            "symbol": symbol, "live_only": live_only,
        },
    }


@app.get("/api/equity/journal/performance")
def journal_performance(days: int = 30, live_only: bool = False):
    return _journal.get_performance(days=days, live_only=live_only)


@app.get("/api/equity/journal/run/{pipeline_run_id}")
def journal_run_timeline(pipeline_run_id: str):
    return {
        "pipeline_run_id": pipeline_run_id,
        "events": _journal.get_by_pipeline_run(pipeline_run_id),
    }


@app.get("/api/equity/journal/open-trades")
def journal_open_trades():
    return {"open_trades": _journal.get_open_trades()}


# ═════════════════════════════════════════════════════════════════
# V6.0-ε: PRO PANELS (10 panels)
# ═════════════════════════════════════════════════════════════════

# ─── 1. Sektör Heatmap ───────────────────────────────────────────

@app.get("/api/equity/pro/sector-heatmap")
def pro_sector_heatmap():
    """Sektör bazlı momentum + winners/losers + rotation score."""
    cache_key = "pro:sector-heatmap"
    hit = _cache_get(cache_key, ttl=60)
    if hit is not None:
        return hit
    md = _fetch_md_cached(90)
    result = pro_panels.compute_sector_heatmap(md, SECTOR_MAP)
    _cache_set(cache_key, result)
    return result


# ─── 2. Earnings Calendar ────────────────────────────────────────

@app.get("/api/equity/pro/earnings-calendar")
def pro_earnings_calendar(days_ahead: int = 14):
    """Yaklaşan earnings — Alpaca news heuristic. Best-effort."""
    cache_key = f"pro:earnings:{days_ahead}"
    hit = _cache_get(cache_key, ttl=900)  # 15dk
    if hit is not None:
        return hit
    result = pro_panels.compute_earnings_calendar(
        news_fetcher=lambda syms: get_market_sentiment(syms),
        symbols=list(WATCHLIST),
        days_ahead=days_ahead,
    )
    _cache_set(cache_key, result)
    return result


# ─── 3. MTF Analysis ─────────────────────────────────────────────

@app.get("/api/equity/pro/mtf/{symbol}")
def pro_mtf_summary(symbol: str):
    """1Day/4Hour/1Hour/15Min trend alignment."""
    sym = symbol.upper()
    cache_key = f"pro:mtf:{sym}"
    hit = _cache_get(cache_key, ttl=120)
    if hit is not None:
        return hit
    result = pro_panels.compute_mtf_summary(sym, bars_fetcher=bars)
    _cache_set(cache_key, result)
    return result


# ─── 4. Correlation Matrix ───────────────────────────────────────

@app.get("/api/equity/pro/correlation-matrix")
def pro_correlation_matrix(days: int = 30,
                           timeframe: str = "1Day",
                           symbols: Optional[str] = None):
    """Cross-symbol getiri korelasyonu (pure Python Pearson)."""
    sym_list = ([s.strip().upper() for s in symbols.split(",") if s.strip()]
                if symbols else list(WATCHLIST)[:10])
    cache_key = f"pro:corr:{','.join(sym_list)}:{timeframe}:{days}"
    hit = _cache_get(cache_key, ttl=600)  # 10dk
    if hit is not None:
        return hit
    result = pro_panels.compute_correlation_matrix(
        symbols=sym_list, bars_fetcher=bars, days=days, timeframe=timeframe,
    )
    _cache_set(cache_key, result)
    return result


# ─── 5. Win Rate Trend ───────────────────────────────────────────

@app.get("/api/equity/pro/win-rate-trend")
def pro_win_rate_trend(days: int = 90, bucket_days: int = 7):
    """Journal'dan haftalık win rate trend."""
    return pro_panels.compute_win_rate_trend(
        journal=_journal, days=days, bucket_days=bucket_days,
    )


# ─── 6. Risk Dashboard ───────────────────────────────────────────

@app.get("/api/equity/pro/risk-dashboard")
def pro_risk_dashboard():
    """Pozisyon-seviyesi + portföy-seviyesi risk metrikleri."""
    cache_key = "pro:risk-dashboard"
    hit = _cache_get(cache_key, ttl=30)
    if hit is not None:
        return hit

    # Hesap + pozisyonlar
    try:
        acct = _broker.get_account_status()
    except Exception as e:
        acct = {"error": str(e), "equity": 0, "cash": 0}

    try:
        positions_raw = _broker.client.get_all_positions()
        positions = []
        for p in positions_raw:
            ac = str(p.asset_class).lower() if p.asset_class else ""
            if "us_equity" not in ac and ac != "":
                continue
            positions.append({
                "symbol": p.symbol, "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
            })
    except Exception as e:
        positions = []
        acct["positions_error"] = str(e)

    md = _fetch_md_cached(90)
    result = pro_panels.compute_risk_dashboard(
        positions=positions, account=acct,
        market_data=md, sector_map=SECTOR_MAP,
    )
    _cache_set(cache_key, result)
    return result


# ─── 7. Gap Scanner ──────────────────────────────────────────────

@app.get("/api/equity/pro/gap-scanner")
def pro_gap_scanner(min_gap_pct: float = 1.0):
    """En büyük gap'ler ile volume confirmation taraması."""
    cache_key = f"pro:gap:{min_gap_pct}"
    hit = _cache_get(cache_key, ttl=60)
    if hit is not None:
        return hit
    md = _fetch_md_cached(90)
    result = pro_panels.compute_gap_scanner(
        market_data=md, sector_map=SECTOR_MAP, min_gap_pct=min_gap_pct,
    )
    _cache_set(cache_key, result)
    return result


# ─── 8. News Timeline ────────────────────────────────────────────

@app.get("/api/equity/pro/news-timeline")
def pro_news_timeline(hours: int = 24):
    """Headline timeline (sentiment + ts)."""
    cache_key = f"pro:news-timeline:{hours}"
    hit = _cache_get(cache_key, ttl=600)
    if hit is not None:
        return hit
    try:
        news_result = get_market_sentiment(WATCHLIST)
    except Exception as e:
        news_result = {"error": str(e)}
    result = pro_panels.compute_news_timeline(news_result, hours=hours)
    _cache_set(cache_key, result)
    return result


# ─── 9. AI Confidence Stats ──────────────────────────────────────

@app.get("/api/equity/pro/ai-confidence-stats")
def pro_ai_confidence_stats(recent_n: int = 50):
    """Brain karar dağılımı + confidence trend (rolling)."""
    return pro_panels.compute_ai_confidence_stats(
        brain_decisions_log=_brain_decisions_log, recent_n=recent_n,
    )


# ─── 10. Trade Replay ────────────────────────────────────────────

@app.get("/api/equity/pro/trade-replay")
def pro_trade_replay(ticker: Optional[str] = None,
                     pipeline_run_id: Optional[str] = None,
                     limit: int = 200):
    """Tek trade'in event timeline'ı — pipeline_run veya ticker bazlı."""
    return pro_panels.compute_trade_replay(
        journal=_journal, ticker=ticker,
        pipeline_run_id=pipeline_run_id, limit=limit,
    )


# ─── Pro panels index endpoint ───────────────────────────────────

@app.get("/api/equity/pro/index")
def pro_panels_index():
    """V6.0-ε panel kataloğu — dashboard için."""
    return {
        "panels": [
            {"id": 1, "name": "Sector Heatmap", "endpoint": "/api/equity/pro/sector-heatmap"},
            {"id": 2, "name": "Earnings Calendar", "endpoint": "/api/equity/pro/earnings-calendar"},
            {"id": 3, "name": "MTF Analysis", "endpoint": "/api/equity/pro/mtf/{symbol}"},
            {"id": 4, "name": "Correlation Matrix", "endpoint": "/api/equity/pro/correlation-matrix"},
            {"id": 5, "name": "Win Rate Trend", "endpoint": "/api/equity/pro/win-rate-trend"},
            {"id": 6, "name": "Risk Dashboard", "endpoint": "/api/equity/pro/risk-dashboard"},
            {"id": 7, "name": "Gap Scanner", "endpoint": "/api/equity/pro/gap-scanner"},
            {"id": 8, "name": "News Timeline", "endpoint": "/api/equity/pro/news-timeline"},
            {"id": 9, "name": "AI Confidence Stats", "endpoint": "/api/equity/pro/ai-confidence-stats"},
            {"id": 10, "name": "Trade Replay", "endpoint": "/api/equity/pro/trade-replay"},
        ],
        "version": "6.0-ε.5",
        "asset_class": "equity",
    }


# ─── Static dashboard ─────────────────────────────────────────────

_static_dir = Path(__file__).parent / "static" / "equity"


@app.get("/", response_class=HTMLResponse)
def root():
    """Bloomberg-grade green-themed equity dashboard.

    Cache busting: HTML her zaman fresh çekilir.
    """
    index_path = _static_dir / "index.html"
    if not index_path.exists():
        # Fallback — V6.0-γ'da static/equity/index.html oluşacak
        return HTMLResponse(
            "<html><body style='background:#08090d;color:#10b981;padding:40px;font-family:monospace;'>"
            "<h1>🟢 Meridian Capital — Equity V6.0-β</h1>"
            "<p>Backend ✅ — Dashboard V6.0-γ'da geliyor.</p>"
            "<p>Endpoints: <a href='/api/equity/health' style='color:#34d399;'>health</a> · "
            "<a href='/api/equity/brain' style='color:#34d399;'>brain</a> · "
            "<a href='/api/equity/scheduler-status' style='color:#34d399;'>auto-exec</a> · "
            "<a href='/api/equity/journal' style='color:#34d399;'>journal</a></p>"
            "</body></html>"
        )
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# Static asset mounting (CSS/JS dosyaları için)
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
