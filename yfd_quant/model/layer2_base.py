"""模块二：多因子底仓与防坑过滤

Base = 0.35 * (f_CPO * τ_CPO) + 0.55 * f_NQ + 0.10 * f_FX

权重说明: CPO(35%), 纳指期货(55%), 汇率(10%)
τ_CPO = 0.8 if CPO 主跌浪, else 1.0
"""


W_CPO = 0.35
W_NQ = 0.55
W_FX = 0.10
TAU_CPO_DISCOUNT = 0.8


def compute_base(f_cpo: float, tau_cpo: float, f_nq: float, f_fx: float) -> float:
    """计算多因子底仓分数

    Args:
        f_cpo: CPO 吸引力分数 (0-100)
        tau_cpo: CPO 防坑系数 (0.8 或 1.0)
        f_nq: 纳指期货吸引力分数 (0-100)
        f_fx: 汇率吸引力分数 (0-100)

    Returns:
        Base 分数 (0-100)
    """
    return round(W_CPO * (f_cpo * tau_cpo) + W_NQ * f_nq + W_FX * f_fx, 2)
