"""价格极值与长期均线"""

import pandas as pd


def get_52w_high(high: pd.Series) -> float:
    """52 周最高价（约 252 个交易日）"""
    window = min(252, len(high))
    return float(high.tail(window).max())


def get_52w_low(low: pd.Series) -> float:
    """52 周最低价（约 252 个交易日）"""
    window = min(252, len(low))
    return float(low.tail(window).min())


def get_ma200(close: pd.Series) -> float:
    """200 日均线（年线）

    Raises:
        ValueError: 数据不足 200 行
    """
    if len(close) < 200:
        raise ValueError(f"MA200 需要至少 200 行数据，当前仅 {len(close)} 行")
    return float(close.tail(200).mean())
