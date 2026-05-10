"""指标计算器 —— 从 NDX 日线 DataFrame 一次性计算全部指标"""

import pandas as pd

from yfd_quant.indicators.ma import sma
from yfd_quant.indicators.atr import atr
from yfd_quant.indicators.rsi import rsi
from yfd_quant.indicators.adx import calc_adx
from yfd_quant.indicators.price_extremes import get_52w_high, get_52w_low, get_ma200
from yfd_quant.types import IndicatorBundle


def compute_all(ndx_df: pd.DataFrame) -> IndicatorBundle:
    """从纳斯达克 100 日线数据计算全部技术指标

    Args:
        ndx_df: 按日期升序排列，列含 open/high/low/close

    Returns:
        IndicatorBundle 包含所有指标
    """
    close = ndx_df["close"]
    high = ndx_df["high"]
    low = ndx_df["low"]

    adx_val, di_plus, di_minus = calc_adx(high, low, close)

    return IndicatorBundle(
        ma20=round(sma(close, 20), 2),
        ma200=round(get_ma200(close), 2),
        high_52w=round(get_52w_high(high), 2),
        low_52w=round(get_52w_low(low), 2),
        atr14=round(atr(high, low, close, 14), 2),
        rsi=round(rsi(close, 14), 2),
        adx=round(adx_val, 2),
        di_plus=round(di_plus, 2),
        di_minus=round(di_minus, 2),
    )
