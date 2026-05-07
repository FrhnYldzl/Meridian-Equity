"""
equity/journal.py — V6.0-α: Equity trade journal (seyir defteri).

Auto-executor'ın her aşamasını SQLite'a kaydeder + Railway Volume support.

Equity-specific:
  - sector field
  - PDT day_trades_remaining tracking
  - Bracket order tracking (Alpaca equity'de native)

Mevcut equity'nin trade_journal.py ve trade_journal_v2.py'si DOKUNULMAZ.
Bu V6.0 için yeni, modern journal — V5.7 trade_journal'ından MIGRATION
sonra çalışmaya başlar (V6.0-θ aşamasında).

Volume mount: /app/data/equity_journal.db (Railway Volume gerekli)
Lokal fallback: server/equity_journal.db
"""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path() -> str:
    """
    DB yolunu çöz:
      1. EQUITY_JOURNAL_DB_PATH env (Railway override)
      2. /app/data/equity_journal.db (Volume mount)
      3. server/equity_journal.db (lokal fallback)
    """
    env_path = os.getenv("EQUITY_JOURNAL_DB_PATH")
    if env_path:
        return env_path
    railway_volume = Path("/app/data")
    if railway_volume.is_dir() or railway_volume.parent.is_dir():
        try:
            railway_volume.mkdir(parents=True, exist_ok=True)
            return str(railway_volume / "equity_journal.db")
        except Exception:
            pass
    return str(Path(__file__).parent.parent / "equity_journal.db")


# ─────────────────────────────────────────────────────────────────
# Schema — equity event log + PDT + bracket + live phase tracking
# ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    asset_class     TEXT NOT NULL DEFAULT 'equity',
    symbol          TEXT,
    -- Brain context
    regime          TEXT,
    strategy        TEXT,
    confidence      INTEGER,
    sector          TEXT,                    -- equity-specific (vs asset_group)
    -- Trade
    action          TEXT,
    qty             REAL,
    entry_price     REAL,
    stop_loss       REAL,
    take_profit     REAL,
    exit_price      REAL,
    pnl_dollar      REAL,
    pnl_pct         REAL,
    hold_minutes    INTEGER,
    -- Equity-specific
    pdt_remaining   INTEGER,                  -- PDT day trade count remaining
    is_bracket      INTEGER DEFAULT 0,        -- bracket order mu?
    is_overnight    INTEGER DEFAULT 0,        -- overnight pozisyon mu?
    -- References
    brain_run_id    INTEGER,
    trade_open_id   INTEGER,
    -- Audit
    audit_verdict   TEXT,
    audit_note      TEXT,
    -- Pipeline
    pipeline_run_id TEXT,
    blocked_reason  TEXT,
    error_message   TEXT,
    -- Live trading metadata
    live_mode       INTEGER DEFAULT 0,        -- live para mı? (0=paper, 1=live)
    live_phase      INTEGER,                  -- Faz 1/2/3/4 (sınırlı→full)
    -- Snapshots (JSON)
    market_snapshot TEXT,
    decisions_json  TEXT,
    metadata_json   TEXT,
    summary         TEXT
);

