#!/usr/bin/env python3
"""基金信息查询工具 —— 获取净值、持仓、经理等详情（仅手动运行，不参与模型决策）

用途:
  - 查看基金基本信息、净值走势、业绩表现
  - 查看前十大持仓并计算美股/A股/港股占比
  - 保存近90日净值历史到 CSV
  - 根据持仓分布，辅助调整 config.yaml 中模型权重

依赖: pip install pandas requests

用法:
  python -m yfd_quant.fund_info                           # 默认查询 012922
  python -m yfd_quant.fund_info --fund-code 012922         # 指定基金代码
  python -m yfd_quant.fund_info --save-csv                 # 查询并保存净值 CSV
  python -m yfd_quant.fund_info --show-holdings            # 仅看持仓+市场占比
"""

import argparse
import json
import sys
import time
from datetime import datetime

import requests

# ---- 配置 ----
FUND_API_URL = "https://fund.sina.com.cn/fund/api/fundDetail"
HOME_URL = "https://fund.sina.cn/"
OUTPUT_DIR = "output"
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 3, 5]  # seconds


def _retry_request(method, url, session, **kwargs):
    """带重试的请求（3次，指数退避），Cookie失效时给出明确提示"""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.request(method, url, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                print(f"  请求超时，{wait}s 后重试 ({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                print("\n[Cookie 失效] 新浪基金接口要求登录态。请手动更新 Cookie：")
                print("  1. 浏览器访问 https://fund.sina.cn/ 并登录")
                print("  2. 打开开发者工具 → Application → Cookies")
                print("  3. 复制 INGRESSCOOKIE 值，更新本脚本中的 Cookie")
                raise
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                time.sleep(wait)

    raise last_error or RuntimeError("网络请求失败（已重试3次）")


def fetch_fund_detail(fundcode="012922"):
    """获取基金详情 JSON"""
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": "https://fund.sina.cn",
        "Referer": "https://fund.sina.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # Step 1: 首页获取 Cookie
    _retry_request("GET", HOME_URL, session)

    # Step 2: POST 基金详情
    payload = {"fundcode": fundcode, "type": "1,2,3,4,5",
               "openLoader": "true", "_": int(time.time() * 1000)}
    resp = _retry_request("POST", FUND_API_URL, session, data=payload)
    data = resp.json()

    if data.get("code") != 0:
        print(f"接口返回错误：{data.get('msg')}")
        return None
    return data


def _classify_market(code: str) -> str:
    """根据股票代码判断市场"""
    code = str(code).upper()
    if code.endswith((".US", ".OQ", ".N")):
        return "美股"
    if code.startswith(("SZ", "SH")) or code[:2].isdigit():
        return "A股"
    if code.startswith("HK") or code.endswith(".HK"):
        return "港股"
    # 纯字母代码，美股（如 TSM, LITE, AXTI, GLW, GOOGL, TSEM）
    if code.replace(".", "").isalpha() and len(code) <= 6:
        return "美股"
    return "其他"


def analyze_fund_data(data, show_holdings_only=False):
    """解析并打印基金数据"""
    if not data or "data" not in data:
        print("无有效数据")
        return None

    fd = data["data"]
    market = fd.get("market", {})
    base = market.get("base_info", {})
    history = market.get("history", [])
    achievement = market.get("achievement", [])
    positions = fd.get("element", {}).get("list", [])
    archive = fd.get("archive", {})
    manager = archive.get("manager", {})
    company = archive.get("company", {})

    if not show_holdings_only:
        print("\n" + "=" * 60)
        print("【基金基本信息】")
        print(f"  名称: {base.get('fundname', '--')}")
        print(f"  代码: {base.get('fundcode', '--')}")
        print(f"  净值: {base.get('netvalue', '--')} ({base.get('navdate', '--')})")
        print(f"  日涨跌: {base.get('dayincratio', '--')}%")
        print(f"  年初至今: {base.get('yearincratio', '--')}%")
        print(f"  类型: {base.get('fundtype_str', '--')} | 规模: {base.get('fundscale_format', '--')}")

        if history:
            print(f"\n【近5日净值】")
            for h in history[:5]:
                print(f"  {h['date']}  {h['netval']}  {h.get('day_rate','--')}%")

    # ---- 持仓分析 ----
    if positions:
        print("\n" + "=" * 60)
        print("【前十大持仓】")
        market_stats = {"美股": 0.0, "A股": 0.0, "港股": 0.0, "其他": 0.0}
        for i, p in enumerate(positions[:10], 1):
            name = p.get("name", "--")
            code = p.get("code", "--")
            rate = float(p.get("rate", 0))
            mkt = _classify_market(code)
            market_stats[mkt] += rate
            print(f"  {i:2d}. {name:20s} {code:12s} {rate:5.1f}%  [{mkt}]")

        print(f"\n  市场占比估算:")
        for mkt, pct in market_stats.items():
            if pct > 0:
                print(f"    {mkt}: {pct:.1f}%")
        print(f"\n  [!] 提示: 若持仓分布与模型权重 (CPO 25%/NQ 65%/FX 10%) 偏差较大,")
        print(f"      建议调整 config.yaml 中的权重以匹配实际持仓。")
    else:
        print("  暂无持仓数据")

    if not show_holdings_only:
        if manager:
            for mid, m in manager.items():
                print(f"\n【基金经理】{m.get('name','--')}")
                print(f"  任职: {m.get('rztime','--')}  任期回报: {m.get('TENUREYIELD','--')}%")
                break
        if company:
            print(f"\n【基金公司】{company.get('short_name','--')}")
            print(f"  规模: {company.get('netvalue','--')}  基金数: {company.get('fund_num','--')}")

    return {"base": base, "history": history, "positions": positions}


def get_latest_nav(fundcode="012922") -> dict | None:
    """获取最新净值信息（供定时任务自动写入 fund_nav 表）

    Returns: {"date": "2026-05-11", "nav": 1.2345, "daily_return": -0.0012} or None
    """
    data = fetch_fund_detail(fundcode)
    if not data:
        return None
    base = data["data"]["market"]["base_info"]
    nav = base.get("netvalue")
    navdate = base.get("navdate")
    dayinc = base.get("dayincratio")
    if not nav or not navdate:
        return None
    try:
        # Sina 返回的 navdate 是 MM-DD 格式，补全为 YYYY-MM-DD
        if len(navdate) == 5 and "-" in navdate:
            import datetime
            year = str(datetime.datetime.now().year)
            navdate = f"{year}-{navdate}"
        return {
            "date": navdate,
            "nav": float(nav),
            "daily_return": float(dayinc) / 100 if dayinc else 0.0,
        }
    except (ValueError, TypeError):
        return None


def save_nav_csv(history, fundcode):
    """保存近90日净值到 CSV"""
    import pandas as pd
    from pathlib import Path
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(history)
    df = df[["date", "netval", "day_rate"]]
    df.columns = ["date", "nav", "daily_return"]
    df["nav"] = df["nav"].astype(float)
    df["daily_return"] = df["daily_return"].astype(float) / 100  # 转小数
    df = df.head(90).sort_values("date")
    path = f"{OUTPUT_DIR}/fund_nav_history.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n近90日净值已保存: {path} ({len(df)}行)")
    print(f"导入模型: python -m yfd_quant.main --import-csv {path}")


def main():
    parser = argparse.ArgumentParser(description="基金信息查询工具")
    parser.add_argument("--fund-code", default="012922", help="基金代码 (默认 012922)")
    parser.add_argument("--save-csv", action="store_true", help="保存近90日净值到 CSV")
    parser.add_argument("--show-holdings", action="store_true",
                        help="仅显示前十大持仓及市场占比")
    args = parser.parse_args()

    print(f"查询基金: {args.fund_code}")
    data = fetch_fund_detail(args.fund_code)
    if not data:
        sys.exit(1)

    result = analyze_fund_data(data, show_holdings_only=args.show_holdings)

    if args.save_csv and result and result["history"]:
        try:
            import pandas as pd  # noqa: F811
            save_nav_csv(result["history"], args.fund_code)
        except ImportError:
            print("需要 pandas: pip install pandas")


if __name__ == "__main__":
    main()
