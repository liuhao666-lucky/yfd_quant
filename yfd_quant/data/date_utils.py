"""交易日计算 —— 四种数据品种的 date 确定规则

规则:
  - 不依赖新浪返回字段
  - operate_time = 抓取时刻（北京时间），date = 实际交易日
  - 美股跨天: 21:30~04:00(夏令时) 属于同一交易日
"""

from datetime import datetime, timedelta


def previous_trading_day(dt: datetime) -> datetime:
    """返回 dt 之前最近的一个交易日（跳过周六、周日）

    Examples:
        Monday    → Friday
        Sunday    → Friday
        Saturday  → Friday
        Wednesday → Tuesday
    """
    prev = dt - timedelta(days=1)
    if prev.weekday() == 5:      # Sat → Fri
        prev -= timedelta(days=1)
    elif prev.weekday() == 6:    # Sun → Fri
        prev -= timedelta(days=2)
    return prev


def get_us_equity_trade_date(capture_time: datetime,
                              is_close_mode: bool) -> str:
    """美股品种 (NQ/NDX/VIX) 的交易日

    close_mode=True  (05:15 收盘抓取):
        美股收盘于次日凌晨 → trade_date = previous_trading_day(capture_time)
        e.g. Tue 05:15 → Mon close → date = Mon

    close_mode=False (14:50 实时抓取):
        trade_date = capture_time.date()
        但周末或凌晨(美股未开盘)回退到 previous_trading_day
        e.g. Tue 01:35 → Mon

    Returns: 'YYYY-MM-DD'
    """
    if is_close_mode:
        return previous_trading_day(capture_time).strftime("%Y-%m-%d")

    # 实时模式: 当天日期, 周末/凌晨回退
    h = capture_time.hour
    if h < 9 or capture_time.weekday() >= 5:
        # 凌晨(美股未收盘)或周末 → 数据属于前一个交易日
        return previous_trading_day(capture_time).strftime("%Y-%m-%d")
    return capture_time.strftime("%Y-%m-%d")


def get_cpo_trade_date(capture_time: datetime,
                        is_close_mode: bool) -> str:
    """A股品种 (CPO) 的交易日

    close_mode=True  (05:15 抓取):
        → previous_trading_day(capture_time)

    close_mode=False (14:50 或任意时间):
        凌晨(h<9)或周末 → previous_trading_day
        否则 → capture_time.date()
    """
    if is_close_mode:
        return previous_trading_day(capture_time).strftime("%Y-%m-%d")
    if capture_time.hour < 9 or capture_time.weekday() >= 5:
        return previous_trading_day(capture_time).strftime("%Y-%m-%d")
    return capture_time.strftime("%Y-%m-%d")


def is_us_close_window(dt: datetime) -> bool:
    """判断北京时间是否处于美股收盘后抓取窗口

    夏令时 (3月第2个周日~11月第1个周日): 美股 04:00 收盘 → 窗口 04:00-06:00
    冬令时 (其余时间):               美股 05:00 收盘 → 窗口 05:00-07:00

    简化: 4月~10月=夏令时, 其余=冬令时 (边界月份由具体日期微调)
    """
    m, d = dt.month, dt.day
    # 夏令时: 3月第2个周日 ~ 11月第1个周日 → 近似 4~10月
    is_dst = 4 <= m <= 10
    if m == 3 and d >= 8:   # 3月8日后通常是夏令时
        is_dst = True
    if m == 11 and d <= 7:  # 11月7日前通常是夏令时
        is_dst = True

    if is_dst:
        return 4 <= dt.hour <= 6   # 夏令时: 04:00~06:00
    else:
        return 5 <= dt.hour <= 7   # 冬令时: 05:00~07:00


def get_fx_trade_date(capture_time: datetime) -> str:
    """汇率 (USDCNH) 的交易日

    仅主模型(14:50)使用:
        hour < 9 (凌晨) → previous_trading_day
        否则 → capture_time.date()
        周末自动回退

    Returns: 'YYYY-MM-DD'
    """
    if capture_time.hour < 9 or capture_time.weekday() >= 5:
        return previous_trading_day(capture_time).strftime("%Y-%m-%d")
    return capture_time.strftime("%Y-%m-%d")