CREATE INDEX IF NOT EXISTS idx_journal_eq_ts ON journal(timestamp);
CREATE INDEX IF NOT EXISTS idx_journal_eq_event ON journal(event_type);
CREATE INDEX IF NOT EXISTS idx_journal_eq_symbol ON journal(symbol);
CREATE INDEX IF NOT EXISTS idx_journal_eq_run ON journal(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_journal_eq_live ON journal(live_mode);
"""


# ─────────────────────────────────────────────────────────────────
# EquityJournal class
# ─────────────────────────────────────────────────────────────────

class EquityJournal:
    """SQLite-backed equity trade journal."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = _resolve_db_path()
        else:
            p = Path(db_path)
            if not p.is_absolute():
                p = Path(__file__).parent.parent / db_path
            self.db_path = str(p)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self):
        with self._conn() as c:
            c.executescript(SCHEMA)

    # ───────────────────────────────────────────────────────
    # Logging API
    # ───────────────────────────────────────────────────────

    def _insert(self, **kwargs) -> int:
        kwargs.setdefault("timestamp", _now_iso())
        kwargs.setdefault("asset_class", "equity")
        cols = list(kwargs.keys())
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT INTO journal ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn() as c:
            cur = c.execute(sql, [kwargs[k] for k in cols])
            return cur.lastrowid

    def log_brain_run(
        self, pipeline_run_id: str, regime: dict, strategy: str,
        market_snapshot: dict, decisions: list, summary: str = "",
        pdt_remaining: int = None,
    ) -> int:
        compact_snapshot = {
            sym: {
                "price": d.get("price"),
                "change_pct": d.get("change_pct"),
                "rsi14": d.get("rsi14"),
                "atr_pct": d.get("atr_pct"),
                "trend": d.get("trend"),
                "momentum_score": d.get("momentum_score"),
                "volume_ratio": d.get("volume_ratio"),
                "macd_cross": d.get("macd_cross"),
            }
            for sym, d in (market_snapshot or {}).items()
            if not sym.startswith("_") and "error" not in d
        }
        return self._insert(
            event_type="brain_run",
            pipeline_run_id=pipeline_run_id,
            regime=regime.get("regime") if isinstance(regime, dict) else regime,
            strategy=strategy,
            market_snapshot=json.dumps(compact_snapshot),
            decisions_json=json.dumps(decisions or []),
            summary=summary,
            pdt_remaining=pdt_remaining,
        )

    def log_trade_open(
        self, pipeline_run_id: str, brain_run_id: Optional[int],
        symbol: str, action: str, qty: float, entry_price: float,
        stop_loss: float = None, take_profit: float = None,
        confidence: int = None, sector: str = None,
        strategy: str = None, regime: str = None,
        execution_status: str = "submitted",
        reasoning: str = "",
        is_bracket: bool = False,
        live_mode: bool = False, live_phase: int = None,
    ) -> int:
        return self._insert(
            event_type="trade_open",
            pipeline_run_id=pipeline_run_id,
            brain_run_id=brain_run_id,
            symbol=symbol, action=action,
            qty=qty, entry_price=entry_price,
            stop_loss=stop_loss, take_profit=take_profit,
            confidence=confidence, sector=sector,
            strategy=strategy, regime=regime,
            is_bracket=1 if is_bracket else 0,
            live_mode=1 if live_mode else 0,
            live_phase=live_phase,
            metadata_json=json.dumps({
                "execution_status": execution_status,
                "reasoning": reasoning,
            }),
        )

    def log_trade_close(
        self, trade_open_id: int, symbol: str,
        entry_price: float, exit_price: float, qty: float,
        exit_reason: str = "manual", hold_minutes: int = None,
        live_mode: bool = False,
    ) -> int:
        pnl_dollar = (exit_price - entry_price) * qty
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        return self._insert(
            event_type="trade_close",
            trade_open_id=trade_open_id,
            symbol=symbol,
            entry_price=entry_price, exit_price=exit_price, qty=qty,
            pnl_dollar=round(pnl_dollar, 2), pnl_pct=round(pnl_pct, 2),
            hold_minutes=hold_minutes,
            live_mode=1 if live_mode else 0,
            metadata_json=json.dumps({"exit_reason": exit_reason}),
        )

    def log_gate_block(
        self, pipeline_run_id: str, brain_run_id: Optional[int],
        symbol: str, action: str, confidence: int,
        blocked_reason: str, sector: str = None,
    ) -> int:
        return self._insert(
            event_type="gate_block",
            pipeline_run_id=pipeline_run_id, brain_run_id=brain_run_id,
            symbol=symbol, action=action, confidence=confidence,
            blocked_reason=blocked_reason, sector=sector,
        )

    def log_audit(
        self, pipeline_run_id: str, brain_run_id: Optional[int],
        symbol: str, audit_verdict: str, audit_note: str = "",
    ) -> int:
        return self._insert(
            event_type="audit",
            pipeline_run_id=pipeline_run_id, brain_run_id=brain_run_id,
            symbol=symbol,
            audit_verdict=audit_verdict, audit_note=audit_note,
        )

    def log_error(
        self, pipeline_run_id: str, error_message: str,
        symbol: str = None,
    ) -> int:
        return self._insert(
            event_type="error",
            pipeline_run_id=pipeline_run_id,
            symbol=symbol, error_message=error_message,
        )

    def log_live_phase_change(self, from_phase: int, to_phase: int, reason: str = ""):
        """Live trading faz değişimini kaydet (audit trail için)."""
        return self._insert(
            event_type="live_phase_change",
            metadata_json=json.dumps({
                "from_phase": from_phase, "to_phase": to_phase,
                "reason": reason,
            }),
            summary=f"Live phase {from_phase} → {to_phase}: {reason}",
        )

    # ───────────────────────────────────────────────────────
    # Query helpers
    # ───────────────────────────────────────────────────────

    def get_recent(self, limit: int = 100, event_type: str = None,
                   symbol: str = None, live_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM journal WHERE 1=1"
        params: list = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if live_only:
            sql += " AND live_mode = 1"
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_by_pipeline_run(self, pipeline_run_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM journal WHERE pipeline_run_id = ? ORDER BY id",
                [pipeline_run_id],
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_open_trades(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM journal
                WHERE event_type = 'trade_open'
                  AND id NOT IN (
                    SELECT trade_open_id FROM journal
                    WHERE event_type = 'trade_close' AND trade_open_id IS NOT NULL
                  )
                ORDER BY id DESC
            """).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_performance(self, days: int = 30, live_only: bool = False) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as c:
            base_filter = "WHERE event_type = 'trade_close' AND timestamp > ?"
            if live_only:
                base_filter += " AND live_mode = 1"
            closed = c.execute(
                f"SELECT pnl_dollar, pnl_pct, hold_minutes, symbol, sector "
                f"FROM journal {base_filter}",
                [cutoff],
            ).fetchall()
            closed = [dict(r) for r in closed]

            brain_count = c.execute(
                "SELECT COUNT(*) FROM journal WHERE event_type='brain_run' AND timestamp>?",
                [cutoff],
            ).fetchone()[0]
            block_count = c.execute(
                "SELECT COUNT(*) FROM journal WHERE event_type='gate_block' AND timestamp>?",
                [cutoff],
            ).fetchone()[0]
            err_count = c.execute(
                "SELECT COUNT(*) FROM journal WHERE event_type='error' AND timestamp>?",
                [cutoff],
            ).fetchone()[0]

        wins = [t for t in closed if (t.get("pnl_dollar") or 0) > 0]
        losses = [t for t in closed if (t.get("pnl_dollar") or 0) < 0]
        total_pnl = sum((t.get("pnl_dollar") or 0) for t in closed)
        win_rate = (len(wins) / len(closed) * 100) if closed else 0
        avg_winner = (sum(t["pnl_dollar"] for t in wins) / len(wins)) if wins else 0
        avg_loser = (sum(t["pnl_dollar"] for t in losses) / len(losses)) if losses else 0
        avg_hold = (sum((t.get("hold_minutes") or 0) for t in closed) / len(closed)) if closed else 0

        # Sector breakdown
        sector_stats: dict = {}
        for t in closed:
            sec = t.get("sector") or "Unknown"
            s = sector_stats.setdefault(sec, {"trades": 0, "pnl": 0, "wins": 0})
            s["trades"] += 1
            s["pnl"] += (t.get("pnl_dollar") or 0)
            if (t.get("pnl_dollar") or 0) > 0:
                s["wins"] += 1

        return {
            "period_days": days,
            "live_only": live_only,
            "brain_runs": brain_count,
            "gate_blocks": block_count,
            "errors": err_count,
            "trades_closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "total_pnl_dollar": round(total_pnl, 2),
            "avg_winner_dollar": round(avg_winner, 2),
            "avg_loser_dollar": round(avg_loser, 2),
            "avg_hold_minutes": round(avg_hold, 0),
            "sector_breakdown": {
                k: {**v, "win_rate_pct": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0}
                for k, v in sector_stats.items()
            },
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        for json_col in ("market_snapshot", "decisions_json", "metadata_json"):
            if d.get(json_col):
                try:
                    d[json_col] = json.loads(d[json_col])
                except Exception:
                    pass
        return d
