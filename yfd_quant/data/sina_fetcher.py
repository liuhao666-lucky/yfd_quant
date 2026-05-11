"""新浪财经 hq.sinajs.cn —— 批量一次性抓取全部数据

一次 HTTP 请求获取: 纳指100、CPO概念、VIX、汇率、纳指期货、费城半导体
"""

# date 逻辑已迁移到 yfd_quant/data/date_utils.py
# 为兼容旧调用方, 从此处 re-export
from yfd_quant.data.date_utils import (
    previous_trading_day,
    get_us_equity_trade_date,
    get_cpo_trade_date,
    get_fx_trade_date,
    is_us_close_window,
)

import re
import requests
from dataclasses import dataclass

SINA_URL = "https://hq.sinajs.cn/list={codes}"
ALL_CODES = "hf_NQ,gb_ndx,gb_$sox,gn0701159,hf_VX,fx_susdcnh"
HEADERS = {"Referer": "https://finance.sina.com.cn"}


@dataclass
class SinaData:
    """一次批量请求获取的全部市场数据"""
    # 纳指100 (gb_ndx)
    ndx_price: float = 0.0       # 收盘 [1]
    ndx_change_pct: float = 0.0  # 涨跌幅% [2]
    ndx_open: float = 0.0        # 今开 [5]
    ndx_high: float = 0.0        # 最高 [6]
    ndx_low: float = 0.0         # 最低 [7]
    ndx_volume: int = 0          # 成交量 [10]
    ndx_prev_close: float = 0.0  # 昨收 [26]
    ndx_time: str = ""           # 时间 [3]

    # CPO概念 (gn0701159)
    cpo_open: float = 0.0        # 今开 [1]
    cpo_prev_close: float = 0.0  # 昨收 [2]
    cpo_price: float = 0.0       # 收盘 [3]
    cpo_high: float = 0.0        # 最高 [4]
    cpo_low: float = 0.0         # 最低 [5]
    cpo_volume: int = 0          # 成交量 [8]
    cpo_amount: float = 0.0      # 成交额 [9]
    cpo_change_pct: float = 0.0  # 涨跌幅%（自算）
    cpo_date: str = ""           # 日期 [30]
    cpo_error: bool = False

    # VIX (hf_VX)
    vix: float = 0.0             # 收盘 [0]
    vix_open: float = 0.0        # 今开 [8]
    vix_high: float = 0.0        # 最高 [4]
    vix_low: float = 0.0         # 最低 [5]
    vix_prev_close: float = 0.0  # 昨收 [7]

    # 汇率 (fx_susdcnh)
    fx_price: float = 0.0        # 收盘 [1]
    fx_open: float = 0.0         # 今开 [5]
    fx_high: float = 0.0         # 最高 [6]
    fx_low: float = 0.0          # 最低 [7]
    fx_prev_close: float = 0.0   # 昨收 [3]
    fx_change_pct: float = 0.0   # 涨跌幅%（自算）

    # 纳指期货 (hf_NQ)
    nq_price: float = 0.0        # 收盘 [0]
    nq_open: float = 0.0         # 今开 [8]
    nq_high: float = 0.0         # 最高 [4]
    nq_low: float = 0.0          # 最低 [5]

    # 费城半导体 (gb_$sox)
    sox_change_pct: float = 0.0

    # 状态
    ok: bool = False
    error: str = ""


class SinaError(Exception):
    """新浪数据获取失败"""


def _parse_field(text: str, code: str) -> list[str]:
    """从批量返回中解析单个代码的字段"""
    # 转义 $ 符号用于正则
    escaped = code.replace("$", "\\$")
    m = re.search(rf'hq_str_{escaped}="([^"]*)"', text)
    if not m:
        raise SinaError(f"未找到 {code} 的数据")
    return m.group(1).split(",")


def _compute_change(cur: float, prev: float) -> float:
    """计算涨跌幅%"""
    if prev > 0:
        return (cur - prev) / prev * 100.0
    return 0.0


def fetch_all() -> SinaData:
    """一次 HTTP 请求获取全部市场数据"""
    try:
        url = SINA_URL.format(codes=ALL_CODES)
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "gb2312"
        text = resp.text
    except requests.RequestException as e:
        return SinaData(ok=False, error=f"网络请求失败: {e}")

    data = SinaData(ok=True)

    try:
        # ---- gb_ndx: 纳斯达克100 ----
        f = _parse_field(text, "gb_ndx")
        data.ndx_price = float(f[1])
        data.ndx_change_pct = float(f[2])
        data.ndx_open = float(f[5])
        data.ndx_high = float(f[6])
        data.ndx_low = float(f[7])
        data.ndx_volume = int(float(f[10])) if len(f) > 10 and f[10] else 0
        data.ndx_prev_close = float(f[26])
        data.ndx_time = f[3]
    except (SinaError, (ValueError, IndexError)) as e:
        data.ok = False
        data.error = f"gb_ndx 解析失败: {e}"
        return data

    try:
        # ---- gn0701159: CPO概念 ----
        # [1]今开 [2]昨收 [3]收盘 [4]最高 [5]最低 [8]成交量 [9]成交额 [30]日期
        f = _parse_field(text, "gn0701159")
        data.cpo_open = float(f[1])
        data.cpo_prev_close = float(f[2])
        data.cpo_price = float(f[3])
        data.cpo_high = float(f[4])
        data.cpo_low = float(f[5])
        data.cpo_volume = int(float(f[8])) if len(f) > 8 and f[8] else 0
        data.cpo_amount = float(f[9]) if len(f) > 9 and f[9] else 0.0
        data.cpo_change_pct = _compute_change(data.cpo_price, data.cpo_prev_close)
        data.cpo_date = f[30] if len(f) > 30 else ""
    except SinaError:
        data.cpo_error = True

    try:
        # ---- hf_VX: VIX恐慌指数期货 ----
        # [0]收盘 [4]最高 [5]最低 [7]昨收 [8]今开
        f = _parse_field(text, "hf_VX")
        data.vix = float(f[0])
        data.vix_high = float(f[4])
        data.vix_low = float(f[5])
        data.vix_prev_close = float(f[7])
        data.vix_open = float(f[8]) if len(f) > 8 and f[8] else 0.0
    except SinaError:
        pass

    try:
        # ---- fx_susdcnh: 汇率 ----
        # [1]收盘 [3]昨收 [5]今开 [6]最高 [7]最低
        f = _parse_field(text, "fx_susdcnh")
        data.fx_price = float(f[1])
        data.fx_prev_close = float(f[3])
        data.fx_open = float(f[5]) if len(f) > 5 and f[5] else 0.0
        data.fx_high = float(f[6]) if len(f) > 6 and f[6] else 0.0
        data.fx_low = float(f[7]) if len(f) > 7 and f[7] else 0.0
        data.fx_change_pct = _compute_change(data.fx_price, data.fx_prev_close)
    except SinaError:
        pass

    try:
        # ---- hf_NQ: 纳指期货 ----
        # [0]收盘 [4]最高 [5]最低 [8]今开
        f = _parse_field(text, "hf_NQ")
        data.nq_price = float(f[0])
        data.nq_high = float(f[4])
        data.nq_low = float(f[5])
        data.nq_open = float(f[8]) if len(f) > 8 and f[8] else 0.0
    except SinaError:
        pass

    try:
        # ---- gb_$sox: 费城半导体（备用） ----
        m = re.search(r'hq_str_gb_.sox="([^"]*)"', text)
        if m:
            f = m.group(1).split(",")
            data.sox_change_pct = float(f[2])
    except (ValueError, IndexError):
        pass

    return data
