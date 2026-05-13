"""指标计算器 —— 从 NDX 日线 DataFrame 一次性计算全部指标"""

import pandas as pd

from yfd_quant.indicators.ma import sma
from yfd_quant.indicators.atr import atr
from yfd_quant.indicators.rsi import rsi
from yfd_quant.indicators.adx import calc_adx
from yfd_quant.indicators.price_extremes import get_52w_high, get_52w_low, get_ma200
from yfd_quant.types import IndicatorBundle


MIN_ROWS = 200  # MA200 需要至少 200 行数据，低于此值直接报错


def compute_all(ndx_df: pd.DataFrame) -> IndicatorBundle:
    """从纳斯达克 100 日线数据计算全部技术指标

    Args:
        ndx_df: 按日期升序排列，列含 open/high/low/close

    Returns:
        IndicatorBundle 包含所有指标

    Raises:
        ValueError: 数据行数不足或列缺失
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(ndx_df.columns)
    if missing:
        raise ValueError(f"NDX 数据缺少必要列: {missing}")

    if len(ndx_df) < MIN_ROWS:
        raise ValueError(f"NDX 历史数据仅 {len(ndx_df)} 行，不足 {MIN_ROWS} 行，"
                         f"MA200 等指标无法准确计算，拒绝降级运行")

    close = ndx_df["close"]
    high = ndx_df["high"]
    low = ndx_df["low"]

    if close.isna().any() or high.isna().any() or low.isna().any():
        raise ValueError("NDX 数据包含 NaN 值，无法计算指标")

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
