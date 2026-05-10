"""测试模块一：吸引力分数"""

from yfd_quant.model.layer1_attraction import attraction_score


def test_attraction_bounds():
    """边界测试"""
    # x <= -2.5 -> 100
    assert attraction_score(-5.0) == 100.0
    assert attraction_score(-2.5) == 100.0
    # x >= 2.5 -> 0
    assert attraction_score(2.5) == 0.0
    assert attraction_score(5.0) == 0.0


def test_attraction_midpoint():
    """中点: x=0 -> 50"""
    assert attraction_score(0.0) == 50.0


def test_attraction_linear():
    """线性区间: f(x) = 50 - 20*x"""
    # x=-1.2 -> 50 - 20*(-1.2) = 74.0
    assert abs(attraction_score(-1.2) - 74.0) < 1e-9
    # x=0.12 -> 50 - 20*0.12 = 47.6
    assert abs(attraction_score(0.12) - 47.6) < 1e-9
    # x=1.0 -> 50 - 20*1 = 30
    assert abs(attraction_score(1.0) - 30.0) < 1e-9
    # x=-1.0 -> 50 + 20 = 70
    assert abs(attraction_score(-1.0) - 70.0) < 1e-9
