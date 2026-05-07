"""
equity/auto_executor.py — V6.0-α: Equity AutoExecutor.

Crypto'nun CryptoAutoExecutor'ının equity karşılığı + cost optimization +
phased live trading support.

Pipeline (10 aşama):
  1. Pre-flight (account, daily anchor, PDT count)
  2. Trade Close Lifecycle (manual close detect, stop/TP zaten bracket'ta)
  3. Anomaly Detection (flash crash, gap risk, halt)
  4. Market Data + Regime
  5. ★ Cost Opt: Smart pre-filter (top momentum candidates)
  6. ★ Cost Opt: Skip if flat market
  7. News + Sentiment
  8. Brain (Claude) — prompt cached
  9. Audit (Gemini) — tiered (sadece conf 5-8)
  10. Anomaly halt + Audit + Safety Gates (incl. PDT)
  11. Risk Sizing (max 2% — equity convention)
  12. Broker Execute (live_phase'e göre güvenlik katmanları)
  13. Journal log (event_type ile)

Live Phase System (V6.0-η detail):
  Phase 0: Paper only (default)
  Phase 1: Paper, V6.0 stable test
  Phase 2: Live ultra-conservative ($50 max, conf≥8)
  Phase 3: Live moderate ($200 max, conf≥7)
  Phase 4: Live full ($500 max, conf≥6)

Master switches (env):
  EQUITY_AUTO_EXECUTE=true/false        — scheduler aktif mi
  EQUITY_DRY_RUN=true/false              — broker simulation mı
  EQUITY_LIVE_MODE=true/false            — live (real money) mı
  EQUITY_LIVE_CONFIRMED=true/false       — extra confirmation
  EQUITY_LIVE_PHASE=0,1,2,3,4            — hangi faz aktif
"""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.asset_class import AssetClass
from equity.journal import EquityJournal


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isofmt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _env_int(key: str, default: int) -> int:
    try: return int(os.getenv(key, str(default)))
    except: return default


def _env_float(key: str, default: float) -> float:
    try: return float(os.getenv(key, str(default)))
    except: return default


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key, str(default).lower()).lower()
    return v in ("true", "1", "yes")


# ─────────────────────────────────────────────────────────────────
# Phase-based safety profile
# ─────────────────────────────────────────────────────────────────

PHASE_PROFILES = {
    0: {  # Paper only — full crypto-equivalent settings
        "max_notional": 500,
        "max_open_positions": 3,
        "daily_loss_halt_pct": -2.0,
        "min_confidence": 6,
        "name": "Paper",
    },
    1: {  # V6.0 stabilization
        "max_notional": 500,
        "max_open_positions": 3,
        "daily_loss_halt_pct": -2.0,
        "min_confidence": 6,
        "name": "Paper V6.0 Stabilize",
    },
    2: {  # Ultra conservative live
        "max_notional": 50,
        "max_open_positions": 2,
        "daily_loss_halt_pct": -1.0,
        "min_confidence": 8,
        "name": "Live Ultra Conservative",
    },
    3: {  # Moderate live
        "max_notional": 200,
        "max_open_positions": 3,
        "daily_loss_halt_pct": -1.5,
        "min_confidence": 7,
        "name": "Live Moderate",
    },
    4: {  # Full live
        "max_notional": 500,
        "max_open_positions": 3,
        "daily_loss_halt_pct": -2.0,
        "min_confidence": 6,
        "name": "Live Full",
    },
}


# ─────────────────────────────────────────────────────────────────
# EquityAutoExecutor
# ─────────────────────────────────────────────────────────────────

