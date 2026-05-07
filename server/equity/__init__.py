"""
equity/ — Equity asset class implementation.

V5.8: Adapter pattern (V5.7 modüllerini sarmalar).
V6.0: Full implementation alongside adapters — auto_executor, journal, audit.

V5.7 modülleri (main.py, claude_brain.py, regime_detector.py, risk_manager.py,
scheduler.py, gemini_auditor.py, news_sentiment.py, anomaly_detector.py,
trade_journal.py, broker/equity.py) HÂLÂ TEK SATIR DEĞİŞMEDİ. V6.0 paralel
yaşar, migration sonrasında V5.7 legacy hâle gelir.
"""

# V5.8 adapters (legacy, hâlâ kullanılabilir)
from equity.broker_adapter import EquityBrokerAdapter
from equity.risk_adapter import EquityRiskAdapter
from equity.brain_adapter import EquityBrainAdapter
from equity.regime_adapter import EquityRegimeAdapter
from equity.scheduler_adapter import EquitySchedulerAdapter

# V6.0 full implementations
from equity.journal import EquityJournal
from equity.audit_impl import EquityAuditor
from equity.auto_executor import EquityAutoExecutor, PHASE_PROFILES
from equity.brain_impl import EquityBrain, EQUITY_SYSTEM_PROMPT, DEFAULT_MODEL as EQUITY_BRAIN_DEFAULT_MODEL
from equity import pro_panels

__all__ = [
    # V5.8 adapters
    "EquityBrokerAdapter",
    "EquityRiskAdapter",
    "EquityBrainAdapter",
    "EquityRegimeAdapter",
    "EquitySchedulerAdapter",
    # V6.0 full implementations
    "EquityJournal",
    "EquityAuditor",
    "EquityAutoExecutor",
    "PHASE_PROFILES",
    "EquityBrain",
    "EQUITY_SYSTEM_PROMPT",
    "EQUITY_BRAIN_DEFAULT_MODEL",
    "pro_panels",
]
