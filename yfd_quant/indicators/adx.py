"""趋向平均 ADX / +DI / -DI —— Wilder's Smoothing"""

import pandas as pd
import numpy as np


def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> tuple[float, float, float]:
    """计算 ADX, +DI, -DI

    Args:
        high, low, close: 日线数据（按日期升序）
        period: 默认 14

    Returns:
        (ADX, +DI, -DI)
    """
    if len(close) < period * 2:
        return 0.0, 0.0, 0.0

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # 方向运动
    up_move = high.diff()
    down_move = -low.diff()

    # +DM: 涨且涨幅 > 跌(绝对值)，且涨>0
    plus_dm = pd.Series(0.0, index=high.index)
    mask_plus = (up_move > down_move) & (up_move > 0)
    plus_dm.loc[mask_plus] = up_move.loc[mask_plus]

    # -DM: 跌且跌幅(绝对值) > 涨幅，且跌>0
    minus_dm = pd.Series(0.0, index=high.index)
    mask_minus = (down_move > up_move) & (down_move > 0)
    minus_dm.loc[mask_minus] = down_move.loc[mask_minus]

    # Wilder's 平滑
    tr_s = _wilder_smooth(tr, period)
    plus_dm_s = _wilder_smooth(plus_dm, period)
    minus_dm_s = _wilder_smooth(minus_dm, period)

    # DI
    plus_di = (plus_dm_s / tr_s) * 100
    minus_di = (minus_dm_s / tr_s) * 100

    # DX
    di_sum = plus_di + minus_di
    dx = pd.Series(0.0, index=plus_di.index)
    mask = di_sum > 0
    dx.loc[mask] = (abs(plus_di.loc[mask] - minus_di.loc[mask]) / di_sum.loc[mask]) * 100

    # ADX = Wilder's 平滑 DX
    adx_s = _wilder_smooth(dx, period)

    return (
        float(adx_s.iloc[-1]) if not np.isnan(adx_s.iloc[-1]) else 0.0,
        float(plus_di.iloc[-1]) if not np.isnan(plus_di.iloc[-1]) else 0.0,
        float(minus_di.iloc[-1]) if not np.isnan(minus_di.iloc[-1]) else 0.0,
    )


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's 平滑 (等效 TRIMA 但用 EMA 近似)"""
    result = pd.Series(np.nan, index=series.index)
    clean = series.dropna()

    if len(clean) < period:
        return pd.Series(0.0, index=series.index)

    vals = clean.values
    # 初始值 = 前 period 个值的均值
    start_idx = clean.index[period - 1]
    running = vals[:period].mean()
    result.loc[start_idx] = running

    for i in range(period, len(vals)):
        running = ((period - 1) * running + vals[i]) / period
        result.loc[clean.index[i]] = running

    return result.fillna(0.0)
