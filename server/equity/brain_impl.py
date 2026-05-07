"""
equity/brain_impl.py — V6.0-δ: Cost-optimized Claude AI brain.

V5.7 claude_brain.py'in yerini alır (legacy DOKUNULMADI, main_v57_archive'de).
V6.0 farkları:

  ✓ Prompt Caching (Anthropic ephemeral cache, 5dk TTL)
    Static system prompt (talimat + risk kuralları + strateji çerçevesi +
    multi-step reasoning checklist + response format) cache'lenir.
    Dynamic data (market data, portfolio, trades) cache'lenmez — fresh.
    Sonuç: ~%50-70 input token tasarrufu, kalite aynı.

  ✓ Sonnet 4.5 default (Opus 4.5 yerine)
    Routine kararlar Sonnet — %95 patternlerde Opus paritesi.
    EQUITY_BRAIN_MODEL env var ile override edilebilir
    (örn. yüksek-kritik sinyallerde Opus).

  ✓ Esnek API key resolution
    EQUITY_ANTHROPIC_API_KEY → ANTHROPIC_API_KEY → sk-ant- prefix scan.

  ✓ Aynı API yüzeyi
    run_brain(market_data, portfolio, ...) → V5.7 ile birebir uyumlu
    dict döner. equity_preview_app legacy yerine direkt çağırır.

Maliyet karşılaştırması (1 brain call başına):
  V5.7 (Opus, no cache):       ~5K input + 2K output  ≈ $0.05
  V6.0 (Sonnet, with cache):
    İlk çağrı (cache write):    ~5K input + 2K output  ≈ $0.020
    Sonraki çağrılar (cache hit): ~500 fresh + 4500 cached + 2K output ≈ $0.005
  Tasarruf: ~%85-90 routine çağrılarda.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import dotenv_values, load_dotenv

from core.asset_class import AssetClass
from core.base_brain import BaseBrain

# .env (lokal dev)
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    _env_vals = dotenv_values(_env_path)
else:
    _env_vals = {}


def _get(key: str) -> str:
    return os.getenv(key) or _env_vals.get(key, "")


# Default Sonnet 4.5 — cost optimized (Paket A)
DEFAULT_MODEL = os.getenv("EQUITY_BRAIN_MODEL", "claude-sonnet-4-5-20250929")


# ─────────────────────────────────────────────────────────────────
# STATIC SYSTEM PROMPT — bu kısım cache'lenir (5dk TTL)
# Risk rules + strategy framework + reasoning checklist + format spec
# ─────────────────────────────────────────────────────────────────

EQUITY_SYSTEM_PROMPT = """You are the Chief Trading Officer of an autonomous AI hedge fund managing a US equity (stocks/ETFs) portfolio.
You are NOT an indicator interpreter. You are an executive decision-maker.

Your job is to:
1. FIRST determine the market regime (bull/bear/neutral) — this drives everything.
2. SELECT the optimal strategy for the current regime.
3. ANALYZE each ticker with multi-step reasoning (not just indicators).
4. PROVIDE specific, actionable decisions with entry/exit levels and position sizing.
5. EXPLAIN your reasoning like a fund manager justifying trades to investors.

## STRATEGY FRAMEWORK

### Strategy Selection (regime-based):

- **BULL market**: MOMENTUM strategy (Ross Cameron Gap & Go)
  - Target: stocks with gap_pct > 2%, volume_ratio > 1.5x, strong_uptrend.
  - Entry: pullback to VWAP or EMA9.
  - Exit: trailing EMA9 stop, take profit at 2:1 R/R minimum.

- **NEUTRAL market**: SELECTIVE SWING strategy
  - Target: only highest momentum_score stocks (>70).
  - Entry: only at key support with volume confirmation.
  - 50% smaller position sizes.
  - Prefer ETFs (SPY, QQQ) over individual stocks.

- **BEAR market**: DEFENSIVE / MEAN REVERSION
  - Close or reduce existing long positions.
  - Short only highest-conviction setups.
  - Hold >60% cash.
  - Inverse plays only with extreme confidence.

