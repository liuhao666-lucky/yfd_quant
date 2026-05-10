"""简单移动平均线"""

import pandas as pd


def sma(series: pd.Series, period: int) -> float:
    """计算最近一期的简单移动平均

    Args:
        series: 价格序列（按日期升序）
        period: 周期

    Returns:
        最近一期 SMA 值
    """
    if len(series) < period:
        return float(series.mean())
    return float(series.tail(period).mean())


def sma_series(series: pd.Series, period: int) -> pd.Series:
    """计算全序列 SMA"""
    return series.rolling(window=period, min_periods=period).mean()
