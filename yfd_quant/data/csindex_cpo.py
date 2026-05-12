"""中证指数 API — 通信设备指数 (931160) 作为 CPO 替代数据源

相比 Sina gn0701159，中证指数返回更完整的 OHLC + change/changePct。
"""

import requests

URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf-oneday?indexCode=931160"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.csindex.com.cn/",
}


class CsindexError(Exception):
    """中证指数 API 错误"""


def fetch_cpo() -> dict | None:
    """获取通信设备指数 (931160) 当日表现

    Returns:
        {"tradeDate": str, "open": float, "prevClose": float,
         "close": float, "high": float?, "low": float?,
         "change": float, "changePct": float,
         "volume": float?, "amount": float?}
        失败返回 None
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.csindex.com.cn/", timeout=10)
        resp = session.get(URL, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("code") != "200":
            return None
        h = data["data"]["intraDayHeader"]
        return {
            "tradeDate": h.get("tradeDate", ""),
            "open": float(h.get("openToday", 0)),
            "prevClose": float(h.get("closePre", 0)),
            "close": float(h.get("current", 0)),
            "high": float(h.get("current", 0)),  # 接口无日内最高，用 current 近似
            "low": float(h.get("current", 0)),
            "change": float(h.get("change", 0)),
            "changePct": float(h.get("changePct", 0)),
            "volume": float(h.get("tradingVol", 0)) if h.get("tradingVol") else 0,
            "amount": float(h.get("tradingValue", 0)) if h.get("tradingValue") else 0,
        }
    except (requests.RequestException, (ValueError, KeyError, TypeError)):
        return None
