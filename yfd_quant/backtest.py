"""历史回测引擎 —— 基于 snapshot 表的 14:50 决策数据

用法:
  python -m yfd_quant.backtest                          # 使用模型金额回测
  python -m yfd_quant.backtest --dca-amount 50          # 指定固定 DCA 金额
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

from yfd_quant.data.db import _get_conn

OUTPUT_DIR = "output"


def load_snapshot_data():
    """从 snapshot 表加载 14:50 决策数据"""
    conn = _get_conn()
    df = pd.read_sql(
        "SELECT date, sbi, amount, r_cpo, r_nq, r_fx, vix, "
        "ndx_close_prev, p_est, base, M, M_min "
        "FROM snapshot ORDER BY date",
        conn
    )
    conn.close()
    if df.empty:
        raise RuntimeError("snapshot 表为空，请先运行模型生成快照")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df.set_index("date", inplace=True)
    return df


def load_fund_nav():
    """加载基金净值数据"""
    conn = _get_conn()
    df = pd.read_sql("SELECT date, nav FROM fund_nav ORDER BY date", conn)
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
        df.set_index("date", inplace=True)
    return df


def run_backtest_from_snapshot(dca_amount=None):
    """基于 snapshot 表数据回测，避免未来幻觉

    Args:
        dca_amount: 固定 DCA 每日金额。None 则使用模型建议金额。
    """
    snapshot = load_snapshot_data()
    fund = load_fund_nav()

    print(f"Snapshot records: {len(snapshot)}")
    print(f"Fund NAV records: {len(fund)}")
    print(f"Date range: {snapshot.index[0].date()} ~ {snapshot.index[-1].date()}")

    # 交易日 = snapshot ∩ fund（需要净值才能计算份额）
    valid_dates = sorted(set(snapshot.index) & set(fund.index))
    if len(valid_dates) < 1:
        raise RuntimeError(f"No valid dates (snapshot ∩ fund_nav)")

    shares = 0.0
    total_cost = 0.0
    records = []
    skipped = 0
    skipped_reasons = []

    for date in valid_dates:
        snap = snapshot.loc[date]
        # 使用固定金额或模型建议金额
        if dca_amount is not None:
            amount = dca_amount
        else:
            amount = float(snap["amount"])
        nav = float(fund.loc[date, "nav"])

        if nav <= 0:
            skipped += 1
            skipped_reasons.append(f"{date.date()} 无基金净值")
            continue

        # 定投模拟
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
            "sbi": float(snap["sbi"]),
            "amount": round(amount, 2),
            "bought": round(bought, 6),
            "shares": round(shares, 6),
            "total_cost": round(total_cost, 2),
            "avg_cost": round(avg_cost, 4),
            "market_value": round(mkt_val, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "r_cpo": float(snap["r_cpo"]),
            "r_nq": float(snap["r_nq"]),
            "r_fx": float(snap["r_fx"]),
            "base": float(snap["base"]),
        })

    return pd.DataFrame(records), skipped, skipped_reasons


def compute_benchmarks(records, dca_amount=None):
    """计算基准收益

    Args:
        records: 回测记录
        dca_amount: 固定 DCA 每日金额。None 则从 snapshot 第一天的 M_min 获取。
    """
    if records.empty:
        return {"model_cumulative_return": 0, "fixed_dca_return": 0,
                "trade_count": 0, "total_invested": 0}

    model_return = records["pnl_pct"].iloc[-1]
    total_invested = records["total_cost"].iloc[-1]
    model_pnl = records["pnl"].iloc[-1]

    # 合成基准：35%光模块 + 55%纳指 + 10%汇率
    synthetic_return = 0.0
    if len(records) > 1:
        w_cpo, w_nq, w_fx = 0.35, 0.55, 0.10
        daily_syn = []
        for i in range(1, len(records)):
            syn_r = (w_cpo * records["r_cpo"].iloc[i] +
                     w_nq  * records["r_nq"].iloc[i] +
                     w_fx  * records["r_fx"].iloc[i]) / 100.0
            daily_syn.append(syn_r)
        cum = 1.0
        for r in daily_syn:
            cum *= (1 + r)
        synthetic_return = round((cum - 1) * 100, 2)

    # 固定 DCA 基准
    fixed_dca_return = 0.0
    fixed_dca_amount = dca_amount
    if fixed_dca_amount is None:
        # 默认使用 20 元（一天限额）
        fixed_dca_amount = 20.0
    if fixed_dca_amount and fixed_dca_amount > 0:
        f_shares, f_cost = 0.0, 0.0
        for _, r in records.iterrows():
            nav = r["nav"]
            if nav > 0:
                f_shares += fixed_dca_amount / nav
                f_cost += fixed_dca_amount
        if f_cost > 0:
            last_nav = records["nav"].iloc[-1]
            fixed_dca_return = round((f_shares * last_nav - f_cost) / f_cost * 100, 2)

    return {
        "model_cumulative_return": round(model_return, 2),
        "model_total_pnl": round(model_pnl, 2),
        "fixed_dca_return": fixed_dca_return,
        "fixed_dca_amount": fixed_dca_amount,
        "synthetic_benchmark_return": synthetic_return,
        "trade_count": len(records),
        "total_invested": round(total_invested, 2),
    }


def compute_stats(records):
    """计算风险指标"""
    if records.empty or len(records) < 2:
        return {}

    # 1. 每日真实收益率（基于市值和资金流）
    daily_returns = []
    for i in range(1, len(records)):
        prev_mv = records["market_value"].iloc[i-1]
        cur_mv  = records["market_value"].iloc[i]
        inflow  = records["amount"].iloc[i]
        denom = prev_mv + inflow
        if denom > 0:
            daily_returns.append((cur_mv - prev_mv - inflow) / denom)
        else:
            daily_returns.append(0.0)

    if len(daily_returns) < 2:
        return {}

    avg = np.mean(daily_returns)
    std = np.std(daily_returns, ddof=1)
    sharpe = (avg / std * np.sqrt(252)) if std > 0 else 0

    # 2. 最大回撤：基于单位净值（market_value / shares）
    shares_arr = records["shares"].values.astype(float)
    mv_arr = records["market_value"].values.astype(float)
    unit_nav = np.divide(mv_arr, shares_arr, out=np.full_like(mv_arr, np.nan),
                         where=shares_arr > 0)
    valid_mask = ~np.isnan(unit_nav)
    if valid_mask.any():
        first_valid = unit_nav[valid_mask][0]
        unit_nav = np.where(np.isnan(unit_nav), first_valid, unit_nav)
    else:
        first_valid = records["nav"].iloc[0]
        unit_nav = np.full_like(mv_arr, first_valid)

    peak = np.maximum.accumulate(unit_nav)
    dd = (unit_nav - peak) / peak
    max_dd = abs(float(np.nanmin(dd))) * 100

    # 3. 胜率与盈亏比
    wins = sum(1 for r in daily_returns if r > 0)
    total = len(daily_returns)
    wr = wins / total * 100 if total > 0 else 0
    avg_win = np.mean([r for r in daily_returns if r > 0]) if wins > 0 else 0
    avg_loss = abs(np.mean([r for r in daily_returns if r < 0])) if (total - wins) > 0 else 1
    pf = avg_win / avg_loss if avg_loss > 0 else 0

    # 交易日过少时夏普标记为 N/A
    if len(records) < 10:
        sharpe = None

    return {
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "avg_daily_return": round(avg, 4),
    }


def generate_report(records, benchmarks, stats, skipped, output_dir="output"):
    """生成回测报告"""
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

        # 固定 DCA 基准线
        fixed_dca_val = benchmarks.get("fixed_dca_return", 0)
        fixed_dca_amt = benchmarks.get("fixed_dca_amount")
        if fixed_dca_val != 0 and fixed_dca_amt:
            plt.axhline(y=fixed_dca_val, linestyle="--",
                        label=f"Fixed DCA ({fixed_dca_amt:.0f}元/日, {fixed_dca_val:.1f}%)")

        # 合成基准线
        syn_val = benchmarks.get("synthetic_benchmark_return", 0)
        if syn_val != 0:
            plt.axhline(y=syn_val, linestyle="-.",
                        label=f"Synthetic Benchmark ({syn_val:.1f}%)")

        plt.axhline(y=0, color="black", linewidth=0.5)
        plt.xlabel("Date"); plt.ylabel("Cumulative Return (%)")
        plt.title(f"Backtest | Sharpe={stats.get('sharpe') or 'N/A'} MaxDD={stats.get('max_drawdown','--')}%")
        plt.legend(); plt.xticks(rotation=45); plt.tight_layout()
        plt.savefig(f"{output_dir}/backtest_chart.png", dpi=150)
        plt.close()
        print(f"Chart: {output_dir}/backtest_chart.png")
    except ImportError:
        pass

    # Summary
    fixed_dca_amt = benchmarks.get("fixed_dca_amount")
    fixed_dca_label = f"Fixed DCA (每日{fixed_dca_amt:.0f}元)" if fixed_dca_amt else "Fixed DCA"

    with open(f"{output_dir}/backtest_summary.md", "w", encoding="utf-8") as f:
        f.write(f"""# Backtest Summary

