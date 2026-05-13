"""历史回测引擎 —— 严格前视偏差杜绝

用法:
  python -m yfd_quant.backtest -M 20 --min 0
  python -m yfd_quant.backtest -M 20 --min 0 --save-to-db
  python -m yfd_quant.backtest -M 50 --min 10 --discount 0.90 --skip-missing
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

from yfd_quant.data.db import get_all as get_ndx, _get_conn
from yfd_quant.types import MarketSnapshot
from yfd_quant.model.engine import QuantEngine

OUTPUT_DIR = "output"


def load_historical_data():
    """加载全部历史数据"""
    ndx = get_ndx()
    if ndx.empty:
        raise RuntimeError("NDX 历史为空，请先导入数据")

    conn = _get_conn()
    tables = {
        "cpo": "SELECT date, open, high, low, close, change_pct FROM cpo_daily ORDER BY date",
        "nq":  "SELECT date, open, high, low, close FROM nq_daily ORDER BY date",
        "vix": "SELECT date, open, high, low, close FROM vix_daily ORDER BY date",
        "fx":  "SELECT date, close FROM fx_daily ORDER BY date",
        "fund":"SELECT date, nav FROM fund_nav ORDER BY date",
    }
    data = {}
    for name, sql in tables.items():
        df = pd.read_sql(sql, conn)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
            df.set_index("date", inplace=True)
        data[name] = df
    conn.close()
    return ndx, data


def _get_change(df, date):
    """计算 date 当日的涨跌幅 = (当日close - 前日close) / 前日close * 100
    Returns (value, ok_flag). ok=False means data missing."""
    if date not in df.index:
        return 0.0, False
    idx = df.index.get_loc(date)
    if idx == 0:
        return 0.0, False
    prev_date = df.index[idx - 1]
    cur = float(df.loc[date, "close"])
    prev = float(df.loc[prev_date, "close"])
    if prev <= 0:
        return 0.0, False
    return round((cur - prev) / prev * 100, 2), True


def _get_cpo_change(df, date):
    """CPO change% 直接取 change_pct 字段（csindex 接口提供）"""
    if date not in df.index:
        return 0.0, False
    val = df.loc[date, "change_pct"]
    if pd.isna(val):
        return 0.0, False
    return float(val), True


def _get_change_fx(df, date):
    """FX change (4 decimal places)"""
    if date not in df.index:
        return 0.0, False
    idx = df.index.get_loc(date)
    if idx == 0:
        return 0.0, False
    prev_date = df.index[idx - 1]
    cur = float(df.loc[date, "close"])
    prev = float(df.loc[prev_date, "close"])
    if prev <= 0:
        return 0.0, False
    return round((cur - prev) / prev * 100, 4), True


def _get_value(df, date, col="close", default=0.0):
    """safe value lookup"""
    if date in df.index:
        return float(df.loc[date, col])
    return default


def run_backtest(M=20.0, M_min=0.0, tz_discount=0.85,
                 skip_missing=True, min_history=1):
    """主回测流程"""
    ndx, data = load_historical_data()
    cpo, nq, vix, fx, fund = data["cpo"], data["nq"], data["vix"], data["fx"], data["fund"]

    # 打印数据覆盖
    ndx_dates = f"{ndx.index[0].date()} ~ {ndx.index[-1].date()}"
    fund_n = len(fund)
    print(f"Data range: {ndx_dates}")
    print(f"  Fund NAV days: {fund_n}  CPO: {len(cpo)}  NQ: {len(nq)}  "
          f"VIX: {len(vix)}  FX: {len(fx)}")

    # 交易日 = NDX ∩ fund（需净值验证）
    valid_dates = sorted(set(ndx.index) & set(fund.index))
    if len(valid_dates) < 3:
        raise RuntimeError(f"Need >=3 valid dates, got {len(valid_dates)}")

    shares = 0.0
    total_cost = 0.0
    records = []
    skipped = 0
    skipped_reasons = []

    engine = QuantEngine()

    for date in valid_dates:
        # ---- 前视偏差杜绝: 只用 date 之前的数据做指标 ----
        ndx_before = ndx[ndx.index < date]
        if len(ndx_before) < 20:
            skipped += 1
            skipped_reasons.append(f"{date.date()} NDX历史不足20天")
            if skip_missing:
                continue
        if len(ndx_before) == 0:
            skipped += 1
            skipped_reasons.append(f"{date.date()} NDX历史为空")
            continue

        ndx_close_prev = float(ndx_before["close"].iloc[-1])

        # ---- 因子计算: CPO 直接用 change_pct ----
        r_cpo, cpo_ok = _get_cpo_change(cpo, date)
        r_nq, nq_ok = _get_change(nq, date)
        r_fx, fx_ok = _get_change_fx(fx, date)

        # VIX
        vix_val = _get_value(vix, date, "close", None)
        if vix_val is None:
            vix_before = vix[vix.index < date]
            if len(vix_before) > 0:
                vix_val = float(vix_before["close"].iloc[-1])
            else:
                vix_val = 15.0

        # 缺失检查
        missing = []
        if not cpo_ok:
            missing.append("CPO")
        if not nq_ok:
            missing.append("NQ")
        if not fx_ok:
            missing.append("FX")
        if missing:
            reason = f"{date.date()} 跳过: [{','.join(missing)}]无当日/前日数据"
            skipped += 1
            skipped_reasons.append(reason)
            print(f"  [回测] {reason}")
            if skip_missing:
                continue

        # ---- CPO 主跌浪 ----
        cpo_before = cpo[cpo.index < date]
        cpo_downtrend = False
        if len(cpo_before) >= 21:
            cpo_close = float(cpo.loc[date, "close"]) if date in cpo.index else 0
            ma20 = cpo_before["close"].iloc[-20:].mean()
            ma20_prev = cpo_before["close"].iloc[-21:-1].mean()
            cpo_downtrend = (cpo_close < ma20) and (ma20 < ma20_prev)

        snapshot = MarketSnapshot(
            timestamp=date.to_pydatetime(),
            r_cpo=r_cpo, r_nq=r_nq, r_fx=r_fx,
            cpo_close_today=float(cpo.loc[date, "close"]) if date in cpo.index else 0.0,
            cpo_ma20_yesterday=0.0, cpo_ma20_5days_ago=0.0,
            cpo_downtrend=cpo_downtrend,
            ndx_close_prev=ndx_close_prev,
            ndx_historical=ndx_before,
            vix=vix_val,
            indicators_ready=False,
            data_quality="full",
        )

        try:
            result = engine.run(snapshot, M=M, M_min=M_min,
                               timezone_discount=tz_discount)
        except (ValueError, ZeroDivisionError, KeyError, TypeError, OverflowError) as e:
            skipped += 1
            skipped_reasons.append(f"{date.date()} 模型计算异常: {e}")
            continue

        # ---- 定投模拟 ----
        amount = result.recommended_amount
        nav = _get_value(fund, date, "nav")
        if nav <= 0:
            skipped += 1
            skipped_reasons.append(f"{date.date()} 无基金净值")
            continue

        bought = amount / nav
        shares += bought
        total_cost += amount
        avg_cost = total_cost / shares if shares > 0 else 0
        mkt_val = shares * nav
        pnl = mkt_val - total_cost
        pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0

        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "nav": round(nav, 4),
            "sbi": result.sbi,
            "amount": round(amount, 2),
            "bought": round(bought, 6),
            "shares": round(shares, 6),
            "total_cost": round(total_cost, 2),
            "avg_cost": round(avg_cost, 4),
            "market_value": round(mkt_val, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "r_cpo": r_cpo, "r_nq": r_nq, "r_fx": r_fx,
            "base": result.layer2_base,
        })

    return (pd.DataFrame(records), ndx, fund,
            skipped, skipped_reasons)


def compute_benchmarks(records, ndx, fund, M_min=0.0):
    if records.empty:
        return {"model_cumulative_return": 0, "fixed_dca_return": 0,
                "ndx_buyhold_return": 0, "trade_count": 0, "total_invested": 0}

    model_return = records["pnl_pct"].iloc[-1]
    total_invested = records["total_cost"].iloc[-1]
    model_pnl = records["pnl"].iloc[-1]

    fixed_return = 0.0
    if M_min > 0:
        f_shares, f_cost = 0.0, 0.0
        for _, r in records.iterrows():
            nav = r["nav"]
            if nav > 0:
                f_shares += M_min / nav
                f_cost += M_min
        if f_cost > 0:
            last_nav = records["nav"].iloc[-1]
            fixed_return = round((f_shares * last_nav - f_cost) / f_cost * 100, 2)

    ndx_ret = 0.0
    if not ndx.empty and not records.empty:
        start_date = pd.Timestamp(records["date"].iloc[0])
        end_date = pd.Timestamp(records["date"].iloc[-1])
        ndx_period = ndx[(ndx.index >= start_date) & (ndx.index <= end_date)]
        if len(ndx_period) >= 2:
            first_close = float(ndx_period["close"].iloc[0])
            if first_close > 0:
                ndx_ret = round(
                    (float(ndx_period["close"].iloc[-1]) - first_close)
                    / first_close * 100, 2
                )

    return {
        "model_cumulative_return": round(model_return, 2),
        "model_total_pnl": round(model_pnl, 2),
        "fixed_dca_return": round(fixed_return, 2),
        "ndx_buyhold_return": ndx_ret,
        "trade_count": len(records),
        "total_invested": round(total_invested, 2),
    }


def compute_stats(records):
    if records.empty or len(records) < 2:
        return {}
    returns = records["pnl_pct"].diff().dropna().tolist()
    if len(returns) < 2:
        return {}
    avg = np.mean(returns)
    std = np.std(returns, ddof=1)
    sharpe = (avg / std * np.sqrt(252)) if std > 0 else 0

    # 最大回撤: 基于收益率曲线构造虚拟净值，排除定投资金干扰
    virtual_nav = 1.0 + (records["pnl_pct"].values.astype(float) / 100.0)
    if np.all(virtual_nav == virtual_nav[0]):
        max_dd = 0.0
    else:
        peak = np.maximum.accumulate(virtual_nav)
        mask = peak > 0
        if not mask.any():
            max_dd = 0.0
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                dd = np.where(mask, (virtual_nav - peak) / peak, 0.0)
            max_dd = abs(float(np.nanmin(dd))) * 100

    wins = sum(1 for r in returns if r > 0)
    total = len(returns)
    wr = wins / total * 100 if total > 0 else 0
    avg_win = np.mean([r for r in returns if r > 0]) if wins > 0 else 0
    avg_loss = abs(np.mean([r for r in returns if r < 0])) if (total - wins) > 0 else 1
    pf = avg_win / avg_loss if avg_loss > 0 else 0
    return {
        "sharpe": round(sharpe, 2), "max_drawdown": round(max_dd, 2),
        "win_rate": round(wr, 1), "profit_factor": round(pf, 2),
        "avg_daily_return": round(avg, 4),
    }


def generate_report(records, benchmarks, stats, skipped, output_dir="output"):
    import os
    os.makedirs(output_dir, exist_ok=True)

    # CSV
    csv_path = f"{output_dir}/backtest_records.csv"
    records.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV: {csv_path}")

    # Chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(12, 6))
        plt.plot(records["date"], records["pnl_pct"], label="Model DCA", linewidth=1.5)
        for lbl, val, ls in [("Fixed DCA", benchmarks.get("fixed_dca_return", 0), "--"),
                              ("NDX Buy&Hold", benchmarks.get("ndx_buyhold_return", 0), ":")]:
            if val != 0:
                plt.axhline(y=val, linestyle=ls, label=f"{lbl} ({val:.1f}%)")
        plt.axhline(y=0, color="black", linewidth=0.5)
        plt.xlabel("Date"); plt.ylabel("Cumulative Return (%)")
        plt.title(f"Backtest | Sharpe={stats.get('sharpe','--')} MaxDD={stats.get('max_drawdown','--')}%")
        plt.legend(); plt.xticks(rotation=45); plt.tight_layout()
        plt.savefig(f"{output_dir}/backtest_chart.png", dpi=150)
        plt.close()
        print(f"Chart: {output_dir}/backtest_chart.png")
    except ImportError:
        pass

    # Summary
    with open(f"{output_dir}/backtest_summary.md", "w", encoding="utf-8") as f:
        f.write(f"""# Backtest Summary

