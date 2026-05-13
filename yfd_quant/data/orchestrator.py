"""数据编排器

一次 Sina 批量请求 → 存入 SQLite (NDX + CPO + NQ) → MarketSnapshot

R_NQ 计算: 纳指期货实时涨跌幅 = (hf_NQ当前 - DB昨收) / DB昨收 * 100
  若无昨收数据(首次运行)，降级使用 gb_ndx 现货涨跌幅
"""

import logging
from datetime import datetime
from typing import Tuple

from yfd_quant.data.sina_fetcher import (
    fetch_all as sina_fetch_all,
    get_us_equity_trade_date,
)
from yfd_quant.data.db import (
    insert_daily, get_all,
    insert_cpo_daily, insert_nq_daily, insert_fx_daily,
    insert_vix_daily,
    get_cpo_ma20,
    get_nq_prev_close, get_nq_last_two, get_ndx_prev_close,
    get_fx_prev_close,
    has_final_record,
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
    """纳指期货涨跌幅 R_NQ = (当前 - DB昨收) / DB昨收 × 100

    DB昨收 = nq_daily 中 date < today 的最近一条记录
    周一自动取上周五，跳过周末
    """
    nq_current = sina.nq_price
    nq_prev = get_nq_prev_close()

    if nq_prev > 0 and nq_current > 0:
        r_nq = round((nq_current - nq_prev) / nq_prev * 100, 2)
        logger.info(f"R_NQ = ({nq_current:.1f} - {nq_prev:.1f}) / {nq_prev:.1f} × 100 = {r_nq:+.2f}%")
    else:
        r_nq = 0.0
        logger.warning(f"R_NQ: 昨收缺失(prev={nq_prev:.1f} cur={nq_current:.1f})——请运行 --capture-nq 补录")
    return r_nq


def fetch_all() -> Tuple[MarketSnapshot, bool]:
    timestamp = datetime.now()
    weekend = _is_weekend()

    # ---- 一次批量请求 ----
    sina = sina_fetch_all()
    if not sina.ok:
        raise DataUnavailableError(f"Sina 数据获取失败: {sina.error}")

    # 关键数据非零校验（VIX/FX/NQ 为 0 说明接口异常，不能用零值跑模型）
    critical = []
    if sina.nq_price <= 0:
        critical.append("NQ期货")
    if sina.vix <= 0:
        critical.append("VIX")
    if sina.fx_price <= 0:
        critical.append("FX汇率")
    if critical and not weekend:
        raise DataUnavailableError(f"关键数据缺失: {', '.join(critical)}，接口可能异常，拒绝运行")

    # CPO 检查：工作日缺失时警告（非阻断，节假日/网络波动可能）
    if sina.cpo_error and not weekend:
        logger.warning("CPO 数据获取失败，R_CPO 将为 0（可能影响模型准确性）")

    # ---- 计算 R_NQ（必须在存入今日 NQ 之前）----
    r_nq = _calc_r_nq(sina)

    # ---- NQ/FX/VIX: 14:50 盘中写入 is_final=0, 次日 05:15 覆盖为 is_final=1 ----
    # NDX/CPO 收盘数据由 --capture-nq 在 05:15 统一写入，此处不写（14:50 数据不准确）
    if not weekend:
        op_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        trading_date = get_us_equity_trade_date(timestamp, is_close_mode=False)

        if sina.nq_price > 0 and not has_final_record("nq_daily", trading_date):
            insert_nq_daily(trading_date, sina.nq_open, sina.nq_high,
                            sina.nq_low, sina.nq_price, op_time, is_final=0)

        if sina.fx_price > 0 and not has_final_record("fx_daily", trading_date):
            insert_fx_daily(trading_date, sina.fx_price, op_time, is_final=0)

        if sina.vix > 0 and not has_final_record("vix_daily", trading_date):
            insert_vix_daily(trading_date, sina.vix_open, sina.vix_high,
                             sina.vix_low, sina.vix, op_time, is_final=0)

    # ---- 加载 NDX 历史 (排除最新行，保证指标用 t-1 数据) ----
    ndx_df = get_all()
    if ndx_df.empty:
        raise DataUnavailableError("SQLite 无 NDX 历史数据")
    # 指标计算应基于昨天收盘后的数据，排除刚插入的最新行
    ndx_hist = ndx_df.iloc[:-1] if len(ndx_df) >= 2 else ndx_df
    if len(ndx_hist) < 200:
        raise DataUnavailableError(f"NDX 历史仅 {len(ndx_hist)} 行，不足 200 行，无法计算 MA200 等指标")

    # ---- 周末：NQ 期货冻结，用 NQ 历史表最近两天的变化 ----
    if weekend:
        nq_rows = get_nq_last_two()
        if len(nq_rows) == 2:
            friday_close, thursday_close = nq_rows[0], nq_rows[1]
            if thursday_close > 0:
                r_nq = round((friday_close - thursday_close) / thursday_close * 100, 2)
                logger.info(f"R_NQ(周末): 周五期货变化 "
                            f"=({friday_close:.1f}-{thursday_close:.1f})/{thursday_close:.1f}*100"
                            f"={r_nq:+.2f}%")
            else:
                logger.warning("R_NQ(周末): 周四收盘价为 0，无法计算涨跌幅")

    # ---- CPO 主跌浪 ----
    cpo_downtrend = _check_cpo_downtrend(sina.cpo_price)

    data_quality = "full" if len(ndx_hist) >= 200 else "degraded"

    # R_FX: (当前 - DB昨收) / DB昨收 × 100
    fx_prev = get_fx_prev_close()
    if fx_prev > 0 and sina.fx_price > 0:
        r_fx = round((sina.fx_price - fx_prev) / fx_prev * 100, 4)
        logger.info(f"R_FX = ({sina.fx_price:.4f} - {fx_prev:.4f}) / {fx_prev:.4f} × 100 = {r_fx:+.4f}%")
    else:
        r_fx = 0.0
        logger.warning(f"R_FX: 昨收缺失(prev={fx_prev:.4f} cur={sina.fx_price:.4f})——请运行 --capture-nq 补录")

    # NDX 昨收：从数据库取（05:15 定时任务已录入），不依赖新浪接口
    ndx_prev = get_ndx_prev_close()
    if ndx_prev > 0:
        logger.info(f"NDX昨收(DB) = {ndx_prev:.2f}")
    else:
        ndx_prev = sina.ndx_prev_close
        logger.warning(f"NDX昨收DB缺失，降级使用新浪接口值 = {ndx_prev:.2f}")

    return MarketSnapshot(
        timestamp=timestamp,
        r_cpo=round(sina.cpo_change_pct, 2),
        r_nq=r_nq,
        r_fx=r_fx,
        cpo_close_today=sina.cpo_price,
        cpo_ma20_yesterday=get_cpo_ma20()[0],
        cpo_ma20_5days_ago=get_cpo_ma20()[1],
        cpo_downtrend=cpo_downtrend,
        ndx_close_prev=ndx_prev,
        ndx_historical=ndx_hist,  # 用 t-1 数据计算指标
        vix=sina.vix,
        indicators_ready=False,
        data_quality=data_quality,
    ), weekend
