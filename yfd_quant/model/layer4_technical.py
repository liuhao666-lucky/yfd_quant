"""模块四：高级技术修正因子（因子互斥区）

包含三个子模块：
  4.1 真实波幅风控 Ω_VOL（防黑天鹅）
  4.2 趋势烈度过滤 τ_ADX（区分飞刀与熊市）
  4.3 S 型恐慌乘数 Φ(VX)
"""

import math
from dataclasses import dataclass


@dataclass
class TechResult:
    omega_vol: float
    tau_adx: float
    phi: float
    gap: float
    strong_downtrend: bool


def omega_vol(p_est: float, close_prev: float, atr14: float) -> tuple[float, float]:
    """4.1 真实波幅风控 Ω_VOL

    盘前跳空缺口超过 2 倍 ATR14 时，总分打 7 折。

    Returns:
        (omega_vol, gap)
    """
    if close_prev == 0:
        return 1.0, 0.0
    gap = abs(p_est - close_prev)
    if gap > 2.0 * atr14:
        return 0.7, gap
    return 1.0, gap


def tau_adx(adx: float, di_plus: float, di_minus: float,
            p_est: float, ma200: float) -> tuple[float, bool]:
    """4.2 趋势烈度过滤 τ_ADX

    三档:
    - 强趋势 + 空头主导 (ADX>25 & DI- > DI+): τ=0.6 "接飞刀"
    - 弱趋势 + 年线以下 (ADX<=25 & P_est<MA200): τ=0.8 "漫漫熊市"
    - 其他: τ=1.0

    Returns:
        (tau_adx, strong_downtrend)
    """
    strong_trend = adx > 25.0 and di_minus > di_plus

    if strong_trend:
        return 0.6, True
    elif adx <= 25.0 and p_est < ma200:
        return 0.8, False
    return 1.0, False


def phi_vix(vix: float) -> float:
    """4.3 S 型恐慌乘数 Φ(VX)

    Logistic: Φ = 0.6 + 1.6 / (1 + e^{-0.7 * (VIX - 14)})
    - VIX 低时 ≈ 0.6（风平浪静不冲动）
    - VIX 升高时平滑放大到接近 2.2（恐慌时贪婪）
    """
    exponent = math.exp(-0.7 * (vix - 14.0))
    return round(0.6 + 1.6 / (1.0 + exponent), 4)


def compute_all(
    p_est: float,
    close_prev: float,
    atr14: float,
    adx: float,
    di_plus: float,
    di_minus: float,
    ma200: float,
    vix: float,
) -> TechResult:
    """一站式计算模块四全部子项"""
    ov, gap = omega_vol(p_est, close_prev, atr14)
    ta, strong = tau_adx(adx, di_plus, di_minus, p_est, ma200)
    phi = phi_vix(vix)

    return TechResult(
        omega_vol=ov,
        tau_adx=ta,
        phi=phi,
        gap=gap,
        strong_downtrend=strong,
    )
