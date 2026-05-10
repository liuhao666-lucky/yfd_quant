"""模块五：最终得分汇聚

SBI = clamp( (Base + Σα) × Φ(VIX) × τ_ADX × Ω_VOL,  0, 100 )
"""


def compute_sbi(
    base: float,
    omega_ext: float,
    omega_bias: float,
    omega_pos: float,
    rsi_bonus: float,
    phi: float,
    tau_adx: float,
    omega_vol: float,
) -> tuple[float, float]:
    """计算最终 SBI 得分

    Args:
        base: 模块二底仓分
        omega_ext/omega_bias/omega_pos/rsi_bonus: 模块三 Alpha 各分量
        phi: VIX 恐慌乘数
        tau_adx: ADX 趋势折扣
        omega_vol: 波动率风控折扣

    Returns:
        (SBI, raw_score) - SBI 已 clamp 到 0~100
    """
    alpha_sum = omega_ext + omega_bias + omega_pos + rsi_bonus
    raw = round((base + alpha_sum) * phi * tau_adx * omega_vol, 2)

    sbi = round(min(100.0, max(0.0, raw)), 2)
    return sbi, raw
