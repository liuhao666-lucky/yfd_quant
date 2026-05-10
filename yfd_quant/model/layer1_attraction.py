"""模块一：单指标吸引力清洗

把涨跌幅统一变成 0~100 的"便宜程度分数"。
f(x) = 100 (x <= -2.5), 0 (x >= 2.5), 50-20x (中间)
"""


def attraction_score(percent_change: float) -> float:
    """将涨跌幅百分比映射为 0~100 的吸引力分数

    Args:
        percent_change: 涨跌幅%，例如 -1.8 表示跌了 1.8%

    Returns:
        吸引力分数，100 表示最便宜，0 表示最贵
    """
    if percent_change <= -2.5:
        return 100.0
    if percent_change >= 2.5:
        return 0.0
    return round(50.0 - 20.0 * percent_change, 2)
