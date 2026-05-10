"""模块六：真金白银买入金额

二次方曲线 + 时区敬畏折扣:
- SBI < 30: 只买底仓 M_min
- SBI >= 30: M_min + 0.85 * max(0, M * ratio^2 - M_min)
  其中 ratio = (SBI - 30) / 70
"""


def compute_amount(sbi: float, M: float = 50.0, M_min: float = 10.0,
                   timezone_discount: float = 0.85) -> tuple[float, dict]:
    """将 SBI 分数映射为建议买入金额

    Args:
        sbi: SBI 总分
        M: 单日最大申购额
        M_min: 每日强制底仓
        timezone_discount: 时区敬畏折扣

    Returns:
        (amount, detail_dict)
    """
    if sbi < 30.0:
        return round(M_min, 2), {
            "ratio": 0.0,
            "full_dynamic": 0.0,
            "extra_before": 0.0,
            "extra_after": 0.0,
            "capped": False,
        }

    ratio = (sbi - 30.0) / 70.0         # 0 → 1
    full_dynamic = M * (ratio ** 2)     # 二次曲线加速
    extra_before = max(0.0, full_dynamic - M_min)
    extra_after = extra_before * timezone_discount
    amount = round((M_min + extra_after) * 100.0) / 100.0
    return amount, {
        "ratio": round(ratio, 4),
        "full_dynamic": round(full_dynamic, 2),
        "extra_before": round(extra_before, 2),
        "extra_after": round(extra_after, 2),
    }
