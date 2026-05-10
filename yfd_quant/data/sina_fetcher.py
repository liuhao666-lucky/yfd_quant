"""新浪财经 hq.sinajs.cn —— 批量一次性抓取全部数据

一次 HTTP 请求获取: 纳指100、CPO概念、VIX、汇率、纳指期货、费城半导体

字段映射（Postman 验证）:
  gb_ndx   [1]收盘 [2]涨跌幅% [5]今开 [6]最高 [7]最低 [26]昨收
  gn0701159 [1]今开 [2]昨收 [3]收盘 [4]最高 [5]最低
  hf_VX    [0]最新价
  fx_susdcnh [0]时间 [1]今收 [2]今开 [3]昨收
  hf_NQ    [0]实时价 [2]昨收
  gb_$sox  [2]涨跌幅%（备用）
"""

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
    ndx_price: float = 0.0       # 最新价
    ndx_change_pct: float = 0.0  # 涨跌幅%
    ndx_open: float = 0.0        # 今开
    ndx_high: float = 0.0        # 最高
    ndx_low: float = 0.0         # 最低
    ndx_prev_close: float = 0.0  # 昨收 (fields[26])
    ndx_time: str = ""

    # CPO概念 (gn0701159)
    cpo_price: float = 0.0       # 最新点位
    cpo_prev_close: float = 0.0  # 昨收点位
    cpo_change_pct: float = 0.0  # 涨跌幅%（自算）
    cpo_date: str = ""

    # VIX (hf_VX)
    vix: float = 0.0

    # 汇率 (fx_susdcnh)
    fx_price: float = 0.0        # 最新价
    fx_prev_close: float = 0.0   # 昨收
    fx_change_pct: float = 0.0   # 涨跌幅%（自算）

    # 纳指期货 (hf_NQ) — 仅参考
    nq_future: float = 0.0

    # 费城半导体 (gb_$sox) — 备用
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
        data.ndx_prev_close = float(f[26])
        data.ndx_time = f[3]
    except (SinaError, (ValueError, IndexError)) as e:
        data.ok = False
        data.error = f"gb_ndx 解析失败: {e}"
        return data

    try:
        # ---- gn0701159: CPO概念 ----
        # A股概念板块: [0]名称 [1]今开 9133.71 [2]昨收 9310.56 [3]收盘 9427.95 [4]最高 [5]最低
        f = _parse_field(text, "gn0701159")
        data.cpo_prev_close = float(f[2])  # 昨收
        data.cpo_price = float(f[3])       # 收盘
        data.cpo_change_pct = _compute_change(data.cpo_price, data.cpo_prev_close)
        data.cpo_date = f[30] if len(f) > 30 else ""
    except SinaError:
        pass

    try:
        # ---- hf_VX: VIX ----
        f = _parse_field(text, "hf_VX")
        data.vix = float(f[0])
    except SinaError:
        pass

    try:
        # ---- fx_susdcnh: 汇率 ----
        # [0]时间 [1]今收 6.794 [2]今开 6.7979 [3]昨收 6.795
        f = _parse_field(text, "fx_susdcnh")
        data.fx_price = float(f[1])       # 今收
        data.fx_prev_close = float(f[3])  # 昨收
        data.fx_change_pct = _compute_change(data.fx_price, data.fx_prev_close)
    except SinaError:
        pass

    try:
        # ---- hf_NQ: 纳指期货（仅参考） ----
        f = _parse_field(text, "hf_NQ")
        data.nq_future = float(f[0])
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
