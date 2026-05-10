"""平均真实波幅 ATR(14) —— Wilder's Smoothing"""

import pandas as pd
import numpy as np


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """计算每日真实波幅 TR"""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """计算 ATR(14) —— Wilder's Smoothing

    Args:
        high, low, close: 日线数据（按日期升序）
        period: 默认 14

    Returns:
        最新一期 ATR 值
    """
    tr = true_range(high, low, close).dropna()

    if len(tr) < period:
        return float(tr.mean())

    # Wilder's 平滑: 初始值 = 前 14 个 TR 的均值
    vals = tr.values
    atr_val = vals[:period].mean()

    # 迭代: ATR_i = (13*ATR_{i-1} + TR_i) / 14
    for i in range(period, len(vals)):
        atr_val = ((period - 1) * atr_val + vals[i]) / period

    return float(atr_val)


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = 14) -> pd.Series:
    """计算全序列 ATR"""
    tr = true_range(high, low, close)
    atr_vals = []
    running = None
    count = 0
    tr_sum = 0.0

    for i, tr_val in enumerate(tr):
        if np.isnan(tr_val):
            atr_vals.append(np.nan)
            continue
        if count < period:
            tr_sum += tr_val
            count += 1
            if count == period:
                running = tr_sum / period
                atr_vals.append(running)
            else:
                atr_vals.append(np.nan)
        else:
            running = ((period - 1) * running + tr_val) / period
            atr_vals.append(running)

    return pd.Series(atr_vals, index=tr.index)
