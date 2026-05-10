"""数据编排器

一次 Sina 批量请求 → 存入 SQLite (NDX + CPO + NQ) → MarketSnapshot

R_NQ 计算: 纳指期货实时涨跌幅 = (hf_NQ当前 - DB昨收) / DB昨收 * 100
  若无昨收数据(首次运行)，降级使用 gb_ndx 现货涨跌幅
"""

import logging
from datetime import datetime
from typing import Tuple

from yfd_quant.data.sina_fetcher import fetch_all as sina_fetch_all
from yfd_quant.data.db import (
    insert_daily, get_all,
    insert_cpo_daily, get_cpo_ma20,
    get_nq_prev_close, get_nq_last_two,
)
from yfd_quant.types import MarketSnapshot

logger = logging.getLogger(__name__)


class DataUnavailableError(Exception):
    """关键数据不可用"""


def _is_weekend() -> bool:
    return datetime.now().weekday() >= 5


def _check_cpo_downtrend(cpo_close_today: float) -> bool:
    ma20_yest, ma20_5d = get_cpo_ma20()
    if ma20_yest <= 0 or ma20_5d <= 0:
        return False
    return cpo_close_today < ma20_yest and ma20_yest < ma20_5d


def _calc_r_nq(sina) -> float:
    """计算纳指期货实时涨跌幅 R_NQ

    (hf_NQ当前价 - DB昨收) / DB昨收 * 100
    昨收缺失时返回 0，不做任何降级
    """
    nq_current = sina.nq_future
    nq_prev = get_nq_prev_close()

    if nq_prev > 0 and nq_current > 0:
        r_nq = (nq_current - nq_prev) / nq_prev * 100
        logger.info(f"R_NQ: 期货 (当前={nq_current:.0f} 昨收={nq_prev:.0f}) = {r_nq:+.2f}%")
        return round(r_nq, 2)

    logger.warning("R_NQ: 纳指期货昨收缺失！请先运行 --capture-nq 抓取收盘价")
    return 0.0


def fetch_all(config: dict = None) -> Tuple[MarketSnapshot, bool]:
    timestamp = datetime.now()
    weekend = _is_weekend()

    # ---- 一次批量请求 ----
    sina = sina_fetch_all()
    if not sina.ok:
        raise DataUnavailableError(f"Sina 数据获取失败: {sina.error}")

    # ---- 计算 R_NQ（必须在存入今日 NQ 之前）----
    r_nq = _calc_r_nq(sina)

    # ---- 存入 SQLite（工作日才写，避免周末重复覆盖） ----
    if not weekend:
        if sina.ndx_open > 0 and sina.ndx_price > 0:
            insert_daily(sina.ndx_time[:10], sina.ndx_open,
                         sina.ndx_high, sina.ndx_low, sina.ndx_price)

        if sina.cpo_price > 0 and sina.cpo_date:
            insert_cpo_daily(sina.cpo_date, sina.cpo_price)

    # NQ 收盘价由 --capture-nq 单独抓取，此处不写入

    # ---- 加载 NDX 历史 (排除最新行，保证指标用 t-1 数据) ----
    ndx_df = get_all()
    if ndx_df.empty:
        raise DataUnavailableError("SQLite 无 NDX 历史数据")
    # 指标计算应基于昨天收盘后的数据，排除刚插入的最新行
    ndx_hist = ndx_df.iloc[:-1] if len(ndx_df) >= 2 else ndx_df

    # ---- 周末：NQ 期货冻结，用 NQ 历史表最近两天的变化 ----
    if weekend:
        nq_rows = get_nq_last_two()
        if len(nq_rows) == 2:
            friday_close, thursday_close = nq_rows[0], nq_rows[1]
            r_nq = round((friday_close - thursday_close) / thursday_close * 100, 2)
            logger.info(f"R_NQ(周末): 周五期货变化 "
                        f"=({friday_close:.1f}-{thursday_close:.1f})/{thursday_close:.1f}*100"
                        f"={r_nq:+.2f}%")

    # ---- CPO 主跌浪 ----
    cpo_downtrend = _check_cpo_downtrend(sina.cpo_price)

    data_quality = "full" if len(ndx_hist) >= 200 else "degraded"

    return MarketSnapshot(
        timestamp=timestamp,
        r_cpo=round(sina.cpo_change_pct, 2),
        r_nq=r_nq,
        r_fx=round(sina.fx_change_pct, 2),
        cpo_close_today=sina.cpo_price,
        cpo_ma20_yesterday=get_cpo_ma20()[0],
        cpo_ma20_5days_ago=get_cpo_ma20()[1],
        cpo_downtrend=cpo_downtrend,
        ndx_close_prev=sina.ndx_prev_close,
        ndx_historical=ndx_hist,  # 用 t-1 数据计算指标
        vix=sina.vix,
        indicators_ready=False,
        data_quality=data_quality,
    ), weekend
