"""相对强弱指标 RSI(14) —— Wilder's Smoothing"""

import pandas as pd
import numpy as np


def rsi(close: pd.Series, period: int = 14) -> float:
    """计算 RSI(14) —— Wilder's Smoothing

    Args:
        close: 收盘价序列（按日期升序）
        period: 默认 14

    Returns:
        最新 RSI 值 (0-100)
    """
    if len(close) < period + 1:
        return 50.0

    delta = close.diff().dropna()
    vals = delta.values

    # 初始均值
    gains = [max(v, 0) for v in vals[:period]]
    losses = [abs(min(v, 0)) for v in vals[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period, len(vals)):
        gain = max(vals[i], 0)
        loss = abs(min(vals[i], 0))
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """计算全序列 RSI"""
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gains = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_losses = losses.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gains / avg_losses
    rsi_vals = 100.0 - 100.0 / (1.0 + rs)
    rsi_vals[avg_losses == 0] = 100.0
    return rsi_vals
