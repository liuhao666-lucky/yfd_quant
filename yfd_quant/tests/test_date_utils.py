"""测试 date_utils —— 四种日期函数边界用例"""
from datetime import datetime
from yfd_quant.data.date_utils import (
    previous_trading_day,
    get_us_equity_trade_date,
    get_cpo_trade_date,
    get_fx_trade_date,
)


def test_previous_trading_day():
    """任意日期 → 前一交易日"""
    assert previous_trading_day(datetime(2026, 5, 11)).strftime("%Y-%m-%d") == "2026-05-08"  # Mon → Fri
    assert previous_trading_day(datetime(2026, 5, 10)).strftime("%Y-%m-%d") == "2026-05-08"  # Sun → Fri
    assert previous_trading_day(datetime(2026, 5, 9)).strftime("%Y-%m-%d") == "2026-05-08"   # Sat → Fri
    assert previous_trading_day(datetime(2026, 5, 12)).strftime("%Y-%m-%d") == "2026-05-11"  # Tue → Mon
    assert previous_trading_day(datetime(2026, 5, 13)).strftime("%Y-%m-%d") == "2026-05-12"  # Wed → Tue


def test_us_equity_close():
    """美股收盘模式"""
    # Tue 05:15 → Mon close
    assert get_us_equity_trade_date(datetime(2026, 5, 12, 5, 15), True) == "2026-05-11"
    # Mon 05:15 → Fri close (Mon前一交易日=Sun→Fri)
    assert get_us_equity_trade_date(datetime(2026, 5, 11, 5, 15), True) == "2026-05-08"
    # Sat 05:15 → Fri
    assert get_us_equity_trade_date(datetime(2026, 5, 9, 5, 15), True) == "2026-05-08"


def test_us_equity_realtime():
    """美股实时模式"""
    # Mon 14:50 → Mon
    assert get_us_equity_trade_date(datetime(2026, 5, 11, 14, 50), False) == "2026-05-11"
    # Tue 01:35 (凌晨) → Mon (美股未开盘)
    assert get_us_equity_trade_date(datetime(2026, 5, 12, 1, 35), False) == "2026-05-11"
    # Sun 14:50 → Fri
    assert get_us_equity_trade_date(datetime(2026, 5, 10, 14, 50), False) == "2026-05-08"


def test_cpo_close():
    """A股收盘模式"""
    assert get_cpo_trade_date(datetime(2026, 5, 12, 5, 15), True) == "2026-05-11"


def test_cpo_realtime():
    """A股实时模式"""
    assert get_cpo_trade_date(datetime(2026, 5, 11, 14, 50), False) == "2026-05-11"
    assert get_cpo_trade_date(datetime(2026, 5, 10, 14, 50), False) == "2026-05-08"


def test_fx():
    """汇率"""
    assert get_fx_trade_date(datetime(2026, 5, 11, 14, 50)) == "2026-05-11"
    assert get_fx_trade_date(datetime(2026, 5, 10, 14, 50)) == "2026-05-08"
    assert get_fx_trade_date(datetime(2026, 5, 12, 1, 35)) == "2026-05-11"  # 凌晨→前日