### Ross Cameron Momentum Criteria (bull regime):
1. Pre-market gap > 4% with catalyst.
2. Relative volume > 2x average.
3. Float rotation (high volume vs shares outstanding).
4. First pullback to VWAP = ideal entry.
5. NEVER chase — if missed entry, wait for next setup.

### Multi-Step Reasoning (REQUIRED per decision):
1. TREND? (EMA structure: 9>21>50 = strong uptrend)
2. MOMENTUM? (RSI band, volume, MACD histogram direction)
3. MACD? (bullish_cross = buy, bearish_cross = sell, histogram growing = momentum increasing)
4. BOLLINGER BANDS? (BB_Pos<0.2 = oversold bounce, BB_Pos>0.8 = overbought)
5. RISK? (ATR-based stop, key support/resistance, BB lower as support)
6. CATALYST? (why is this moving?)
7. ALIGN with regime? (don't go long in bear)
8. R/R ratio? (min 1:2, prefer 1:3)

### SIGNAL CONFLUENCE:
- MACD bullish cross + RSI 40-65 + uptrend = HIGH confidence
- MACD bearish cross + RSI > 70 + downtrend = SELL signal
- BB squeeze (low width) → expansion = breakout imminent
- Lower BB + bullish MACD = mean reversion buy
- Upper BB + bearish MACD divergence = potential reversal

## RISK RULES (ABSOLUTE — NEVER VIOLATE)
1. NEVER risk more than 2% of total equity per trade.
2. Max 3 day trades per 5-day rolling window (PDT rule).
3. PDT trades left = 0 → ONLY swing trades (overnight hold).
4. NEVER all-in on a single position.
5. Bear regime → max 40% invested, 60% cash min.
6. ALWAYS stop-loss plan before entry.
7. Market CLOSED → analyze + watchlist, NO immediate execution.
8. NEVER chase a stock already up 10%+ on the day without pullback.

## POSITION SIZING
- Confidence 8-10: up to 2.0% portfolio risk
- Confidence 6-7: up to 1.5% portfolio risk
- Confidence 4-5: up to 1.0% portfolio risk
- Confidence 1-3: NO TRADE — watch only

## RESPONSE FORMAT (JSON only, no markdown, no extra text)
{
  "regime": "bull | bear | neutral",
  "regime_reasoning": "2-3 sentences explaining WHY this regime based on data",
  "active_strategy": "momentum | selective_swing | defensive | mean_reversion",
  "decisions": [
    {
      "ticker": "NVDA",
      "action": "long | short | close_long | close_short | hold | watch | reduce",
      "confidence": 8,
      "strategy": "momentum",
      "sector": "Technology",
      "reasoning": "Multi-step: (1) EMA9>21>50 strong uptrend, (2) RSI 58 ideal, (3) Vol 2.1x institutional, (4) AI demand catalyst, (5) Aligns bull regime.",
      "entry_zone": "950-960",
      "stop_loss": "935",
      "take_profit": "985",
      "risk_reward": "1:2.5",
      "position_size_pct": 1.5,
      "urgency": "high | medium | low",
      "risk_note": "Earnings 2 weeks — consider reducing before"
    }
  ],
  "market_summary": "3-4 sentences overall market with regime context",
  "portfolio_note": "2-3 sentences: portfolio health, suggested adjustments, cash allocation",
  "watchlist_alerts": [
    {"ticker": "COIN", "alert": "Approaching breakout at $250 resistance, watch volume"}
  ]
}

IMPORTANT:
- Cover TOP 8-10 most relevant tickers (skip low-interest holds).
- Confidence is 1-10 integer.
- Reasoning: 1-2 sentences with key factors.
- entry_zone, stop_loss, take_profit: specific price levels.
- Market CLOSED → urgency="low", note next-session plan.
- KEEP JSON COMPACT — no extra whitespace."""


# ─────────────────────────────────────────────────────────────────
# EquityBrain class
# ─────────────────────────────────────────────────────────────────

class EquityBrain(BaseBrain):
    """
    V6.0 cost-optimized Claude AI brain for equity trading.
    Prompt caching + Sonnet 4.5 default.
    """

    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL
        api_key, source = self._resolve_api_key()
        self.api_key_source = source
        self.enabled = bool(api_key)
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = None

    @staticmethod
    def _resolve_api_key():
        """Esnek key çözümü — crypto pattern'i ile aynı."""
        for name in ("EQUITY_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"):
            v = _get(name)
            if v:
                return v, f"{name} (env)"
        # Scan
        all_keys = {**os.environ, **_env_vals}
        for k, v in all_keys.items():
            if isinstance(v, str) and v.startswith("sk-ant-"):
                return v, f"{k} (auto-detected, sk-ant- prefix)"
        return None, "MISSING (hiçbir env var sk-ant- ile başlamıyor)"

    @property
    def asset_class(self) -> AssetClass:
        return AssetClass.EQUITY

    # ───────────────────────────────────────────────────────
    # MAIN
    # ───────────────────────────────────────────────────────

    def run_brain(
        self,
        market_data: dict,
        portfolio: dict,
        recent_trades: list = None,
        regime: dict = None,
        sentiment: dict = None,
        learning_context: str = None,
        auto_execute: bool = False,
    ) -> dict:
        """
        Run brain with prompt caching.

        Returns equity-compatible dict (V5.7 ile birebir uyumlu).
        """
        if not self.enabled:
            return self._empty("ANTHROPIC_API_KEY (ya da sk-ant- prefix env) eksik")

        if not market_data or "error" in market_data:
            return self._empty(f"Piyasa verisi alınamadı: {market_data.get('error') if market_data else 'veri yok'}")

        meta = market_data.get("_meta", {})
        market_open = meta.get("market_open", False)
        detected_regime = (regime or {}).get("regime") or meta.get("regime", "unknown")

        # Dynamic data formatting
        cash = portfolio.get("cash", 0)
        equity = portfolio.get("equity", 0)
        try:
            from claude_brain import pdt_trades_left
            pdt_left = pdt_trades_left(recent_trades or [])
        except Exception:
            pdt_left = 3

        positions_text = self._format_positions(portfolio)
        market_text = self._format_market_data(market_data)
        ranking_text = self._format_momentum_ranking(market_data)
        trades_text = self._format_recent_trades(recent_trades or [])
        sentiment_text = self._format_sentiment(sentiment) if sentiment else ""
        learning_section = (
            f"\n## LESSONS FROM PAST TRADES\n{learning_context}\n"
            if learning_context else ""
        )

        # ─── DYNAMIC USER MESSAGE (her çağrıda farklı, cache yok) ───
        user_message = f"""## CURRENT STATE
Market Status: {"OPEN" if market_open else "CLOSED (pre/post analysis mode)"}
Pre-detected Regime: {detected_regime}
Portfolio Cash: ${cash:,.2f}
Total Equity: ${equity:,.2f}
PDT Day Trades Remaining: {pdt_left}/3

## OPEN POSITIONS
{positions_text}

## MARKET DATA (with technical indicators)
{market_text}

## MOMENTUM RANKING (sorted by momentum score)
{ranking_text}

## RECENT TRADE HISTORY
{trades_text}{learning_section}{sentiment_text}

Provide your analysis as JSON per the response format specification."""

        # ─── API call with prompt caching ───
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=[
                    {
                        "type": "text",
                        "text": EQUITY_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract usage metrics for cost tracking
            usage = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
                "cache_creation_input_tokens": getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": getattr(
                    response.usage, "cache_read_input_tokens", 0
                ),
            }

            response_text = response.content[0].text
            decisions = self._extract_json(response_text)

            decisions["timestamp"] = datetime.now(timezone.utc).isoformat()
            decisions["model"] = self.model
            decisions["asset_class"] = "equity"
            decisions["_usage"] = usage
            return decisions

        except Exception as e:
            return self._empty(f"Claude API hatası: {e}")

    def review_past_trades(self, recent_trades: list, portfolio: dict) -> dict:
        """V5.7 review_past_trades'i çağır (legacy)."""
        try:
            from claude_brain import review_past_trades
            return review_past_trades(recent_trades, portfolio)
        except Exception as e:
            return {"review": f"Hata: {e}", "lessons": []}

    # ───────────────────────────────────────────────────────
    # Format helpers (V5.7 paritesi)
    # ───────────────────────────────────────────────────────

    @staticmethod
    def _format_positions(portfolio: dict) -> str:
        positions = portfolio.get("positions", [])
        if not positions:
            return "  No open positions (100% cash)"
        lines = []
        for p in positions:
            pl = p.get("unrealized_pl", 0)
            sign = "+" if pl >= 0 else ""
            ticker = p.get("ticker") or p.get("symbol", "?")
            lines.append(
                f"  {ticker}: {p.get('qty', 0)} shares @ ${p.get('avg_entry') or p.get('avg_entry_price', 0):.2f} "
                f"| Now ${p.get('current_price', 0):.2f} | PL {sign}${pl:.2f} ({p.get('sector', '?')})"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_market_data(market_data: dict) -> str:
        lines = []
        for ticker, d in market_data.items():
            if ticker.startswith("_") or "error" in d:
                continue
            ema9 = d.get("ema9") or 0
            ema21 = d.get("ema21") or 0
            ema50 = d.get("ema50") or 0
            ema_struct = ""
            if ema9 and ema21 and ema50:
                if ema9 > ema21 > ema50:
                    ema_struct = "EMA: bull"
                elif ema9 < ema21 < ema50:
                    ema_struct = "EMA: bear"
                else:
                    ema_struct = "EMA: mixed"
            macd_cross = d.get("macd_cross", "none")
            lines.append(
                f"  {ticker}: ${d.get('price')} ({d.get('change_pct', 0):+.2f}%) | "
                f"RSI {d.get('rsi14')} | ATR%{d.get('atr_pct')} | "
                f"Vol×{d.get('volume_ratio')} | Mom {d.get('momentum_score')} | "
                f"{d.get('trend', '?')} | {ema_struct} | MACD {macd_cross}"
            )
        return "\n".join(lines) if lines else "  No data"

    @staticmethod
    def _format_momentum_ranking(market_data: dict) -> str:
        items = []
        for ticker, d in market_data.items():
            if ticker.startswith("_") or "error" in d:
                continue
            score = d.get("momentum_score", 0) or 0
            items.append((ticker, score, d.get("change_pct", 0) or 0))
        items.sort(key=lambda x: x[1], reverse=True)
        top = items[:10]
        return "\n".join(
            f"  #{i+1} {t}: momentum {s} (change {c:+.2f}%)"
            for i, (t, s, c) in enumerate(top)
        ) or "  No ranking data"

    @staticmethod
    def _format_recent_trades(trades: list) -> str:
        if not trades:
            return "  No recent trades"
        lines = []
        for t in trades[-10:]:
            ts = (t.get('timestamp', '?') or '?')[:16]
            lines.append(
                f"  {ts} {t.get('action', '?')} {t.get('ticker') or t.get('symbol', '?')} "
                f"qty={t.get('qty', '?')} @ ${t.get('price', 0):.2f} → {t.get('result', '?')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_sentiment(sentiment: dict) -> str:
        lines = []
        for ticker, info in sentiment.items():
            if isinstance(info, dict):
                score = info.get("score", "?")
                summary = info.get("summary", "")
                lines.append(f"  {ticker}: sentiment {score} — {summary}")
        return "\n## NEWS & SENTIMENT\n" + "\n".join(lines) if lines else ""

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
            return {"error": "JSON parse failed", "raw": text[:500], "decisions": []}

    @staticmethod
    def _empty(reason: str) -> dict:
        return {
            "decisions": [],
            "regime": "unknown",
            "regime_reasoning": reason,
            "active_strategy": "none",
            "market_summary": reason,
            "portfolio_note": "",
            "watchlist_alerts": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "asset_class": "equity",
            "error": reason,
        }
