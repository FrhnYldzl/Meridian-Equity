"""
equity/audit_impl.py — V6.0-α: Equity Gemini Auditor (Council mode).

Crypto'nun audit_impl.py felsefesi equity için:
  Brain (Claude) → Audit (Gemini) → Gates → Risk → Broker → Journal

Equity-specific audit checklist:
  1. Action regime ile uyumlu mu? (Bear regime → no new longs)
  2. RSI tehlikeli mi? (>75 overheating)
  3. PDT day trade quota durumu? (3 trade/5 gün limit)
  4. Earnings yakın mı? (önümüzdeki 7 gün → reject yeni position)
  5. Sektör concentration (mevcut zaten ağır mı, %30 max)
  6. Position size (max %2 risk per trade — equity convention)
  7. Volume anomaly (vol×4+ catalyst'siz)
  8. Pre/post market mi? (limited liquidity)
  9. Market open/close sürec (PDT için kritik)
  10. Bracket order yapısı uygun mu?

Cost optimization (Paket A):
  - Gemini Flash-Lite (Flash yerine, %30 daha ucuz)
  - Tiered audit: confidence 5-8 audit, ≥9 ve ≤4 bypass

API key resolution:
  1. EQUITY_GEMINI_API_KEY (dedicated)
  2. GEMINI_API_KEY (default)
  3. SCAN: 'AIza' prefix (Google API format)

Mevcut equity'nin gemini_auditor.py'sı DOKUNULMAZ — V6.0 ile paralel
yaşar. V6.0-θ (migration) sonrasında legacy kalır referans için.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from core.asset_class import AssetClass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────
# EquityAuditor
# ─────────────────────────────────────────────────────────────────

class EquityAuditor:
    """
    Gemini-based equity trading decision auditor with cost optimization.

    Crypto'nun CryptoAuditor'undan AYRI (asset_class izolasyonu).
    Mevcut gemini_auditor.py'dan da AYRI.
    """

    asset_class = AssetClass.EQUITY
    DEFAULT_MODEL = "gemini-2.0-flash-lite"  # Cost optimization (Paket A): Flash-Lite, %30 ucuz

    def __init__(self, model: str = None):
        self.model = model or os.getenv("EQUITY_GEMINI_MODEL", self.DEFAULT_MODEL)
        api_key, source = self._resolve_api_key()
        self.api_key_source = source
        self.api_key = api_key
        self.enabled = bool(api_key)
        self._last_audit: dict = {
            "status": "Henüz audit yapılmadı",
            "timestamp": None,
            "results": [],
        }

        # Tiered audit thresholds (Paket A optimization)
        self.tier_skip_low = int(os.getenv("EQUITY_AUDIT_SKIP_BELOW", "5"))  # ≤4 atla
        self.tier_skip_high = int(os.getenv("EQUITY_AUDIT_SKIP_ABOVE", "8"))  # ≥9 atla

    @staticmethod
    def _resolve_api_key():
        """Esnek key çözüm — Crypto auditor pattern'i."""
        from dotenv import dotenv_values
        from pathlib import Path
        env_path = Path(__file__).parent.parent.parent / ".env"
        env_vals = dotenv_values(env_path) if env_path.exists() else {}

        for name in ("EQUITY_GEMINI_API_KEY", "GEMINI_API_KEY"):
            v = os.getenv(name) or env_vals.get(name, "")
            if v:
                return v, f"{name} (env)"

        all_keys = {**os.environ, **env_vals}
        for k, v in all_keys.items():
            if isinstance(v, str) and v.startswith("AIza"):
                return v, f"{k} (auto-detected, AIza prefix)"

        return None, "MISSING (hiçbir env var AIza ile başlamıyor)"

    def get_last_audit(self) -> dict:
        return self._last_audit

    # ───────────────────────────────────────────────────────
    # Tiered audit — cost optimization
    # ───────────────────────────────────────────────────────

    def _should_audit(self, decision: dict) -> tuple[bool, str]:
        """
        Tiered audit — confidence'a göre Gemini çağır ya da atla.

        Returns: (should_audit, reason)
        """
        conf = int(decision.get("confidence", 0))
        if conf <= self.tier_skip_low:
            return False, f"low_conf_{conf}"  # gate'lerde zaten reject olur
        if conf >= self.tier_skip_high:
            return False, f"high_conf_{conf}"  # brain çok emin, atla
        return True, "uncertain_band"

    # ───────────────────────────────────────────────────────
    # MAIN — audit batch
    # ───────────────────────────────────────────────────────

    def audit_decisions(
        self,
        decisions: list,
        market_data: dict,
        portfolio: dict,
        regime: str = "unknown",
        pdt_remaining: int = 3,
        market_open: bool = True,
    ) -> list[dict]:
        if not self.enabled:
            self._last_audit = {
                "status": f"Gemini disabled: {self.api_key_source}",
                "timestamp": _now_iso(),
                "results": [],
            }
            return []

        # Sadece actionable kararlar
        actionable = [
            d for d in decisions
            if (d.get("action") or "").lower() in ("long", "short", "close_long", "close_short", "reduce")
        ]
        if not actionable:
            self._last_audit = {
                "status": "Denetlenecek aksiyon yok",
                "timestamp": _now_iso(),
                "results": [],
            }
            return []

        market_summary = self._format_market(market_data, actionable)
        portfolio_summary = self._format_portfolio(portfolio)

        results = []
        skipped = 0
        for decision in actionable:
            # Tiered audit gate
            should_audit, skip_reason = self._should_audit(decision)
            if not should_audit:
                # Auto-approve with skip flag
                results.append({
                    "ticker": decision.get("ticker", "?"),
                    "claude_action": decision.get("action", "?"),
                    "claude_confidence": decision.get("confidence", 0),
                    "audit_verdict": "APPROVE",
                    "reasoning": f"Audit atlandı: {skip_reason} (cost optimization)",
                    "risk_flags": ["audit_skipped"],
                    "risk_score": 5,
                    "modified_params": {},
                    "audit_skipped": True,
                })
                skipped += 1
                continue

            try:
                result = self._audit_single(
                    decision, market_summary, portfolio_summary,
                    regime, pdt_remaining, market_open,
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "ticker": decision.get("ticker", "?"),
                    "claude_action": decision.get("action", "?"),
                    "claude_confidence": decision.get("confidence", 0),
                    "audit_verdict": "APPROVE",
                    "reasoning": f"Gemini offline — auto-approved. Error: {str(e)[:100]}",
                    "risk_flags": ["gemini_unavailable"],
                    "risk_score": 5,
                    "modified_params": {},
                })

        self._last_audit = {
            "status": "ok",
            "timestamp": _now_iso(),
            "total_decisions": len(actionable),
            "audited": len(results) - skipped,
            "skipped": skipped,
            "approved": sum(1 for r in results if r["audit_verdict"] == "APPROVE"),
            "rejected": sum(1 for r in results if r["audit_verdict"] == "REJECT"),
            "modified": sum(1 for r in results if r["audit_verdict"] == "MODIFY"),
            "results": results,
        }
        print(
            f"[EquityAudit] {len(actionable)} karar: "
            f"{len(results) - skipped} audit + {skipped} skipped (cost opt). "
            f"{self._last_audit['approved']} onay / "
            f"{self._last_audit['rejected']} red / "
            f"{self._last_audit['modified']} modify"
        )
        return results

    # ───────────────────────────────────────────────────────
    # Single decision audit
    # ───────────────────────────────────────────────────────

    def _audit_single(
        self, decision: dict, market_summary: str,
        portfolio_summary: str, regime: str,
        pdt_remaining: int, market_open: bool,
    ) -> dict:
        from google import genai

        client = genai.Client(api_key=self.api_key)

        ticker = decision.get("ticker", "?")
        action = decision.get("action", "?")
        confidence = decision.get("confidence", 0)
        reasoning = decision.get("reasoning", "")
        entry_zone = decision.get("entry_zone", "?")
        stop_loss = decision.get("stop_loss", "?")
        take_profit = decision.get("take_profit", "?")
        risk_reward = decision.get("risk_reward", "?")
        position_pct = decision.get("position_size_pct", 0)
        sector = decision.get("sector", "?")

        market_status = "OPEN" if market_open else "CLOSED (after-hours/pre-market)"

        prompt = f"""You are the RISK AUDITOR of an AI equity hedge fund. Independently verify trading decisions made by the primary AI (Claude).

Be SKEPTICAL and CONSERVATIVE. Catch mistakes, flag risks, prevent bad trades.

## EQUITY MARKET CONTEXT
- US equities, regular hours 9:30-16:00 ET
- PDT rule: max 3 day trades per 5-day rolling window for accounts <$25k
- Bracket orders supported (entry + stop + take_profit atomic)
- Sectors: Technology, Healthcare, Financial, Consumer Cyclical, Communication, Industrials, Energy, Utilities, Materials, Real Estate, Consumer Defensive

## CURRENT STATE
Market: {market_status}
Regime: {regime}
PDT Day Trades Remaining: {pdt_remaining}/3

## PORTFOLIO STATE
{portfolio_summary}

## MARKET DATA
{market_summary}

## CLAUDE'S DECISION TO AUDIT
Ticker: {ticker} ({sector})
Action: {action}
Confidence: {confidence}/10
Entry Zone: {entry_zone}
Stop Loss: {stop_loss}
Take Profit: {take_profit}
Risk/Reward: {risk_reward}
Position Size: {position_pct}% of portfolio
Claude's Reasoning: {reasoning}

## EQUITY-SPECIFIC AUDIT CHECKLIST
1. Action aligned with regime? (Bear regime → reject new longs)
2. RSI dangerous? (>75 overheating, >80 extreme)
3. PDT quota? (If pdt_remaining=0 and this is a same-day close, REJECT)
4. Stop appropriate? (Equity ATR ~1-3%, stop should respect ATR)
5. Position size reasonable? (Max 2% risk per trade)
6. Sector concentration? (Already heavy in same sector?)
7. Volume anomaly without clear catalyst?
8. Bracket structure makes sense? (entry/stop/TP coherent)
9. Market hours appropriate? (After-hours = wider spreads, REJECT for low confidence)
10. Earnings risk? (If known earnings within 7 days, mention)

## VERDICT OPTIONS
APPROVE — Mantıklı, riskler kabul edilebilir
REJECT — Riskli, işlem yapılmamalı
MODIFY — Karar fikren OK, ama parametreler değişsin

## RESPONSE FORMAT (JSON only, no markdown)
{{
  "verdict": "APPROVE | REJECT | MODIFY",
  "reasoning": "2-3 sentences",
  "risk_flags": ["regime_mismatch", "overheating", "concentration", "pdt_exhausted", ...],
  "risk_score": 1-10,
  "modified_params": {{}}
}}

For MODIFY: include changed params in modified_params, e.g.:
{{"stop_loss": "new_value", "position_size_pct": 1.0, "take_profit": "new_value"}}"""

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]

        try:
            parsed = json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end+1])
            else:
                raise

        return {
            "ticker": ticker,
            "claude_action": action,
            "claude_confidence": confidence,
            "sector": sector,
            "audit_verdict": parsed.get("verdict", "APPROVE").upper(),
            "reasoning": parsed.get("reasoning", ""),
            "risk_flags": parsed.get("risk_flags", []),
            "risk_score": parsed.get("risk_score", 5),
            "modified_params": parsed.get("modified_params", {}),
        }

    # ───────────────────────────────────────────────────────
    # Format helpers
    # ───────────────────────────────────────────────────────

    @staticmethod
    def _format_market(market_data: dict, decisions: list) -> str:
        lines = []
        tickers = {d.get("ticker") for d in decisions if d.get("ticker")}
        for sym in sorted(tickers):
            d = market_data.get(sym, {})
            if not d or "error" in d:
                continue
            lines.append(
                f"  {sym}: ${d.get('price')} ({d.get('change_pct'):+.2f}%) | "
                f"RSI {d.get('rsi14')} | ATR%{d.get('atr_pct')} | "
                f"Vol×{d.get('volume_ratio')} | trend={d.get('trend')}"
            )
        # Always include SPY for context (equity benchmark)
        if "SPY" not in tickers:
            spy = market_data.get("SPY", {})
            if spy:
                lines.insert(0,
                    f"  SPY (benchmark): ${spy.get('price')} "
                    f"({spy.get('change_pct'):+.2f}%) | trend={spy.get('trend')}"
                )
        return "\n".join(lines) or "  No data"

    @staticmethod
    def _format_portfolio(portfolio: dict) -> str:
        cash = portfolio.get("cash", 0)
        equity = portfolio.get("equity", 0)
        positions = portfolio.get("positions", [])
        lines = [f"  Cash: ${cash:,.2f} | Equity: ${equity:,.2f}"]
        if positions:
            lines.append(f"  Open positions ({len(positions)}):")
            for p in positions:
                lines.append(
                    f"    {p.get('ticker') or p.get('symbol')}: "
                    f"{p.get('qty')} @ ${p.get('avg_entry') or p.get('avg_entry_price', 0):.2f} | "
                    f"PL ${p.get('unrealized_pl', 0):+.2f} ({p.get('sector', '?')})"
                )
        else:
            lines.append("  No open positions (100% cash)")
        return "\n".join(lines)