class EquityAutoExecutor:
    """
    Equity pipeline orchestrator with cost optimization + phased live.
    """

    asset_class = AssetClass.EQUITY

    def __init__(
        self,
        broker, brain, regime, risk, scheduler_helper,
        data_fetcher, universe,
        sector_map: dict,
        cache_get=None, cache_set=None,
        journal: Optional[EquityJournal] = None,
        auditor=None,  # EquityAuditor
        news_fetcher=None,  # callable: () → sentiment dict
        anomaly_detector=None,  # callable: (md) → anomaly dict
    ):
        self.broker = broker
        self.brain = brain
        self.regime = regime
        self.risk = risk
        self.scheduler_helper = scheduler_helper
        self.data_fetcher = data_fetcher
        self.universe = universe
        self.sector_map = sector_map
        self._cache_get = cache_get
        self._cache_set = cache_set
        self.journal = journal or EquityJournal()
        self.auditor = auditor
        self.news_fetcher = news_fetcher
        self.anomaly_detector = anomaly_detector

        # Master switches
        self.enabled = _env_bool("EQUITY_AUTO_EXECUTE", False)
        self.live_mode = _env_bool("EQUITY_LIVE_MODE", False)
        self.live_confirmed = _env_bool("EQUITY_LIVE_CONFIRMED", False)
        self.live_phase = _env_int("EQUITY_LIVE_PHASE", 0)

        # Two-factor live check
        if self.live_mode and not self.live_confirmed:
            print("[EquityAutoExec] WARNING: LIVE_MODE=true but LIVE_CONFIRMED=false → forcing paper")
            self.live_mode = False

        # Phase profile
        profile = PHASE_PROFILES.get(self.live_phase, PHASE_PROFILES[0])
        self.gates = {
            "MIN_CONFIDENCE": _env_int("EQUITY_MIN_CONFIDENCE", profile["min_confidence"]),
            "MAX_OPEN_POSITIONS": _env_int("EQUITY_MAX_OPEN_POSITIONS", profile["max_open_positions"]),
            "DAILY_LOSS_HALT_PCT": _env_float("EQUITY_DAILY_LOSS_HALT_PCT", profile["daily_loss_halt_pct"]),
            "SYMBOL_COOLDOWN_HOURS": _env_int("EQUITY_SYMBOL_COOLDOWN_HOURS", 4),
            "MAX_NOTIONAL_PER_TRADE": _env_float("EQUITY_MAX_NOTIONAL_PER_TRADE", profile["max_notional"]),
            "MAX_SECTOR_PCT": _env_float("EQUITY_MAX_SECTOR_PCT", 30.0),  # equity %30 (crypto'da %40)
        }

        # Cost optimization (Paket A)
        self.cost_opt = {
            "smart_prefilter_enabled": _env_bool("EQUITY_PREFILTER_ENABLED", True),
            "prefilter_top_n": _env_int("EQUITY_PREFILTER_TOP_N", 10),
            "skip_flat_market": _env_bool("EQUITY_SKIP_FLAT", True),
            "flat_threshold_pct": _env_float("EQUITY_FLAT_THRESHOLD", 0.5),
            "regime_cache_min": _env_int("EQUITY_REGIME_CACHE_MIN", 30),
        }

        # Runtime state
        self.last_run: Optional[dict] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
        self._daily_equity_anchor: Optional[dict] = None
        self._last_order_per_symbol: dict[str, datetime] = {}
        self._scheduler: Optional[BackgroundScheduler] = None
        self._regime_cache: Optional[dict] = None
        self._regime_cache_ts: Optional[datetime] = None

    # ───────────────────────────────────────────────────────────
    # Scheduler
    # ───────────────────────────────────────────────────────────

    def start_scheduler(self) -> dict:
        if not self.enabled:
            return {"started": False, "reason": "EQUITY_AUTO_EXECUTE=false"}
        if self._scheduler and self._scheduler.running:
            return {"started": False, "reason": "Already running"}

        mode, interval_min = self.scheduler_helper.detect_scan_mode()

        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(
            self._scheduled_run,
            trigger=IntervalTrigger(minutes=interval_min),
            id="equity_auto_exec", replace_existing=True,
            next_run_time=_now_utc() + timedelta(seconds=10),
        )
        self._scheduler.start()
        self.next_run = _now_utc() + timedelta(seconds=10)
        return {"started": True, "mode": mode, "interval_min": interval_min}

    def stop_scheduler(self) -> dict:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self.next_run = None
            return {"stopped": True}
        return {"stopped": False, "reason": "Not running"}

    def _scheduled_run(self):
        try:
            self.run_once()
        finally:
            mode, interval_min = self.scheduler_helper.detect_scan_mode()
            self.next_run = _now_utc() + timedelta(minutes=interval_min)

    # ───────────────────────────────────────────────────────────
    # Cost optimization helpers (Paket A)
    # ───────────────────────────────────────────────────────────

    def _smart_prefilter(self, market_data: dict, top_n: int = 10) -> dict:
        """
        Smart pre-filter: top N momentum candidates → brain'e gönder.
        Bear regime'de extended: top 20 (lower momentum dipler).

        Çalışma:
          - SPY/QQQ benchmark'lar HER ZAMAN dahil (regime sinyali için)
          - Mevcut açık pozisyonlar HER ZAMAN dahil (close kararı için)
          - Geri kalan: |change_pct| + vol_ratio bazlı ranking, top N
        """
        if not self.cost_opt["smart_prefilter_enabled"]:
            return market_data

        # Open positions — her zaman dahil
        try:
            open_symbols = {p.get("symbol", "").upper() for p in self._get_portfolio().get("positions", [])}
        except Exception:
            open_symbols = set()

        # Benchmark'lar
        always_include = {"SPY", "QQQ"} | open_symbols

        # Skor ve sırala
        scored = []
        for sym, d in market_data.items():
            if sym.startswith("_") or "error" in d:
                continue
            if sym in always_include:
                continue  # zaten dahil
            change = abs(d.get("change_pct", 0) or 0)
            vol_ratio = d.get("volume_ratio", 0) or 0
            score = change * 2 + (vol_ratio - 1) * 10
            scored.append((sym, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_picks = {s for s, _ in scored[:top_n]}
        keep = always_include | top_picks

        # Filter et
        filtered = {k: v for k, v in market_data.items() if k.startswith("_") or k in keep}
        filtered["_meta"] = market_data.get("_meta", {})
        filtered["_meta"]["prefilter_applied"] = True
        filtered["_meta"]["prefilter_top_n"] = top_n
        filtered["_meta"]["prefilter_kept"] = len(keep)
        return filtered

    def _is_flat_market(self, market_data: dict) -> bool:
        """
        Market flat mı? (Skip brain optimization).
        Top-tier ticker'larda en yüksek mutlak change < threshold ise flat.
        """
        threshold = self.cost_opt["flat_threshold_pct"]
        max_change = 0
        for sym in ("SPY", "QQQ", "AAPL", "MSFT", "NVDA"):
            d = market_data.get(sym, {})
            ch = abs(d.get("change_pct", 0) or 0)
            max_change = max(max_change, ch)
        return max_change < threshold

    def _get_cached_regime(self, market_data: dict) -> dict:
        """30 dakikalık regime cache."""
        ttl_min = self.cost_opt["regime_cache_min"]
        if (self._regime_cache and self._regime_cache_ts
            and (_now_utc() - self._regime_cache_ts).total_seconds() < ttl_min * 60):
            return self._regime_cache
        regime = self.regime.detect(market_data)
        self._regime_cache = regime
        self._regime_cache_ts = _now_utc()
        return regime

    # ───────────────────────────────────────────────────────────
    # MAIN PIPELINE
    # ───────────────────────────────────────────────────────────

    def run_once(self, force: bool = False) -> dict:
        pipeline_run_id = str(uuid.uuid4())[:8]

        result = {
            "timestamp": _isofmt(_now_utc()),
            "pipeline_run_id": pipeline_run_id,
            "force": force,
            "live_mode": self.live_mode,
            "live_phase": self.live_phase,
            "phase_name": PHASE_PROFILES.get(self.live_phase, {}).get("name", "?"),
            "decisions_total": 0,
            "decisions_executed": 0,
            "decisions_blocked": 0,
            "blocked_by_gate": {},
            "errors": [],
            "regime": None,
            "strategy": None,
            "broker_dry_run": getattr(self.broker, "dry_run", True),
            "cost_opt_applied": [],
            "summary": "",
        }

        # 1. Pre-flight
        try:
            account = self.broker.get_account_status()
            equity = account.get("equity", 0)
            self._update_daily_anchor(equity)

            # PDT count (equity-specific)
            try:
                pdt_remaining = max(0, 3 - int(account.get("daytrade_count", 0) or 0))
            except Exception:
                pdt_remaining = 3
            result["pdt_remaining"] = pdt_remaining
        except Exception as e:
            result["errors"].append(f"account fetch: {e}")
            result["summary"] = "Pre-flight failed"
            try: self.journal.log_error(pipeline_run_id, f"account: {e}")
            except: pass
            self.last_run = result
            self.run_count += 1
            return result

        # Daily halt gate
        halt_check = self._check_daily_halt(equity)
        if halt_check["blocked"]:
            result["blocked_by_gate"]["daily_halt"] = halt_check["reason"]
            result["summary"] = f"DAILY HALT: {halt_check['reason']}"
            self.last_run = result
            self.run_count += 1
            return result

        # 2. Trade Close Lifecycle (manual close detect)
        try:
            close_summary = self._check_exits_and_close(pipeline_run_id)
            result["closes_processed"] = close_summary
        except Exception as e:
            result["errors"].append(f"close_lifecycle: {e}")

        # 3. Anomaly Detection
        anomaly_state = {"emergency_halt": False, "anomalies": []}
        if self.anomaly_detector:
            try:
                # First fetch market data (skip prefilter for anomaly check)
                md_full = self.data_fetcher()
                anomaly_state = self.anomaly_detector(md_full)
                result["anomalies"] = anomaly_state
            except Exception as e:
                result["errors"].append(f"anomaly: {e}")

        # 4. Market Data
        try:
            md = anomaly_state.get("_md_full") if anomaly_state.get("_md_full") else self.data_fetcher()
        except Exception as e:
            result["errors"].append(f"data: {e}")
            self.last_run = result
            self.run_count += 1
            return result

        # 5. Cost Opt: Skip flat market
        if self.cost_opt["skip_flat_market"] and self._is_flat_market(md):
            result["cost_opt_applied"].append("skip_flat_market")
            result["summary"] = "Flat market — brain çağrılmadı (cost opt)"
            self.last_run = result
            self.run_count += 1
            return result

        # 6. Regime (cached)
        regime = self._get_cached_regime(md)
        result["regime"] = regime.get("regime")
        if self._regime_cache_ts and (_now_utc() - self._regime_cache_ts).total_seconds() < 60:
            result["cost_opt_applied"].append("regime_cache_hit")

        # 7. Cost Opt: Smart pre-filter (regime-aware top N)
        if self.cost_opt["smart_prefilter_enabled"]:
            top_n = self.cost_opt["prefilter_top_n"]
            if regime.get("regime") in ("bear", "bear_strong"):
                top_n = top_n * 2  # bear'de extended (dipler için)
            md_filtered = self._smart_prefilter(md, top_n=top_n)
            result["cost_opt_applied"].append(f"prefilter_top_{top_n}")
        else:
            md_filtered = md

        # 8. News + Sentiment (opsiyonel)
        sentiment_data = None
        if self.news_fetcher:
            try:
                sentiment_data = self.news_fetcher(list(md_filtered.keys()))
                if sentiment_data:
                    result["news_summary"] = {"tickers_with_news": len(sentiment_data)}
            except Exception as e:
                result["errors"].append(f"news: {e}")

        # 9. Brain
        brain_run_id: Optional[int] = None
        try:
            portfolio = self._get_portfolio()
            brain_out = self.brain.run_brain(
                market_data=md_filtered, portfolio=portfolio,
                regime=regime, recent_trades=[],
                sentiment=sentiment_data, learning_context=None,
            )
            result["strategy"] = brain_out.get("active_strategy")
            decisions = brain_out.get("decisions", [])
            result["decisions_total"] = len(decisions)
            try:
                brain_run_id = self.journal.log_brain_run(
                    pipeline_run_id=pipeline_run_id,
                    regime=regime, strategy=result["strategy"],
                    market_snapshot=md_filtered, decisions=decisions,
                    summary=brain_out.get("market_summary", ""),
                    pdt_remaining=pdt_remaining,
                )
            except Exception as je:
                result["errors"].append(f"journal brain: {je}")
        except Exception as e:
            result["errors"].append(f"brain: {e}")
            result["summary"] = f"Brain error: {e}"
            try: self.journal.log_error(pipeline_run_id, f"brain: {e}")
            except: pass
            self.last_run = result
            self.run_count += 1
            return result

        # 10. Audit (Gemini, tiered)
        audit_results: list[dict] = []
        if self.auditor and getattr(self.auditor, "enabled", False):
            try:
                audit_results = self.auditor.audit_decisions(
                    decisions=decisions, market_data=md_filtered,
                    portfolio=portfolio,
                    regime=regime.get("regime", "unknown"),
                    pdt_remaining=pdt_remaining,
                    market_open=md.get("_meta", {}).get("market_open", False),
                )
                audit_by_ticker = {a["ticker"]: a for a in audit_results}
                for d in decisions:
                    a = audit_by_ticker.get(d.get("ticker"))
                    if a:
                        d["audit"] = a
                        try:
                            self.journal.log_audit(
                                pipeline_run_id=pipeline_run_id,
                                brain_run_id=brain_run_id,
                                symbol=d.get("ticker"),
                                audit_verdict=a.get("audit_verdict", "?"),
                                audit_note=a.get("reasoning", ""),
                            )
                        except: pass
            except Exception as e:
                result["errors"].append(f"audit: {e}")

        # 11+12+13. Per-decision: gates → audit → size → execute
        positions_now = portfolio.get("positions", [])
        pending_executions: list[dict] = []
        audit_rejects = 0

        for d in decisions:
            ticker = d.get("ticker", "?")
            action = (d.get("action") or "").lower()

            if action not in ("long", "short", "close_long", "close_short", "reduce"):
                continue

            # Anomaly halt gate
            if anomaly_state.get("emergency_halt") and action in ("long", "short"):
                halt_reason = anomaly_state.get("summary", "Anomaly emergency halt")
                result["blocked_by_gate"][ticker] = halt_reason
                result["decisions_blocked"] += 1
                try:
                    self.journal.log_gate_block(
                        pipeline_run_id=pipeline_run_id, brain_run_id=brain_run_id,
                        symbol=ticker, action=action,
                        confidence=int(d.get("confidence", 0)),
                        blocked_reason=halt_reason,
                        sector=d.get("sector") or self.sector_map.get(ticker, "Unknown"),
                    )
                except: pass
                continue

            # Audit REJECT gate
            audit = d.get("audit")
            if audit and audit.get("audit_verdict") == "REJECT":
                reject_reason = audit.get("reasoning", "Gemini audit rejected")
                flags = ", ".join(audit.get("risk_flags", []))
                full_reason = f"Gemini REJECT: {reject_reason} [{flags}]"
                result["blocked_by_gate"][ticker] = full_reason
                result["decisions_blocked"] += 1
                audit_rejects += 1
                try:
                    self.journal.log_gate_block(
                        pipeline_run_id=pipeline_run_id, brain_run_id=brain_run_id,
                        symbol=ticker, action=action,
                        confidence=int(d.get("confidence", 0)),
                        blocked_reason=full_reason,
                        sector=d.get("sector") or self.sector_map.get(ticker, "Unknown"),
                    )
                except: pass
                continue

            # Audit MODIFY override
            if audit and audit.get("audit_verdict") == "MODIFY":
                mods = audit.get("modified_params", {})
                if "stop_loss" in mods: d["stop_loss"] = mods["stop_loss"]
                if "take_profit" in mods: d["take_profit"] = mods["take_profit"]
                if "position_size_pct" in mods: d["position_size_pct"] = mods["position_size_pct"]

            # Safety gates (incl. PDT)
            gate_block = self._check_decision_gates(
                d, positions_now, pending_executions, equity, pdt_remaining,
            )
            if gate_block:
                result["blocked_by_gate"][ticker] = gate_block
                result["decisions_blocked"] += 1
                try:
                    self.journal.log_gate_block(
                        pipeline_run_id=pipeline_run_id, brain_run_id=brain_run_id,
                        symbol=ticker, action=action,
                        confidence=int(d.get("confidence", 0)),
                        blocked_reason=gate_block,
                        sector=d.get("sector") or self.sector_map.get(ticker, "Unknown"),
                    )
                except: pass
                continue

            # Position sizing
            try:
                entry = self._parse_price(d.get("entry_zone")) or md.get(ticker, {}).get("price", 0)
                stop = self._parse_price(d.get("stop_loss"))
                if entry > 0 and stop and stop > 0:
                    sizing = self.risk.dynamic_position_size(
                        equity=equity, entry_price=entry, stop_loss_price=stop,
                        confidence=int(d.get("confidence", 5)),
                        regime=regime.get("regime", "neutral"),
                    )
                else:
                    sizing = {"qty": 0, "error": "invalid entry/stop"}
            except Exception as e:
                result["errors"].append(f"sizing {ticker}: {e}")
                continue

            # Notional cap (phase-dependent)
            notional = sizing.get("position_value") or 0
            if notional > self.gates["MAX_NOTIONAL_PER_TRADE"]:
                cap = self.gates["MAX_NOTIONAL_PER_TRADE"]
                sizing["qty"] = max(1, int(cap / entry)) if entry > 0 else 0
                sizing["position_value"] = sizing["qty"] * entry
                sizing["notional_capped"] = True

            # Execute (broker'da dry_run kontrolü)
            try:
                exec_result = self.broker.execute(
                    action=action, ticker=ticker,
                    qty=sizing.get("qty", 0), price=entry,
                    stop_loss=stop,
                    take_profit=self._parse_price(d.get("take_profit")),
                    order_type="market",
                )
                d["execution"] = exec_result
                d["sizing"] = sizing

                exec_status = (exec_result.get("status") or "").lower()
                rejected_statuses = ("error", "rejected", "canceled", "expired", "rejected_new")
                if exec_status not in rejected_statuses:
                    result["decisions_executed"] += 1
                    self._last_order_per_symbol[ticker] = _now_utc()
                    pending_executions.append({
                        "symbol": ticker,
                        "market_value": sizing.get("position_value", 0),
                        "sector": d.get("sector") or self.sector_map.get(ticker, "Unknown"),
                        "qty": sizing.get("qty", 0),
                        "_pending": True,
                    })
                    # Journal
                    try:
                        self.journal.log_trade_open(
                            pipeline_run_id=pipeline_run_id,
                            brain_run_id=brain_run_id,
                            symbol=ticker, action=action,
                            qty=sizing.get("qty", 0),
                            entry_price=entry, stop_loss=stop,
                            take_profit=self._parse_price(d.get("take_profit")),
                            confidence=int(d.get("confidence", 0)),
                            sector=d.get("sector") or self.sector_map.get(ticker, "Unknown"),
                            strategy=d.get("strategy"),
                            regime=regime.get("regime"),
                            execution_status=exec_status,
                            reasoning=d.get("reasoning", ""),
                            is_bracket=bool(stop and d.get("take_profit")),
                            live_mode=self.live_mode,
                            live_phase=self.live_phase,
                        )
                    except Exception as je:
                        result["errors"].append(f"journal trade_open {ticker}: {je}")
                else:
                    result["decisions_blocked"] += 1
                    result["blocked_by_gate"][ticker] = (
                        f"broker rejected: {exec_result.get('reason', 'unknown')}"
                    )
            except Exception as e:
                result["errors"].append(f"execute {ticker}: {e}")

        # Audit summary
        audit_summary = ""
        if audit_results:
            approved = sum(1 for a in audit_results if a.get("audit_verdict") == "APPROVE")
            modified = sum(1 for a in audit_results if a.get("audit_verdict") == "MODIFY")
            skipped = sum(1 for a in audit_results if a.get("audit_skipped"))
            audit_summary = (
                f" Audit: {approved}✓ {audit_rejects}✗ {modified}~ ({skipped} skipped)."
            )
            result["audit"] = {
                "total": len(audit_results),
                "approved": approved, "rejected": audit_rejects,
                "modified": modified, "skipped": skipped,
                "results": audit_results,
            }

        # Final summary
        result["summary"] = (
            f"[Phase {self.live_phase}/{PHASE_PROFILES.get(self.live_phase,{}).get('name','?')}] "
            f"{result['decisions_total']} kararın "
            f"{result['decisions_executed']}'i execute, "
            f"{result['decisions_blocked']}'i bloke. "
            f"Strategy: {result['strategy']}, Regime: {result['regime']}, "
            f"PDT: {pdt_remaining}/3.{audit_summary}"
        )
        result["decisions"] = [
            {
                "ticker": d.get("ticker"),
                "action": d.get("action"),
                "confidence": d.get("confidence"),
                "executed": "execution" in d,
                "execution_status": d.get("execution", {}).get("status"),
                "sizing_qty": d.get("sizing", {}).get("qty"),
                "sizing_value": d.get("sizing", {}).get("position_value"),
            }
            for d in decisions
        ]

        self.last_run = result
        self.run_count += 1
        return result

    # ───────────────────────────────────────────────────────────
    # Safety gates
    # ───────────────────────────────────────────────────────────

    def _update_daily_anchor(self, equity: float):
        today = _now_utc().date().isoformat()
        if not self._daily_equity_anchor or self._daily_equity_anchor.get("date") != today:
            self._daily_equity_anchor = {"date": today, "equity": equity}

    def _check_daily_halt(self, equity: float) -> dict:
        if not self._daily_equity_anchor:
            return {"blocked": False}
        anchor = self._daily_equity_anchor.get("equity", 0)
        if anchor <= 0:
            return {"blocked": False}
        change_pct = (equity - anchor) / anchor * 100
        if change_pct <= self.gates["DAILY_LOSS_HALT_PCT"]:
            return {
                "blocked": True,
                "reason": f"Günlük kayıp %{change_pct:.2f}, halt eşiği %{self.gates['DAILY_LOSS_HALT_PCT']}",
                "current_pct": round(change_pct, 2),
            }
        return {"blocked": False, "current_pct": round(change_pct, 2)}

    def _check_decision_gates(
        self, decision: dict, positions: list,
        pending_executions: list, equity: float,
        pdt_remaining: int,
    ) -> Optional[str]:
        """Equity gates — crypto + PDT eklenmiş."""
        ticker = decision.get("ticker", "?")
        action = (decision.get("action") or "").lower()
        confidence = int(decision.get("confidence", 0))

        all_held = list(positions) + list(pending_executions)

        # Gate 1: Min confidence
        if confidence < self.gates["MIN_CONFIDENCE"]:
            return f"confidence {confidence} < {self.gates['MIN_CONFIDENCE']}"

        # Gate 2 (EQUITY-SPECIFIC): PDT — 0 day trade kaldıysa same-day close blokla
        # Gerçek hayatta bu daha karmaşık; basit version: PDT=0 ise yeni long/short açma
        if action in ("long", "short") and pdt_remaining <= 0:
            return f"PDT day trade quota exhausted (0/3)"

        # Gate 3: Max open positions
        if action in ("long", "short"):
            distinct_symbols = {p.get("symbol") for p in all_held if p.get("symbol") != ticker}
            existing_count = len(distinct_symbols)
            if existing_count >= self.gates["MAX_OPEN_POSITIONS"]:
                return f"max positions reached ({existing_count}/{self.gates['MAX_OPEN_POSITIONS']})"

        # Gate 4: Cooldown
        last = self._last_order_per_symbol.get(ticker)
        if last:
            elapsed_h = (_now_utc() - last).total_seconds() / 3600
            if elapsed_h < self.gates["SYMBOL_COOLDOWN_HOURS"]:
                remaining = self.gates["SYMBOL_COOLDOWN_HOURS"] - elapsed_h
                return f"cooldown {remaining:.1f}h kaldı"

        # Gate 5: Sector concentration
        if action in ("long", "short") and equity > 0:
            sector = decision.get("sector") or self.sector_map.get(ticker, "Unknown")
            current_sector_value = sum(
                p.get("market_value", 0) for p in all_held
                if (p.get("sector") or self.sector_map.get(p.get("symbol", ""), "Unknown")) == sector
            )
            current_sector_pct = current_sector_value / equity * 100
            if current_sector_pct >= self.gates["MAX_SECTOR_PCT"]:
                return (
                    f"sector {sector} %{current_sector_pct:.1f} "
                    f"≥ %{self.gates['MAX_SECTOR_PCT']} cap"
                )

        return None

    # ───────────────────────────────────────────────────────────
    # Trade close lifecycle (manual close detect)
    # ───────────────────────────────────────────────────────────

    def _check_exits_and_close(self, pipeline_run_id: str) -> dict:
        """Manual close detect (Alpaca'da bracket order zaten stop/TP hallediyor)."""
        summary = {"manual_close": 0, "errors": 0}
        try:
            open_trades = self.journal.get_open_trades()
        except Exception:
            return summary
        if not open_trades:
            return summary

        # Alpaca açık pozisyonlar
        try:
            alpaca_positions = self.broker.client.get_all_positions()
            alpaca_symbols = {p.symbol.upper() for p in alpaca_positions}
        except Exception:
            return summary

        for trade in open_trades:
            symbol = (trade.get("symbol") or "").upper()
            if not symbol or symbol in alpaca_symbols:
                continue
            # Pozisyon kayıp = bracket'tan kapandı ya da manuel
            entry_price = trade.get("entry_price", 0)
            qty = trade.get("qty", 0)
            # Exit price'ı bilmiyoruz (Alpaca order history check edilebilir, basit hâl: skip)
            try:
                self.journal.log_trade_close(
                    trade_open_id=trade.get("id"),
                    symbol=symbol,
                    entry_price=entry_price,
                    exit_price=entry_price,  # placeholder, gerçeği için Alpaca activities API
                    qty=qty,
                    exit_reason="bracket_or_manual",
                    live_mode=self.live_mode,
                )
                summary["manual_close"] += 1
            except Exception:
                summary["errors"] += 1

        return summary

    # ───────────────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────────────

    def _get_portfolio(self) -> dict:
        try:
            account = self.broker.get_account_status()
            positions_raw = self.broker.client.get_all_positions()
            positions = [
                {
                    "ticker": p.symbol,
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry_price": float(p.avg_entry_price),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price) if p.current_price else None,
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "sector": self.sector_map.get(p.symbol, "Unknown"),
                }
                for p in positions_raw
                if not p.asset_class or "us_equity" in str(p.asset_class).lower()
            ]
            return {
                "cash": account.get("cash", 0),
                "equity": account.get("equity", 0),
                "positions": positions,
            }
        except Exception:
            return {"cash": 0, "equity": 0, "positions": []}

    @staticmethod
    def _parse_price(s) -> Optional[float]:
        if s is None: return None
        if isinstance(s, (int, float)): return float(s)
        try:
            txt = str(s).replace("$", "").replace(",", "").strip()
            if "-" in txt:
                parts = txt.split("-")
                return (float(parts[0]) + float(parts[1])) / 2
            return float(txt)
        except Exception:
            return None

    # ───────────────────────────────────────────────────────────
    # Status
    # ───────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "asset_class": "equity",
            "auto_execute_enabled": self.enabled,
            "scheduler_running": bool(self._scheduler and self._scheduler.running),
            "broker_dry_run": getattr(self.broker, "dry_run", True),
            "broker_paper": getattr(self.broker, "paper", True),
            "live_mode": self.live_mode,
            "live_confirmed": self.live_confirmed,
            "live_phase": self.live_phase,
            "phase_profile": PHASE_PROFILES.get(self.live_phase, {}),
            "run_count": self.run_count,
            "last_run": self.last_run,
            "next_run": _isofmt(self.next_run),
            "gates": self.gates,
            "cost_optimization": self.cost_opt,
            "daily_anchor": self._daily_equity_anchor,
            "cooldowns": {
                t: _isofmt(dt) for t, dt in self._last_order_per_symbol.items()
            },
        }
