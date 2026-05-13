"""模块三：聪明资金 Alpha 补偿（因子互斥区）

包含四个子模块（遵守互斥铁律）：
  3.1 现价动态投射 P_est
  3.2 极端离散奖励 Ω_EXT（血洗日独立通道）
  3.3 双向乖离率补偿 Ω_BIAS（与 Ω_EXT 互斥）
  3.4 历史水位补偿 Ω_POS（黄金坑，始终有效）
  +   RSI 衰竭奖励（与 Ω_EXT 互斥，且要求乖离小）
"""

import math
from dataclasses import dataclass


@dataclass
class AlphaResult:
    omega_ext: float
    omega_bias: float
    omega_pos: float
    rsi_bonus: float
    bias_pct: float
    p_pos: float
    p_est: float


def compute_p_est(ndx_close_prev: float, r_nq: float) -> float:
    """3.1 预估纳斯达克今晚开盘价

    P_est = C_{t-1} * (1 + R_NQ / 100)
    """
    return ndx_close_prev * (1.0 + r_nq / 100.0)


def omega_extreme(r_cpo: float, r_nq: float) -> float:
    """3.2 极端离散奖励 Ω_EXT

    触发条件: 中美科技盘出现 -5% 以上的砸盘
    - 两者同时 <= -5%: +12 分
    - 仅其一 <= -5%: +5 分
    - 否则: 0
    """
    cpo_crash = r_cpo <= -5.0
    nq_crash = r_nq <= -5.0

    if cpo_crash and nq_crash:
        return 12.0
    elif cpo_crash or nq_crash:
        return 5.0
    return 0.0


def omega_bias(p_est: float, ma20: float, omega_ext: float = 0.0) -> tuple[float, float]:
    """3.3 单向乖离率补偿 — 只捡超卖的皮筋

    与 Ω_EXT 互斥，且仅向下偏离（BIAS ≤ -2.5%）时才奖励。
    向上偏离直接为 0，杜绝追高。

    Returns:
        (omega_bias, bias_pct)
    """
    if ma20 == 0:
        return 0.0, 0.0

    bias_pct = round(((p_est - ma20) / ma20) * 100.0, 2)

    if omega_ext > 0:
        return 0.0, bias_pct

    # 单向：仅 BIAS ≤ -2.5%（超卖）给予 8×|BIAS| 奖励
    if bias_pct <= -2.5:
        return round(8.0 * abs(bias_pct), 2), bias_pct
    return 0.0, bias_pct


def omega_position(p_est: float, high_52w: float, low_52w: float) -> tuple[float, float]:
    """3.4 历史水位补偿 Ω_POS（黄金坑探测器）

    看预估开盘价在过去一年 52 周高低区间内的位置。
    越低越靠近历史大坑，补偿越多（最多 20 分）。

    Returns:
        (omega_pos, p_pos)
    """
    price_range = high_52w - low_52w
    if price_range <= 0:
        return 0.0, 0.0

    p_pos = round(((p_est - low_52w) / price_range) * 100.0, 2)
    p_pos = max(0.0, min(100.0, p_pos))  # 防止越界产生虚假信号

    if p_pos <= 20.0:
        omega = round(20.0 * (1.0 - p_pos / 20.0), 2)
        return omega, p_pos
    return 0.0, p_pos


def rsi_bonus(rsi: float, omega_ext: float = 0.0, abs_bias: float = 99.0) -> float:
    """RSI 衰竭奖励

    互斥条件:
    - omega_ext > 0 时 = 0（急跌已由乖离率处理）
    - abs_bias >= 2.5 时 = 0（乖离率大的市场，RSI 信号不独立）

    奖励规则:
    - RSI <= 20: 满额 +10
    - 20 < RSI < 30: 线性 (30 - RSI)
    - RSI >= 30: 0
    """
    if omega_ext > 0 or abs_bias >= 2.5:
        return 0.0

    if rsi <= 20:
        return 10.0
    if rsi < 30:
        return 30.0 - rsi
    return 0.0


def compute_all(
    r_cpo: float,
    r_nq: float,
    ndx_close_prev: float,
    ma20: float,
    high_52w: float,
    low_52w: float,
    rsi_val: float,
) -> AlphaResult:
    """一站式计算模块三全部子项"""
    p_est = compute_p_est(ndx_close_prev, r_nq)
    oe = omega_extreme(r_cpo, r_nq)
    ob, bias_pct = omega_bias(p_est, ma20, oe)
    op, ppos = omega_position(p_est, high_52w, low_52w)
    rb = rsi_bonus(rsi_val, oe, abs(bias_pct))

    return AlphaResult(
        omega_ext=oe,
        omega_bias=ob,
        omega_pos=op,
        rsi_bonus=rb,
        bias_pct=bias_pct,
        p_pos=ppos,
        p_est=p_est,
    )
