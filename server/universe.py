"""
universe.py — Broad Scan Universe Loader

NASDAQ 100 + Core WATCHLIST + S&P 500 leaders + Crypto-related stocks.
Toplam ~180 sembol, hepsi sektör mapping'li.

Kullanım:
    from universe import get_broad_universe, EXTENDED_SECTOR_MAP
    tickers = get_broad_universe()

Hata durumunda: Core WATCHLIST fallback (asla boş dönmez).
"""

from typing import List


# ─────────────────────────────────────────────────────────────────
# NASDAQ 100 (2024 sonu itibarıyla güncel, ~100 sembol)
# ─────────────────────────────────────────────────────────────────

NASDAQ_100: List[str] = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
    "AVGO", "COST", "NFLX", "ASML", "AMD", "ADBE", "PEP", "CSCO",
    "TMUS", "LIN", "INTU", "TXN", "QCOM", "ISRG", "AMAT", "BKNG",
    "HON", "AMGN", "PANW", "SBUX", "ADI", "GILD", "LRCX", "MDLZ",
    "REGN", "VRTX", "KLAC", "CMCSA", "ADP", "MU", "SNPS", "INTC",
    "CDNS", "ABNB", "PYPL", "CRWD", "MAR", "ORLY", "MELI", "CTAS",
    "FTNT", "MRVL", "CSX", "PCAR", "ROP", "MNST", "WDAY", "KDP",
    "NXPI", "CHTR", "CPRT", "ADSK", "PAYX", "FANG", "KHC", "AEP",
    "EXC", "ROST", "DASH", "BKR", "IDXX", "CCEP", "FAST", "ODFL",
    "AZN", "TTD", "LULU", "GEHC", "CTSH", "EA", "DDOG", "DXCM",
    "VRSK", "MCHP", "BIIB", "ANSS", "CSGP", "CDW", "ZS", "TEAM",
    "ON", "WBD", "XEL", "ILMN", "GFS", "MDB", "TTWO", "SMCI",
    "PDD", "ARM", "APP", "PLTR", "MSTR",
]


# ─────────────────────────────────────────────────────────────────
# S&P 500 ek leaders (NDX'te olmayan büyük caps — bank, pharma, retail, energy)
# ─────────────────────────────────────────────────────────────────

SP500_EXTRAS: List[str] = [
    # Financial (banks, payments, insurance)
    "JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "TFC", "SCHW",
    "V", "MA", "AXP", "BLK", "BX", "KKR", "SPGI", "MCO", "ICE", "CME",
    "BRK.B", "MET", "PRU", "AIG", "CB", "PGR",

    # Healthcare (pharma, medical devices, insurance)
    "JNJ", "UNH", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "CVS", "ELV", "CI", "HUM", "ZTS", "SYK", "BSX", "MDT", "MCK",

    # Consumer Defensive
    "WMT", "PG", "KO", "PEP", "PM", "MO", "CL", "GIS", "K", "HSY",
    "TGT", "COST",

    # Consumer Cyclical
    "HD", "NKE", "MCD", "LOW", "TJX", "DIS", "ULTA", "DG", "DLTR",

    # Industrial / Aerospace / Defense
    "BA", "CAT", "GE", "RTX", "LMT", "NOC", "GD", "DE", "MMM", "EMR",
    "ETN", "ITW", "PH", "UPS", "FDX", "UNP", "NSC",

    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "VLO", "WMB",
    "KMI", "OKE", "PXD",

    # Utilities (defensive)
    "NEE", "DUK", "SO", "D", "AEP",

    # Real Estate
    "AMT", "PLD", "EQIX", "WELL", "DLR", "PSA", "O", "SPG",

    # Communication Services
    "VZ", "T", "DIS", "NFLX", "CMCSA", "CHTR",

    # Materials
    "LIN", "APD", "SHW", "FCX", "NEM",

    # Crypto-related equities (önemli — equity ama crypto exposure)
    "COIN", "MARA", "RIOT", "MSTR", "CLSK", "HUT", "WULF", "BITF", "HOOD",

    # Popular ETFs
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "XLF", "XLE", "XLK",
    "XLV", "XLI", "XLY", "XLP", "GLD", "SLV", "TLT", "HYG", "VXX", "TQQQ",
    "SQQQ", "USO", "UVXY",
]


# ─────────────────────────────────────────────────────────────────
# Genişletilmiş sektör mapping (NASDAQ-100 + SP500 leaders + ETFs)
# ─────────────────────────────────────────────────────────────────