**Period**: {records['date'].iloc[0]} ~ {records['date'].iloc[-1]}
**Trades**: {benchmarks.get('trade_count', 0)} | **Skipped**: {skipped}
**Data Source**: snapshot 表（14:50 决策时刻数据，无未来幻觉）

## Returns
| Metric | Value |
|--------|-------|
| Model Cumulative Return | {benchmarks.get('model_cumulative_return', 0)}% |
| {fixed_dca_label} | {benchmarks.get('fixed_dca_return', 0)}% |
| Synthetic Benchmark (35%CPO+55%NDX+10%FX) | {benchmarks.get('synthetic_benchmark_return', 0)}% |
| Total Invested | {benchmarks.get('total_invested', 0)} CNY |
| Total PnL | {benchmarks.get('model_total_pnl', 0)} CNY |

## Risk
| Metric | Value |
|--------|-------|
| Sharpe Ratio | {stats.get('sharpe') or 'N/A'} |
| Max Drawdown | {stats.get('max_drawdown', '--')}% |
| Win Rate | {stats.get('win_rate', '--')}% |
| Profit Factor | {stats.get('profit_factor', '--')} |
""")
    print(f"Summary: {output_dir}/backtest_summary.md")


def main():
    p = argparse.ArgumentParser(description="YFD Quant Backtest (基于 snapshot 表)")
    p.add_argument("--dca-amount", type=float, default=None,
                   help="固定 DCA 每日定投金额（元），不传则使用模型底仓 M_min")
    args = p.parse_args()

    print("Loading snapshot data...")
    records, skipped, reasons = run_backtest_from_snapshot(dca_amount=args.dca_amount)

    if records.empty:
        print("No valid trades.")
        sys.exit(1)

    benchmarks = compute_benchmarks(records, dca_amount=args.dca_amount)
    stats = compute_stats(records)

    print(f"\nTrades: {len(records)} | Skipped: {skipped} | "
          f"Return: {benchmarks['model_cumulative_return']}%")
    print(f"Sharpe: {stats.get('sharpe') or 'N/A'} | MaxDD: {stats.get('max_drawdown','--')}%")
    if benchmarks.get('fixed_dca_amount'):
        print(f"Fixed DCA: {benchmarks['fixed_dca_amount']:.0f}元/日 → {benchmarks['fixed_dca_return']}%")

    generate_report(records, benchmarks, stats, skipped, "output")


if __name__ == "__main__":
    main()