**Period**: {records['date'].iloc[0]} ~ {records['date'].iloc[-1]}
**Trades**: {benchmarks.get('trade_count', 0)} | **Skipped**: {skipped}

## Returns
| Metric | Value |
|--------|-------|
| Model Cumulative Return | {benchmarks.get('model_cumulative_return', 0)}% |
| Fixed DCA | {benchmarks.get('fixed_dca_return', 0)}% |
| NDX Buy & Hold | {benchmarks.get('ndx_buyhold_return', 0)}% |
| Total Invested | {benchmarks.get('total_invested', 0)} CNY |
| Total PnL | {benchmarks.get('model_total_pnl', 0)} CNY |

## Risk
| Metric | Value |
|--------|-------|
| Sharpe Ratio | {stats.get('sharpe', '--')} |
| Max Drawdown | {stats.get('max_drawdown', '--')}% |
| Win Rate | {stats.get('win_rate', '--')}% |
| Profit Factor | {stats.get('profit_factor', '--')} |
""")
    print(f"Summary: {output_dir}/backtest_summary.md")


def save_to_validation(records, ndx_df, M, M_min):
    from yfd_quant.data.db import save_validation, update_actual
    n = 0
    for _, r in records.iterrows():
        date_str = r["date"]
        try:
            dt = pd.Timestamp(date_str)
            prev = ndx_df[ndx_df.index < dt]
            c_prev = float(prev["close"].iloc[-1]) if len(prev) > 0 else 0.0
            p_est = round(c_prev * (1 + r["r_nq"] / 100), 2) if c_prev > 0 else 0.0

            result_mock = type("R", (), {
                "sbi": r["sbi"], "recommended_amount": r["amount"],
                "r_cpo": r["r_cpo"], "r_nq": r["r_nq"], "r_fx": r["r_fx"],
                "vix": 0.0, "ndx_close_prev": c_prev, "p_est": p_est,
                "layer2_base": r["base"], "M": M, "M_min": M_min,
                "alpha": type("A", (), dict(omega_ext=0, omega_bias=0, omega_pos=0,
                    rsi_bonus=0, bias_pct=0.0, p_pos=0.0))(),
                "tech": type("T", (), dict(phi=1.0, tau_adx=1.0, omega_vol=1.0,
                    gap=0, strong_downtrend=False))(),
                "indicators": type("I", (), dict(rsi=50.0, adx=0.0, ma20=0, ma200=0,
                    high_52w=0, low_52w=0, atr14=0, di_plus=0, di_minus=0))(),
            })()
            save_validation(date_str, result_mock)
            if date_str in ndx_df.index:
                update_actual(date_str, float(ndx_df.loc[date_str, "open"]),
                              float(ndx_df.loc[date_str, "close"]))
            n += 1
        except Exception:
            pass
    print(f"Saved {n} validation entries to DB")


def main():
    p = argparse.ArgumentParser(description="YFD Quant Backtest")
    p.add_argument("-M", type=float, default=20.0)
    p.add_argument("--min", type=float, default=0.0, dest="M_min")
    p.add_argument("--discount", type=float, default=0.85)
    p.add_argument("-o", "--output", default="output")
    p.add_argument("--save-to-db", action="store_true")
    p.add_argument("--skip-missing", action="store_true", default=True,
                   help="Skip dates with missing data (default)")
    p.add_argument("--allow-zero-fill", action="store_true",
                   help="Allow zero-fill for missing factors (overrides skip-missing)")
    args = p.parse_args()

    skip = args.skip_missing and not args.allow_zero_fill

    print("Loading data...")
    records, ndx, fund, skipped, reasons = run_backtest(
        M=args.M, M_min=args.M_min, tz_discount=args.discount,
        skip_missing=skip)

    if records.empty:
        print("No valid trades.")
        sys.exit(1)

    benchmarks = compute_benchmarks(records, ndx, fund, args.M_min)
    stats = compute_stats(records)

    print(f"\nTrades: {len(records)} | Skipped: {skipped} | "
          f"Return: {benchmarks['model_cumulative_return']}%")
    print(f"Sharpe: {stats.get('sharpe','--')} | MaxDD: {stats.get('max_drawdown','--')}%")

    generate_report(records, benchmarks, stats, skipped, args.output)

    if args.save_to_db:
        save_to_validation(records, get_ndx(), args.M, args.M_min)


if __name__ == "__main__":
    main()