EXTENDED_SECTOR_MAP: dict[str, str] = {
    # ═══ Technology ═══
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "GOOGL": "Technology", "GOOG": "Technology", "META": "Technology",
    "AMD": "Technology", "AVGO": "Technology", "ADBE": "Technology",
    "CRM": "Technology", "ORCL": "Technology", "CSCO": "Technology",
    "INTC": "Technology", "QCOM": "Technology", "TXN": "Technology",
    "AMAT": "Technology", "MU": "Technology", "INTU": "Technology",
    "NOW": "Technology", "PANW": "Technology", "FTNT": "Technology",
    "CRWD": "Technology", "ZS": "Technology", "SNPS": "Technology",
    "CDNS": "Technology", "ANSS": "Technology", "WDAY": "Technology",
    "ADSK": "Technology", "ADI": "Technology", "LRCX": "Technology",
    "KLAC": "Technology", "MRVL": "Technology", "MCHP": "Technology",
    "ON": "Technology", "GFS": "Technology", "ARM": "Technology",
    "ASML": "Technology", "NXPI": "Technology", "SMCI": "Technology",
    "DDOG": "Technology", "TEAM": "Technology", "MDB": "Technology",
    "PLTR": "Technology", "APP": "Technology", "CTSH": "Technology",
    "CDW": "Technology", "CSGP": "Technology", "VRSK": "Technology",
    "TTD": "Technology",

    # ═══ Consumer Cyclical ═══
    "AMZN": "Consumer Cyclical", "TSLA": "Consumer Cyclical",
    "HD": "Consumer Cyclical", "NKE": "Consumer Cyclical",
    "MCD": "Consumer Cyclical", "SBUX": "Consumer Cyclical",
    "BKNG": "Consumer Cyclical", "ABNB": "Consumer Cyclical",
    "MAR": "Consumer Cyclical", "LULU": "Consumer Cyclical",
    "ROST": "Consumer Cyclical", "ORLY": "Consumer Cyclical",
    "LOW": "Consumer Cyclical", "TJX": "Consumer Cyclical",
    "ULTA": "Consumer Cyclical", "DG": "Consumer Cyclical",
    "DLTR": "Consumer Cyclical", "MELI": "Consumer Cyclical",
    "PDD": "Consumer Cyclical", "DASH": "Consumer Cyclical",

    # ═══ Consumer Defensive ═══
    "WMT": "Consumer Defensive", "PG": "Consumer Defensive",
    "KO": "Consumer Defensive", "PEP": "Consumer Defensive",
    "PM": "Consumer Defensive", "MO": "Consumer Defensive",
    "CL": "Consumer Defensive", "GIS": "Consumer Defensive",
    "K": "Consumer Defensive", "HSY": "Consumer Defensive",
    "MDLZ": "Consumer Defensive", "MNST": "Consumer Defensive",
    "KDP": "Consumer Defensive", "KHC": "Consumer Defensive",
    "COST": "Consumer Defensive", "TGT": "Consumer Defensive",
    "CCEP": "Consumer Defensive",

    # ═══ Communication ═══
    "NFLX": "Communication", "DIS": "Communication", "TMUS": "Communication",
    "CMCSA": "Communication", "CHTR": "Communication", "VZ": "Communication",
    "T": "Communication", "WBD": "Communication", "EA": "Communication",
    "TTWO": "Communication",

    # ═══ Financial ═══
    "JPM": "Financial", "BAC": "Financial", "WFC": "Financial",
    "GS": "Financial", "MS": "Financial", "C": "Financial",
    "USB": "Financial", "PNC": "Financial", "TFC": "Financial",
    "SCHW": "Financial", "V": "Financial", "MA": "Financial",
    "AXP": "Financial", "BLK": "Financial", "BX": "Financial",
    "KKR": "Financial", "SPGI": "Financial", "MCO": "Financial",
    "ICE": "Financial", "CME": "Financial", "BRK.B": "Financial",
    "MET": "Financial", "PRU": "Financial", "AIG": "Financial",
    "CB": "Financial", "PGR": "Financial", "PYPL": "Financial",
    "PAYX": "Financial", "ADP": "Financial",
    # Crypto-related equities (financial under sector for risk grouping)
    "COIN": "Financial", "MARA": "Financial", "RIOT": "Financial",
    "MSTR": "Financial", "CLSK": "Financial", "HUT": "Financial",
    "WULF": "Financial", "BITF": "Financial", "HOOD": "Financial",

    # ═══ Healthcare ═══
    "JNJ": "Healthcare", "UNH": "Healthcare", "LLY": "Healthcare",
    "PFE": "Healthcare", "ABBV": "Healthcare", "MRK": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare", "DHR": "Healthcare",
    "BMY": "Healthcare", "AMGN": "Healthcare", "CVS": "Healthcare",
    "ELV": "Healthcare", "CI": "Healthcare", "HUM": "Healthcare",
    "ZTS": "Healthcare", "SYK": "Healthcare", "BSX": "Healthcare",
    "MDT": "Healthcare", "MCK": "Healthcare", "GILD": "Healthcare",
    "REGN": "Healthcare", "VRTX": "Healthcare", "BIIB": "Healthcare",
    "ISRG": "Healthcare", "IDXX": "Healthcare", "DXCM": "Healthcare",
    "ILMN": "Healthcare", "GEHC": "Healthcare", "AZN": "Healthcare",

    # ═══ Industrial ═══
    "BA": "Industrial", "CAT": "Industrial", "GE": "Industrial",
    "RTX": "Industrial", "LMT": "Industrial", "NOC": "Industrial",
    "GD": "Industrial", "DE": "Industrial", "MMM": "Industrial",
    "EMR": "Industrial", "ETN": "Industrial", "ITW": "Industrial",
    "PH": "Industrial", "UPS": "Industrial", "FDX": "Industrial",
    "UNP": "Industrial", "NSC": "Industrial", "CSX": "Industrial",
    "HON": "Industrial", "ROP": "Industrial", "FAST": "Industrial",
    "ODFL": "Industrial", "PCAR": "Industrial", "CTAS": "Industrial",
    "CPRT": "Industrial",

    # ═══ Energy ═══
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "EOG": "Energy",
    "SLB": "Energy", "MPC": "Energy", "PSX": "Energy", "OXY": "Energy",
    "VLO": "Energy", "WMB": "Energy", "KMI": "Energy", "OKE": "Energy",
    "PXD": "Energy", "BKR": "Energy", "FANG": "Energy",

    # ═══ Utilities ═══
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "D": "Utilities", "AEP": "Utilities", "EXC": "Utilities",
    "XEL": "Utilities",

    # ═══ Real Estate ═══
    "AMT": "Real Estate", "PLD": "Real Estate", "EQIX": "Real Estate",
    "WELL": "Real Estate", "DLR": "Real Estate", "PSA": "Real Estate",
    "O": "Real Estate", "SPG": "Real Estate",

    # ═══ Materials ═══
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials",
    "FCX": "Materials", "NEM": "Materials",

    # ═══ ETF ═══
    "SPY": "ETF", "QQQ": "ETF", "DIA": "ETF", "IWM": "ETF",
    "VTI": "ETF", "VOO": "ETF", "ARKK": "ETF", "XLF": "ETF",
    "XLE": "ETF", "XLK": "ETF", "XLV": "ETF", "XLI": "ETF",
    "XLY": "ETF", "XLP": "ETF", "GLD": "ETF", "SLV": "ETF",
    "TLT": "ETF", "HYG": "ETF", "VXX": "ETF", "TQQQ": "ETF",
    "SQQQ": "ETF", "USO": "ETF", "UVXY": "ETF",
}


