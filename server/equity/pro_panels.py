"""
equity/pro_panels.py — V6.0-ε: Pro Full panel hesaplamaları.

Saf hesaplama fonksiyonları — IO yok, dependency'ler argüman olarak verilir.
equity_preview_app.py thin endpoint'lerle bu modülü çağırır.

Panel listesi:
  1. sector_heatmap        — Sektör bazlı momentum + winners/losers
  2. earnings_calendar     — Yaklaşan earnings (Alpaca news heuristic)
  3. mtf_summary           — Multi-timeframe trend alignment
  4. correlation_matrix    — Cross-symbol getiri korelasyonu (pure Python Pearson)
  5. win_rate_trend        — Haftalık win rate journal'dan
  6. risk_dashboard        — Pozisyon-seviyesi risk metrikleri + sektör concentration
  7. gap_scanner           — En büyük gap'ler ile volume confirmation
  8. news_timeline         — Headline timeline (sentiment + ts)
  9. ai_confidence_stats   — Brain karar dağılımı (rolling)
 10. trade_replay          — Tek pipeline_run veya ticker için event timeline

Pure Python — numpy/pandas dependency yok (Railway slim image).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional


# ══════════════════════════════════════════════════════════════════
# 1. SECTOR HEATMAP
# ══════════════════════════════════════════════════════════════════

def compute_sector_heatmap(market_data: dict, sector_map: dict) -> dict:
    """
    Sektör bazlı momentum, winners/losers, sektör rotation indikatörü.

    Returns:
        {
          "sectors": [
            {"name": "Technology", "ticker_count": 5,
             "avg_change_pct": 2.3, "median_change_pct": 1.8,
             "avg_momentum": 65.2, "winners": 4, "losers": 1,
             "best": {"ticker":"NVDA","change_pct":4.2},
             "worst": {"ticker":"AMD","change_pct":-0.5},
             "tickers": ["NVDA","AMD",...]},
            ...
          ],
          "total_tickers": 15,
          "rotation_score": 0.34
        }
    """
    by_sector: dict[str, list] = defaultdict(list)
    for ticker, d in market_data.items():
        if ticker.startswith("_") or "error" in d:
            continue
        sector = sector_map.get(ticker, "Unknown")
        by_sector[sector].append({
            "ticker": ticker,
            "change_pct": d.get("change_pct") or 0,
            "momentum_score": d.get("momentum_score") or 0,
            "rsi14": d.get("rsi14") or 0,
            "volume_ratio": d.get("volume_ratio") or 0,
            "trend": d.get("trend", "?"),
        })

    sectors = []
    for sector, items in by_sector.items():
        if not items:
            continue
        changes = [i["change_pct"] for i in items]
        moms = [i["momentum_score"] for i in items]
        winners = sum(1 for c in changes if c > 0)
        losers = sum(1 for c in changes if c < 0)
        best = max(items, key=lambda x: x["change_pct"])
        worst = min(items, key=lambda x: x["change_pct"])
        sectors.append({
            "name": sector,
            "ticker_count": len(items),
            "avg_change_pct": round(sum(changes) / len(changes), 2),
            "median_change_pct": round(statistics.median(changes), 2) if changes else 0,
            "avg_momentum": round(sum(moms) / len(moms), 1) if moms else 0,
            "winners": winners,
            "losers": losers,
            "neutral": len(items) - winners - losers,
            "best": {"ticker": best["ticker"], "change_pct": best["change_pct"]},
            "worst": {"ticker": worst["ticker"], "change_pct": worst["change_pct"]},
            "tickers": [i["ticker"] for i in sorted(items, key=lambda x: -x["change_pct"])],
        })
    sectors.sort(key=lambda s: s["avg_change_pct"], reverse=True)

    # Rotation score: best vs worst sector spread
    if len(sectors) >= 2:
        rotation = round(sectors[0]["avg_change_pct"] - sectors[-1]["avg_change_pct"], 2)
    else:
        rotation = 0
    total_tickers = sum(s["ticker_count"] for s in sectors)

    return {
        "sectors": sectors,
        "total_tickers": total_tickers,
        "rotation_score": rotation,
        "leader": sectors[0]["name"] if sectors else None,
        "laggard": sectors[-1]["name"] if sectors else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 2. EARNINGS CALENDAR (best-effort)
# ══════════════════════════════════════════════════════════════════

def compute_earnings_calendar(news_fetcher, symbols: list, days_ahead: int = 14) -> dict:
    """
    Yaklaşan earnings — Alpaca news 'earnings' topic heuristic.

    Production'da Polygon/Finnhub earnings endpoint daha temiz, ama Paket A'da
    ek dependency yok. news headlines'tan "earnings" geçen + tarih içeren
    items'ı extract ediyoruz.

    Args:
        news_fetcher: lambda symbols → news result (headlines + ts)
        symbols: ticker listesi
        days_ahead: bakılacak gün

    Returns:
        {"events": [{"ticker":"NVDA","date":"2026-05-21","summary":"..."}],
         "data_source": "news_heuristic", "limitations": "..."}
    """
    events = []
    try:
        news_result = news_fetcher(symbols) if news_fetcher else {}
    except Exception as e:
        return {
            "events": [],
            "error": f"news fetcher hatası: {e}",
            "data_source": "news_heuristic",
        }

    # news_result yapısı: {ticker: {summary, articles: [{title, ts, ...}]}}
    if isinstance(news_result, dict) and "articles" in news_result:
        # Market-level result
        articles = news_result.get("articles", [])
    else:
        articles = []
        for sym, info in (news_result or {}).items():
            if isinstance(info, dict):
                for a in info.get("articles", []) or []:
                    a = dict(a)
                    a.setdefault("ticker", sym)
                    articles.append(a)

    seen_keys = set()
    for art in articles:
        title = (art.get("title") or "").lower()
        if "earnings" not in title and "earning" not in title:
            continue
        ticker = art.get("ticker") or art.get("symbols", [None])[0] if isinstance(art.get("symbols"), list) else art.get("ticker")
        if not ticker:
            continue
        key = (ticker, title[:60])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        events.append({
            "ticker": ticker,
            "headline": art.get("title", ""),
            "date_hint": art.get("created_at") or art.get("published_utc") or art.get("ts"),
            "url": art.get("url"),
        })

    return {
        "events": events[:50],
        "count": len(events),
        "data_source": "alpaca_news_heuristic",
        "limitations": (
            "Best-effort earnings extraction from news headlines. "
            "Production: Polygon/Finnhub earnings endpoint önerilir."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 3. MULTI-TIMEFRAME (MTF) ANALYSIS
# ══════════════════════════════════════════════════════════════════

def _ema_from_closes(closes: list, period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi_from_closes(closes: list, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)


def _trend_from_closes(closes: list) -> str:
    if len(closes) < 50:
        return "insufficient_data"
    e9 = _ema_from_closes(closes, 9)
    e21 = _ema_from_closes(closes, 21)
    e50 = _ema_from_closes(closes, 50)
    if e9 and e21 and e50:
        if e9 > e21 > e50:
            return "strong_uptrend"
        if e9 < e21 < e50:
            return "strong_downtrend"
        if e9 > e21:
            return "uptrend"
        if e9 < e21:
            return "downtrend"
    return "sideways"


def compute_mtf_summary(symbol: str, bars_fetcher) -> dict:
    """
    Multi-timeframe trend alignment: 1Day, 4Hour, 1Hour, 15Min.
    bars_fetcher(symbol, timeframe, days) → {"bars": [{c:price,...}]}

    Returns:
        {"symbol": "NVDA",
         "timeframes": {
           "1Day":  {"trend":"strong_uptrend","rsi":58,"close":960,"bars":N},
           ...
         },
         "alignment": "fully_bullish | fully_bearish | mixed",
         "score": 8  (out of 10),
         "interpretation": "..."}
    """
    tf_specs = [
        ("1Day", 60),
        ("4Hour", 30),
        ("1Hour", 10),
        ("15Min", 3),
    ]
    timeframes = {}
    bull_count, bear_count, total = 0, 0, 0

    for tf, days in tf_specs:
        try:
            res = bars_fetcher(symbol, timeframe=tf, days=days)
            bars = res.get("bars", []) if isinstance(res, dict) else []
            closes = [float(b["c"]) for b in bars if b.get("c") is not None]
            if len(closes) < 10:
                timeframes[tf] = {"error": "insufficient_data", "bar_count": len(closes)}
                continue
            trend = _trend_from_closes(closes)
            rsi = _rsi_from_closes(closes)
            timeframes[tf] = {
                "trend": trend,
                "rsi": rsi,
                "close": closes[-1] if closes else None,
                "first_close": closes[0] if closes else None,
                "change_pct": round((closes[-1] - closes[0]) / closes[0] * 100, 2) if closes and closes[0] else 0,
                "bar_count": len(closes),
            }
            total += 1
            if trend in ("strong_uptrend", "uptrend"):
                bull_count += 1
            elif trend in ("strong_downtrend", "downtrend"):
                bear_count += 1
        except Exception as e:
            timeframes[tf] = {"error": str(e)}

    if total == 0:
        alignment = "no_data"
        score = 0
    elif bull_count == total:
        alignment = "fully_bullish"
        score = 10
    elif bear_count == total:
        alignment = "fully_bearish"
        score = 10  # high conviction short
    else:
        alignment = "mixed"
        score = max(bull_count, bear_count) * 10 // total

    if alignment == "fully_bullish":
        interp = "Tüm timeframe'ler bullish — momentum trade için yüksek conviction."
    elif alignment == "fully_bearish":
        interp = "Tüm timeframe'ler bearish — long pozisyondan kaçın, short setup ara."
    elif alignment == "mixed":
        interp = f"Timeframe'ler arası uyumsuzluk ({bull_count} bull / {bear_count} bear / {total} total) — düşük conviction, küçük pozisyon."
    else:
        interp = "Yetersiz veri."

    return {
        "symbol": symbol,
        "timeframes": timeframes,
        "alignment": alignment,
        "bull_timeframes": bull_count,
        "bear_timeframes": bear_count,
        "total_timeframes": total,
        "score": score,
        "interpretation": interp,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 4. CORRELATION MATRIX
# ══════════════════════════════════════════════════════════════════

def _pearson(xs: list, ys: list) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sx2 = sum((x - mx) ** 2 for x in xs)
    sy2 = sum((y - my) ** 2 for y in ys)
    if sx2 == 0 or sy2 == 0:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return round(sxy / math.sqrt(sx2 * sy2), 3)


def compute_correlation_matrix(symbols: list, bars_fetcher,
                               days: int = 30, timeframe: str = "1Day") -> dict:
    """
    Sembol-arası getiri (daily return) korelasyonu.

    Returns:
        {"symbols": ["NVDA","AAPL",...],
         "matrix": [[1.0, 0.72,...],...],
         "highest_corr": {"pair":["NVDA","AAPL"],"value":0.87},
         "lowest_corr": {...},
         "diversification_score": 0-100}
    """
    returns_by_symbol: dict[str, list] = {}
    for sym in symbols:
        try:
            res = bars_fetcher(sym, timeframe=timeframe, days=days)
            bars = res.get("bars", []) if isinstance(res, dict) else []
            closes = [float(b["c"]) for b in bars if b.get("c") is not None]
            if len(closes) < 5:
                continue
            rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
            returns_by_symbol[sym] = rets
        except Exception:
            continue

    valid_symbols = list(returns_by_symbol.keys())
    if len(valid_symbols) < 2:
        return {
            "symbols": valid_symbols,
            "matrix": [],
            "error": "En az 2 sembol için getiri verisi gerekli",
        }

    # Hizala — ortak en kısa uzunluk
    min_len = min(len(r) for r in returns_by_symbol.values())
    aligned = {s: r[-min_len:] for s, r in returns_by_symbol.items()}

    matrix = []
    pairs = []
    for i, s1 in enumerate(valid_symbols):
        row = []
        for j, s2 in enumerate(valid_symbols):
            if i == j:
                row.append(1.0)
            else:
                c = _pearson(aligned[s1], aligned[s2])
                row.append(c if c is not None else 0.0)
                if i < j and c is not None:
                    pairs.append({"pair": [s1, s2], "value": c})
        matrix.append(row)

    pairs.sort(key=lambda x: x["value"], reverse=True)
    highest = pairs[0] if pairs else None
    lowest = pairs[-1] if pairs else None
    avg_corr = sum(p["value"] for p in pairs) / len(pairs) if pairs else 0
    diversification = round((1 - avg_corr) * 100, 1)

    return {
        "symbols": valid_symbols,
        "matrix": matrix,
        "data_points": min_len,
        "timeframe": timeframe,
        "lookback_days": days,
        "highest_corr": highest,
        "lowest_corr": lowest,
        "avg_correlation": round(avg_corr, 3),
        "diversification_score": diversification,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 5. WIN RATE TREND
# ══════════════════════════════════════════════════════════════════

def compute_win_rate_trend(journal, days: int = 90, bucket_days: int = 7) -> dict:
    """
    Journal'dan win rate haftalık (veya custom bucket) trend.

    Bucket = bucket_days. Default 7 = haftalık.
    Win = trade_close event with pnl > 0.

    Returns:
        {"buckets": [
           {"start":"2026-04-01","end":"2026-04-07",
            "trades":12,"wins":7,"losses":5,
            "win_rate_pct":58.3,"total_pnl":234.50},
           ...
         ],
         "overall_win_rate": 60.0,
         "trend": "improving|declining|stable"}
    """
    try:
        events = journal.get_recent(limit=10000, event_type="trade_close")
    except Exception as e:
        return {"buckets": [], "error": f"journal hatası: {e}"}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    closes = []
    for e in events:
        ts_str = e.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        # PnL extraction — payload veya direct field
        payload = e.get("payload") or {}
        if isinstance(payload, str):
            try:
                import json
                payload = json.loads(payload)
            except Exception:
                payload = {}
        pnl = payload.get("pnl") or e.get("pnl") or 0
        try:
            pnl = float(pnl)
        except Exception:
            pnl = 0
        closes.append({"ts": ts, "pnl": pnl})

    closes.sort(key=lambda x: x["ts"])

    # Bucket
    buckets = []
    if not closes:
        return {
            "buckets": [],
            "overall_win_rate": 0,
            "total_trades": 0,
            "trend": "no_data",
            "lookback_days": days,
        }

    bucket_delta = timedelta(days=bucket_days)
    bucket_start = cutoff
    while bucket_start < now:
        bucket_end = bucket_start + bucket_delta
        in_bucket = [c for c in closes if bucket_start <= c["ts"] < bucket_end]
        wins = sum(1 for c in in_bucket if c["pnl"] > 0)
        losses = sum(1 for c in in_bucket if c["pnl"] < 0)
        total_pnl = sum(c["pnl"] for c in in_bucket)
        n = len(in_bucket)
        if n > 0:
            buckets.append({
                "start": bucket_start.date().isoformat(),
                "end": bucket_end.date().isoformat(),
                "trades": n,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": round(wins / n * 100, 1) if n else 0,
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / n, 2) if n else 0,
            })
        bucket_start = bucket_end

    overall_wins = sum(1 for c in closes if c["pnl"] > 0)
    overall_total = len(closes)
    overall_wr = round(overall_wins / overall_total * 100, 1) if overall_total else 0

    # Trend: ilk yarı vs ikinci yarı
    if len(buckets) >= 4:
        half = len(buckets) // 2
        first_wr = sum(b["win_rate_pct"] for b in buckets[:half]) / half if half else 0
        second_wr = sum(b["win_rate_pct"] for b in buckets[half:]) / (len(buckets) - half) if (len(buckets) - half) else 0
        diff = second_wr - first_wr
        if diff > 5:
            trend = "improving"
        elif diff < -5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_buckets"

    return {
        "buckets": buckets,
        "bucket_days": bucket_days,
        "overall_win_rate": overall_wr,
        "total_trades": overall_total,
        "total_pnl": round(sum(c["pnl"] for c in closes), 2),
        "trend": trend,
        "lookback_days": days,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 6. RISK DASHBOARD
# ══════════════════════════════════════════════════════════════════

def compute_risk_dashboard(positions: list, account: dict, market_data: dict,
                            sector_map: dict) -> dict:
    """
    Pozisyon-seviyesi + portföy-seviyesi risk metrikleri.

    Returns:
        {
          "portfolio": {"equity":...,"cash":...,"cash_pct":...,
                        "invested_pct":...,"position_count":N},
          "positions": [
            {"ticker":"NVDA","value":...,"pct_of_equity":...,
             "atr_pct":...,"distance_to_stop_pct":...,
             "unrealized_plpc":...},
            ...
          ],
          "concentration": {"top1_pct":...,"top3_pct":...,
                            "max_sector_pct":...,"max_sector":"Tech"},
          "alerts": ["..."]
        }
    """
    equity = float(account.get("equity") or account.get("portfolio_value") or 0)
    cash = float(account.get("cash") or 0)
    cash_pct = (cash / equity * 100) if equity else 0
    invested = equity - cash
    invested_pct = (invested / equity * 100) if equity else 0

    pos_details = []
    by_sector_value: dict[str, float] = defaultdict(float)
    for p in positions or []:
        sym = p.get("symbol") or p.get("ticker") or ""
        mv = float(p.get("market_value") or 0)
        pct_eq = (mv / equity * 100) if equity else 0
        sector = sector_map.get(sym, "Unknown")
        md = market_data.get(sym, {}) if market_data else {}
        atr_pct = md.get("atr_pct")
        unrealized_pl = float(p.get("unrealized_pl") or 0)
        unrealized_plpc = float(p.get("unrealized_plpc") or 0) * (100 if abs(float(p.get("unrealized_plpc") or 0)) < 1 else 1)
        pos_details.append({
            "ticker": sym,
            "sector": sector,
            "qty": float(p.get("qty") or 0),
            "market_value": round(mv, 2),
            "pct_of_equity": round(pct_eq, 2),
            "avg_entry": float(p.get("avg_entry_price") or p.get("avg_entry") or 0),
            "current_price": float(p.get("current_price") or 0) if p.get("current_price") else None,
            "atr_pct": atr_pct,
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_plpc": round(unrealized_plpc, 2),
        })
        by_sector_value[sector] += mv

    pos_details.sort(key=lambda x: x["pct_of_equity"], reverse=True)

    top1_pct = pos_details[0]["pct_of_equity"] if pos_details else 0
    top3_pct = sum(p["pct_of_equity"] for p in pos_details[:3])
    sector_concentration = sorted(
        [{"sector": s, "value": round(v, 2),
          "pct_of_equity": round((v / equity * 100) if equity else 0, 2)}
         for s, v in by_sector_value.items()],
        key=lambda x: -x["pct_of_equity"],
    )
    max_sector = sector_concentration[0] if sector_concentration else None

    # Alerts
    alerts = []
    if top1_pct > 25:
        alerts.append(f"Tek pozisyon konsantrasyon: {pos_details[0]['ticker']} %{top1_pct:.1f} portföy (>25% risk)")
    if max_sector and max_sector["pct_of_equity"] > 35:
        alerts.append(f"Sektör konsantrasyonu: {max_sector['sector']} %{max_sector['pct_of_equity']:.1f} (>35% risk)")
    if cash_pct < 10:
        alerts.append(f"Düşük cash: %{cash_pct:.1f} (acil çıkış sırasında esnek değil)")
    if invested_pct > 90:
        alerts.append(f"Yüksek invested: %{invested_pct:.1f} (regime değişimi tehlikeli)")

    return {
        "portfolio": {
            "equity": round(equity, 2),
            "cash": round(cash, 2),
            "invested": round(invested, 2),
            "cash_pct": round(cash_pct, 2),
            "invested_pct": round(invested_pct, 2),
            "position_count": len(pos_details),
        },
        "positions": pos_details,
        "concentration": {
            "top1_pct": round(top1_pct, 2),
            "top3_pct": round(top3_pct, 2),
            "sectors": sector_concentration,
            "max_sector_pct": round(max_sector["pct_of_equity"], 2) if max_sector else 0,
            "max_sector": max_sector["sector"] if max_sector else None,
        },
        "alerts": alerts,
        "alert_count": len(alerts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 7. GAP SCANNER
# ══════════════════════════════════════════════════════════════════

def compute_gap_scanner(market_data: dict, sector_map: dict,
                        min_gap_pct: float = 1.0) -> dict:
    """
    Premarket/open gap'leri ile volume confirmation taraması.

    market_data'da gap_pct varsa onu kullanır, yoksa change_pct.

    Returns:
        {"gaps": [
           {"ticker":"NVDA","gap_pct":4.2,"volume_ratio":2.1,
            "confirmed":True,"sector":"Tech","direction":"up"},
           ...
         ],
         "confirmed_count": N,  // gap + volume birlikte
         "unconfirmed_count": M}
    """
    gaps = []
    for ticker, d in market_data.items():
        if ticker.startswith("_") or "error" in d:
            continue
        gap_pct = d.get("gap_pct")
        if gap_pct is None:
            gap_pct = d.get("change_pct") or 0
        if abs(gap_pct) < min_gap_pct:
            continue
        vol_ratio = d.get("volume_ratio") or 0
        confirmed = abs(gap_pct) >= min_gap_pct and vol_ratio >= 1.5
        gaps.append({
            "ticker": ticker,
            "sector": sector_map.get(ticker, "Unknown"),
            "gap_pct": round(gap_pct, 2),
            "direction": "up" if gap_pct > 0 else "down",
            "volume_ratio": round(vol_ratio, 2),
            "confirmed": confirmed,
            "rsi14": d.get("rsi14"),
            "momentum_score": d.get("momentum_score"),
            "trend": d.get("trend"),
            "price": d.get("price"),
        })
    gaps.sort(key=lambda g: abs(g["gap_pct"]), reverse=True)
    confirmed = sum(1 for g in gaps if g["confirmed"])
    return {
        "gaps": gaps[:30],
        "total_with_gap": len(gaps),
        "confirmed_count": confirmed,
        "unconfirmed_count": len(gaps) - confirmed,
        "min_gap_pct": min_gap_pct,
        "criteria": "abs(gap_pct) >= min_gap_pct AND volume_ratio >= 1.5",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 8. NEWS TIMELINE
# ══════════════════════════════════════════════════════════════════

def compute_news_timeline(news_result: dict, hours: int = 24) -> dict:
    """
    News headlines flat timeline (sentiment + ts ile).

    Returns:
        {"timeline": [
           {"ts":"...","ticker":"NVDA","title":"...",
            "sentiment":"positive","score":0.8,"url":"..."},
           ...
         ],
         "buckets": {"positive":N,"negative":M,"neutral":K},
         "total":N+M+K}
    """
    items = []
    if not news_result:
        return {"timeline": [], "total": 0, "buckets": {"positive": 0, "negative": 0, "neutral": 0}}

    if isinstance(news_result, dict):
        if "articles" in news_result and isinstance(news_result["articles"], list):
            for a in news_result["articles"]:
                items.append({
                    "ticker": a.get("ticker") or "MARKET",
                    "title": a.get("title", ""),
                    "ts": a.get("created_at") or a.get("published_utc") or a.get("ts"),
                    "score": a.get("sentiment_score") or a.get("score") or 0,
                    "url": a.get("url"),
                })
        else:
            for sym, info in news_result.items():
                if not isinstance(info, dict):
                    continue
                for a in info.get("articles", []) or []:
                    items.append({
                        "ticker": sym,
                        "title": a.get("title", ""),
                        "ts": a.get("created_at") or a.get("published_utc") or a.get("ts"),
                        "score": a.get("sentiment_score") or a.get("score") or info.get("sentiment_score", 0),
                        "url": a.get("url"),
                    })

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    fresh = []
    for it in items:
        ts_str = it.get("ts")
        if not ts_str:
            fresh.append(it)
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ts >= cutoff:
                fresh.append(it)
        except Exception:
            fresh.append(it)

    # Sentiment label
    pos, neg, neu = 0, 0, 0
    for it in fresh:
        s = it.get("score") or 0
        try:
            s = float(s)
        except Exception:
            s = 0
        if s > 0.2:
            it["sentiment"] = "positive"
            pos += 1
        elif s < -0.2:
            it["sentiment"] = "negative"
            neg += 1
        else:
            it["sentiment"] = "neutral"
            neu += 1

    # Sort by ts desc (newest first)
    def _ts_key(x):
        ts = x.get("ts")
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0
    fresh.sort(key=_ts_key, reverse=True)

    return {
        "timeline": fresh[:100],
        "total": len(fresh),
        "buckets": {"positive": pos, "negative": neg, "neutral": neu},
        "lookback_hours": hours,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 9. AI CONFIDENCE STATS
# ══════════════════════════════════════════════════════════════════

def compute_ai_confidence_stats(brain_decisions_log: list,
                                  recent_n: int = 50) -> dict:
    """
    Brain karar log'undan confidence dağılımı + trend.

    brain_decisions_log: [{"ts":"...","decisions":[{...,"confidence":N,"action":"long|hold|..."},...]}]

    Returns:
        {"distribution": {1:0,2:0,...,10:N},
         "by_action": {"long":[...],"short":[...]},
         "mean":7.2,"median":7,
         "high_conviction_pct":34.0,
         "recent_runs":N}
    """
    if not brain_decisions_log:
        return {
            "distribution": {},
            "by_action": {},
            "mean": 0,
            "median": 0,
            "high_conviction_pct": 0,
            "recent_runs": 0,
            "total_decisions": 0,
        }

    recent = brain_decisions_log[-recent_n:]
    confidences = []
    by_action: dict[str, list] = defaultdict(list)
    distribution = {i: 0 for i in range(1, 11)}

    for run in recent:
        decisions = run.get("decisions", []) if isinstance(run, dict) else []
        for d in decisions:
            if not isinstance(d, dict):
                continue
            try:
                c = int(d.get("confidence") or 0)
            except Exception:
                continue
            if 1 <= c <= 10:
                confidences.append(c)
                distribution[c] += 1
                action = (d.get("action") or "unknown").lower()
                by_action[action].append(c)

    if not confidences:
        return {
            "distribution": distribution,
            "by_action": {},
            "mean": 0,
            "median": 0,
            "high_conviction_pct": 0,
            "recent_runs": len(recent),
            "total_decisions": 0,
        }

    mean = round(sum(confidences) / len(confidences), 2)
    median = round(statistics.median(confidences), 1)
    high_conv = sum(1 for c in confidences if c >= 8)
    high_conv_pct = round(high_conv / len(confidences) * 100, 1)

    by_action_summary = {
        action: {
            "count": len(arr),
            "mean_confidence": round(sum(arr) / len(arr), 2) if arr else 0,
        }
        for action, arr in by_action.items()
    }

    return {
        "distribution": distribution,
        "by_action": by_action_summary,
        "mean": mean,
        "median": median,
        "high_conviction_pct": high_conv_pct,
        "recent_runs": len(recent),
        "total_decisions": len(confidences),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 10. TRADE REPLAY
# ══════════════════════════════════════════════════════════════════

def compute_trade_replay(journal, ticker: str = None,
                          pipeline_run_id: str = None,
                          limit: int = 200) -> dict:
    """
    Tek trade'in event timeline'ı — pipeline_run veya ticker bazlı.

    Returns:
        {"events":[{ts,event_type,...}], "summary":{...}}
    """
    if pipeline_run_id:
        try:
            events = journal.get_by_pipeline_run(pipeline_run_id)
        except Exception as e:
            return {"events": [], "error": f"journal hatası: {e}"}
    elif ticker:
        try:
            events = journal.get_recent(limit=limit, symbol=ticker.upper())
        except Exception as e:
            return {"events": [], "error": f"journal hatası: {e}"}
    else:
        return {"events": [], "error": "ticker veya pipeline_run_id gerekli"}

    # Summary
    event_types = defaultdict(int)
    first_ts, last_ts = None, None
    pnl_total = 0.0
    has_open, has_close = False, False
    for e in events:
        et = e.get("event_type", "")
        event_types[et] += 1
        ts = e.get("timestamp")
        if ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
        if et == "trade_open":
            has_open = True
        elif et == "trade_close":
            has_close = True
            payload = e.get("payload") or {}
            if isinstance(payload, str):
                try:
                    import json
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            pnl_total += float(payload.get("pnl") or 0)

    return {
        "events": events,
        "event_count": len(events),
        "summary": {
            "first_ts": first_ts,
            "last_ts": last_ts,
            "event_types": dict(event_types),
            "has_open": has_open,
            "has_close": has_close,
            "lifecycle_complete": has_open and has_close,
            "total_pnl": round(pnl_total, 2),
        },
        "filter": {"ticker": ticker, "pipeline_run_id": pipeline_run_id},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
