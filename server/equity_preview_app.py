"""
equity_preview_app.py — V6.0 Standalone FastAPI app for Meridian Equity.

Mevcut V5.7 main.py'a HİÇ DOKUNMAZ. Ayrı Railway project (meridian-equity-v6)
ile deploy edilir. V5.7 'devine-laughter' production hâlâ koşar.

Çalıştır:
    uvicorn equity_preview_app:app --host 0.0.0.0 --port 8001

Endpoint'ler (crypto_preview_app paritesi + equity-specific):
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
    GET  /api/equity/brain              → Claude AI multi-step reasoning
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
"""

import os
import time
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

# V6.0 yeni modüller (full impl)
from equity import (
    EquityJournal,
    EquityAuditor,
    EquityAutoExecutor,
    PHASE_PROFILES,
)

app = FastAPI(title="Meridian Capital — Equity V6.0", version="6.0-β")


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

class _BrainWrapper:
    """V5.7 claude_brain.run_brain'i V6.0 BaseBrain interface'iyle uyumlu sarar."""
    @property
    def asset_class(self): return "equity"
    def run_brain(self, market_data, portfolio, recent_trades=None,
                  regime=None, sentiment=None, learning_context=None):
        return legacy_run_brain(
            market_data=market_data,
            portfolio=portfolio,
            recent_trades=recent_trades or [],
        )
    def review_past_trades(self, recent_trades, portfolio):
        from claude_brain import review_past_trades
        return review_past_trades(recent_trades, portfolio)


_regime = _RegimeWrapper()
_risk = _RiskWrapper()
_scheduler_helper = _SchedulerWrapper()
_brain = _BrainWrapper()

# Cache layer (Crypto pattern)
_cache: dict = {}
DEFAULT_TTL = 30

def _cache_get(key: str, ttl: int = DEFAULT_TTL):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["data"]
    return None

def _cache_set(key: str, data):
    _cache[key] = {"ts": time.time(), "data": data}


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
    return {
        "current": "equity",
        "modules": [
            {
                "id": "equity", "label": "Equity", "icon": "M",
                "color": "#10b981",
                "url": os.getenv("MERIDIAN_EQUITY_URL", "http://127.0.0.1:8001"),
                "active": True, "current": True,
            },
            {
                "id": "crypto", "label": "Crypto", "icon": "₿",
                "color": "#f7931a",
                "url": os.getenv("MERIDIAN_CRYPTO_URL", "http://127.0.0.1:8002"),
                "active": True,
            },
            {
                "id": "options", "label": "Options", "icon": "σ",
                "color": "#3b82f6",
                "url": os.getenv("MERIDIAN_OPTIONS_URL", "http://127.0.0.1:8003"),
                "active": False, "note": "V6.1+",
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
        "version": "6.0-β",
        "asset_class": "equity",
        "dry_run": _broker_dry_run,
        "paper": True,  # V6.0-η'da live mode env var ile değişecek
        "live_mode": _auto_executor.live_mode,
        "live_phase": _auto_executor.live_phase,
        "phase_name": PHASE_PROFILES.get(_auto_executor.live_phase, {}).get("name"),
        "brain_enabled": True,  # V5.7 brain her zaman, ANTHROPIC_API_KEY kontrolü içinde
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
    return {
        "core": list(WATCHLIST),
        "sector_map": SECTOR_MAP,
        "core_count": len(WATCHLIST),
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
            result.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": str(p.side),
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

    from datetime import timedelta
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "4Hour": TimeFrame(4, TimeFrameUnit.Hour),
        "1Day": TimeFrame.Day,
        "1Week": TimeFrame.Week,
    }
    tf = tf_map.get(timeframe, TimeFrame.Day)

    try:
        client = StockHistoricalDataClient(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_SECRET_KEY"),
        )
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

    out = {"benchmark": None, "positions": []}

    # SPY benchmark
    spy = bars("SPY", timeframe=timeframe, days=days)
    out["benchmark"] = {
        "symbol": "SPY",
        "bars": spy.get("bars", []),
        "sector": "ETF",
    }

    # Açık pozisyonlar
    try:
        all_positions = _broker.client.get_all_positions()
        for p in all_positions:
            ac = str(p.asset_class).lower() if p.asset_class else ""
            if "us_equity" not in ac and ac != "":
                continue
            sym = p.symbol
            b = bars(sym, timeframe=timeframe, days=days)
            out["positions"].append({
                "symbol": sym,
                "bars": b.get("bars", []),
                "sector": SECTOR_MAP.get(sym, "Unknown"),
                "position": {
                    "qty": float(p.qty),
                    "side": str(p.side),
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price) if p.current_price else None,
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc),
                },
            })
    except Exception as e:
        out["error"] = f"positions fetch: {e}"

    out["timeframe"] = timeframe
    out["days"] = days
    out["count"] = 1 + len(out["positions"])
    _cache_set(cache_key, out)
    return out


@app.get("/api/equity/symbol-summary/{symbol}")
def symbol_summary(symbol: str):
    """Tek sembol özeti — chart sayfası için."""
    sym = symbol.upper()
    md = _fetch_md_cached(90)
    coin = md.get(sym, {}) if not md.get(sym, {}).get("error") else {}

    # Position lookup
    position = None
    try:
        pos = _broker.get_position(sym)
        if pos:
            position = pos
    except Exception:
        position = None

    return {
        "symbol": sym,
        "sector": SECTOR_MAP.get(sym, "Unknown"),
        "market": {
            "price": coin.get("price"),
            "change_pct": coin.get("change_pct"),
            "rsi14": coin.get("rsi14"),
            "atr_pct": coin.get("atr_pct"),
            "trend": coin.get("trend"),
            "ema9": coin.get("ema9"),
            "ema21": coin.get("ema21"),
            "ema50": coin.get("ema50"),
            "momentum_score": coin.get("momentum_score"),
            "volume_ratio": coin.get("volume_ratio"),
            "macd_cross": coin.get("macd_cross"),
        },
        "position": position,
        "has_position": position is not None,
    }


# ─── Brain & Audit ───────────────────────────────────────────────

@app.get("/api/equity/brain")
def brain_decisions(fresh: bool = False):
    """Claude AI multi-step reasoning. 60sn cache."""
    cache_key = "brain:equity"
    if not fresh:
        hit = _cache_get(cache_key, ttl=60)
        if hit is not None:
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
    _cache_set(cache_key, result)
    return result


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
        "max_risk_pct": 0.02,  # equity standart %2
        "max_sector_pct": _auto_executor.gates.get("MAX_SECTOR_PCT", 30),
        "asset_groups": list(set(SECTOR_MAP.values())),
        "note": "Equity convention: max %2 risk per trade, max %30 sektör concentration.",
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