def get_extended_universe() -> List[str]:
    """Tüm tradable equity universe'ü döndür (~180 sembol, sektör mapping'li)."""
    return sorted(EXTENDED_SECTOR_MAP.keys())


def get_sector(symbol: str) -> str:
    """Bir sembol için sektör — extended map'te yoksa 'Unknown'."""
    return EXTENDED_SECTOR_MAP.get(symbol.upper(), "Unknown")


def get_broad_universe(include_core: bool = True) -> List[str]:
    """
    Broad scan için sembol listesi döndür.

    Args:
        include_core: True ise Core WATCHLIST'i garanti ekle (duplicate'siz)

    Returns:
        Unique ticker listesi (alfabetik sıralı)

    Fallback: Hata olursa Core WATCHLIST döner (asla boş liste yok).
    """
    try:
        universe = set(NASDAQ_100)

        if include_core:
            # Circular import'u önlemek için lazy import
            from config import WATCHLIST as CORE
            universe.update(CORE)

        return sorted(universe)

    except Exception:
        # En kötü senaryo: Core WATCHLIST fallback
        try:
            from config import WATCHLIST as CORE
            return sorted(set(CORE))
        except Exception:
            # Config bile yüklenemezse minimal hardcoded fallback
            return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
                    "TSLA", "META", "AMD", "SPY", "QQQ",
                    "NFLX", "CRM", "AVGO", "COIN", "MARA"]


def get_core_universe() -> List[str]:
    """
    Sadece Core WATCHLIST döndür (broad scan kapalıyken kullanılır).
    Mevcut davranışı korumak için wrapper.
    """
    try:
        from config import WATCHLIST as CORE
        return list(CORE)
    except Exception:
        return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
                "TSLA", "META", "AMD", "SPY", "QQQ",
                "NFLX", "CRM", "AVGO", "COIN", "MARA"]


def universe_stats() -> dict:
    """Diagnostic: evren boyutlarını göster (dashboard/debug için)."""
    try:
        from config import WATCHLIST as CORE
        core_set = set(CORE)
        ndx_set = set(NASDAQ_100)
        broad = core_set | ndx_set

        return {
            "core_count": len(core_set),
            "nasdaq100_count": len(ndx_set),
            "broad_total": len(broad),
            "overlap": len(core_set & ndx_set),
        }
    except Exception as e:
        return {"error": str(e)}
