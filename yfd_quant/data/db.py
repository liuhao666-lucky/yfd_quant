"""SQLite 数据库 —— NDX 纳斯达克100 + CPO 概念板块历史日线存储

表: ndx_daily (date, open, high, low, close, volume)
表: cpo_daily (date, close)  — 用于计算 CPO MA20，判断主跌浪
"""

import sqlite3
import csv
from pathlib import Path
from typing import Optional

import pandas as pd

DB_PATH = Path(__file__).parent.parent.parent / "output" / "quant.db"

# NDX 表
CREATE_NDX = (
    "CREATE TABLE IF NOT EXISTS ndx_daily ("
    "date TEXT PRIMARY KEY, "
    "open REAL NOT NULL, "
    "high REAL NOT NULL, "
    "low REAL NOT NULL, "
    "close REAL NOT NULL, "
    "volume INTEGER DEFAULT 0)"
)
INSERT_NDX = (
    "INSERT OR REPLACE INTO ndx_daily (date, open, high, low, close, volume) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

# CPO 表
CREATE_CPO = (
    "CREATE TABLE IF NOT EXISTS cpo_daily ("
    "date TEXT PRIMARY KEY, "
    "close REAL NOT NULL)"
)
INSERT_CPO = "INSERT OR REPLACE INTO cpo_daily (date, close) VALUES (?, ?)"

# NQ 期货表
CREATE_NQ = (
    "CREATE TABLE IF NOT EXISTS nq_daily ("
    "date TEXT PRIMARY KEY, "
    "close REAL NOT NULL)"
)
INSERT_NQ = "INSERT OR REPLACE INTO nq_daily (date, close) VALUES (?, ?)"

# 验证表 — T+2 QDII 基金: T日15:00前申购 → 净值按T日美股收盘
# 核心检验: P_est 预测精度 + 入场日收益(SBI高分日是否真便宜)
CREATE_VALIDATION = (
    "CREATE TABLE IF NOT EXISTS validation ("
    "date TEXT PRIMARY KEY, "             # 模型运行日期 (T日)
    "sbi REAL, amount REAL, "
    "r_cpo REAL, r_nq REAL, r_fx REAL, vix REAL, "
    "c_prev REAL, p_est REAL, "          # C_{t-1}, 预估开盘价
    "base REAL, omega_ext REAL, omega_bias REAL, omega_pos REAL, rsi_bonus REAL, "
    "phi REAL, tau_adx REAL, omega_vol REAL, "
    "bias_pct REAL, rsi REAL, adx REAL, "
    "ndx_actual_open REAL, "             # T日纳指100实际开盘
    "ndx_actual_close REAL, "            # T日纳指100实际收盘 (决定基金净值)
    "p_est_deviation REAL, "             # P_est偏差 = (实际开-P_est)/P_est*100; 正=低估 负=高估
    "entry_return REAL, "               # 入场日涨跌 = (T收-T-1收)/T-1收*100; 负=买到跌=划算
    "forward_return REAL)"               # 买入后收益 = (次日收-T收)/T收*100; 正=买入后涨了
)
INSERT_VALIDATION = (
    "INSERT OR REPLACE INTO validation "
    "(date, sbi, amount, r_cpo, r_nq, r_fx, vix, c_prev, p_est, "
    "base, omega_ext, omega_bias, omega_pos, rsi_bonus, "
    "phi, tau_adx, omega_vol, bias_pct, rsi, adx) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
UPDATE_VALIDATION = (
    "UPDATE validation SET ndx_actual_open=?, ndx_actual_close=?, "
    "p_est_deviation=?, entry_return=?, forward_return=? WHERE date=?"
)


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_NDX)
    conn.execute(CREATE_CPO)
    conn.execute(CREATE_NQ)
    conn.execute(CREATE_FUND)
    conn.execute(CREATE_VALIDATION)
    conn.commit()
    return conn


def insert_daily(date, open_, high, low, close, volume=0):
    conn = _get_conn()
    conn.execute(INSERT_NDX, (date, open_, high, low, close, volume))
    conn.commit()
    conn.close()


def get_all():
    conn = _get_conn()
    df = pd.read_sql("SELECT * FROM ndx_daily ORDER BY date", conn)
    conn.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def count():
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM ndx_daily").fetchone()
    conn.close()
    return row[0] if row else 0


def latest():
    conn = _get_conn()
    row = conn.execute(
        "SELECT date, open, high, low, close, volume "
        "FROM ndx_daily ORDER BY date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(["date", "open", "high", "low", "close", "volume"], row))


def import_from_sina_kline(raw_data: str) -> int:
    """从 Sina 日K线格式批量导入

    格式: timestamp,date,open,close,volume,high,low,--,change,change%,--,ma5,ma10,vol_ma10,...
    记录间用分号分隔

    Returns:
        导入行数
    """
    conn = _get_conn()
    n = 0

    for record in raw_data.split(";"):
        record = record.strip()
        if not record:
            continue
        fields = record.split(",")
        if len(fields) < 7:
            continue

        try:
            date = fields[1]
            op = float(fields[2])
            cl = float(fields[3])
            vol = int(float(fields[4]))
            hi = float(fields[5])
            lo = float(fields[6])

            if date and op > 0 and cl > 0:
                conn.execute(INSERT_NDX, (date, op, hi, lo, cl, vol))
                n += 1
        except (ValueError, IndexError):
            continue

    conn.commit()
    conn.close()
    return n


# ---- CPO 历史 ----

def insert_cpo_daily(date: str, close: float):
    conn = _get_conn()
    conn.execute(INSERT_CPO, (date, close))
    conn.commit()
    conn.close()


def get_cpo_ma20() -> tuple[float, float]:
    """获取 CPO 的 MA20 相关值用于主跌浪判断

    Returns:
        (ma20_yesterday, ma20_5days_ago)  — 都是基于昨天收盘的数据
        数据不足 21 天时返回 (0, 0)
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date, close FROM cpo_daily ORDER BY date DESC LIMIT 25"
    ).fetchall()
    conn.close()

    if len(rows) < 21:
        return 0.0, 0.0

    closes = [r[1] for r in rows]
    ma20_yesterday = sum(closes[1:21]) / 20
    ma20_5days_ago = sum(closes[5:25]) / 20 if len(closes) >= 25 else 0.0
    return ma20_yesterday, ma20_5days_ago


def get_cpo_latest_close() -> Optional[float]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT close FROM cpo_daily ORDER BY date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def cpo_count() -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM cpo_daily").fetchone()
    conn.close()
    return row[0] if row else 0


# ---- NQ 期货历史 ----

def insert_nq_daily(date: str, close: float):
    conn = _get_conn()
    conn.execute(INSERT_NQ, (date, close))
    conn.commit()
    conn.close()


def get_nq_last_two() -> list[float]:
    """获取 NQ 最近两天的收盘价，用于周末计算周五涨跌幅"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT close FROM nq_daily ORDER BY date DESC LIMIT 2"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_nq_prev_close() -> float:
    """获取最近一次保存的 NQ 期货收盘价（用于计算 R_NQ）"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT close FROM nq_daily ORDER BY date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


# 基金净值表 — 手动录入，作为验证基准
CREATE_FUND = (
    "CREATE TABLE IF NOT EXISTS fund_nav ("
    "date TEXT PRIMARY KEY, "
    "nav REAL NOT NULL,"
    "daily_return REAL)"
)
INSERT_FUND = "INSERT OR REPLACE INTO fund_nav (date, nav, daily_return) VALUES (?, ?, ?)"


def insert_fund_nav(date: str, nav: float, daily_return: float = 0):
    conn = _get_conn()
    conn.execute(INSERT_FUND, (date, nav, daily_return))
    conn.commit()
    conn.close()


def get_fund_navs() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date, nav, daily_return FROM fund_nav ORDER BY date"
    ).fetchall()
    conn.close()
    return [{"date": r[0], "nav": r[1], "daily_return": r[2]} for r in rows]


# ---- 验证记录 ----

def save_validation(date: str, result) -> None:
    """保存每日模型输出到验证表"""
    conn = _get_conn()
    conn.execute(INSERT_VALIDATION, (
        date, result.sbi, result.recommended_amount,
        result.r_cpo, result.r_nq, result.r_fx, result.vix,
        result.ndx_close_prev, result.p_est,
        result.layer2_base,
        result.alpha.omega_ext, result.alpha.omega_bias,
        result.alpha.omega_pos, result.alpha.rsi_bonus,
        result.tech.phi, result.tech.tau_adx, result.tech.omega_vol,
        result.alpha.bias_pct, result.indicators.rsi, result.indicators.adx,
    ))
    conn.commit()
    conn.close()


def update_actual(date: str, actual_open: float, actual_close: float) -> None:
    """补录 T 日纳指100实际开盘/收盘

    计算:
      p_est_deviation = (实际开 - P_est) / P_est * 100
        正数 = 实际开盘 > 预估 → P_est 低估了
        负数 = 实际开盘 < 预估 → P_est 高估了
      entry_return = (T日收 - T-1日收) / T-1日收 * 100
        入场日涨跌: 负=买到跌(划算), 正=买到涨(买贵了)
      forward_return = (T+1日收 - T日收) / T日收 * 100
        买入后涨跌: 正=买入后涨了(赚了), 负=买入后跌了
    """
    prev = _get_validation_row(date)
    if not prev:
        return
    p_est = prev["p_est"]
    c_prev = prev["c_prev"]
    deviation = ((actual_open - p_est) / p_est * 100) if p_est > 0 else 0
    entry_ret = ((actual_close - c_prev) / c_prev * 100) if c_prev > 0 else 0

    # forward_return: 查次日收盘
    conn = _get_conn()
    next_row = conn.execute(
        "SELECT close FROM ndx_daily WHERE date > ? ORDER BY date LIMIT 1",
        (date,)
    ).fetchone()
    fwd_ret = 0.0
    if next_row and actual_close > 0:
        next_close = next_row[0]
        fwd_ret = ((next_close - actual_close) / actual_close * 100)

    conn.execute(UPDATE_VALIDATION, (
        actual_open, actual_close,
        round(deviation, 2), round(entry_ret, 2), round(fwd_ret, 2),
        date))
    conn.commit()
    conn.close()


def get_pending_validations() -> list[dict]:
    """获取尚未补录实际数据的记录"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date, p_est, c_prev FROM validation "
        "WHERE ndx_actual_open IS NULL ORDER BY date"
    ).fetchall()
    conn.close()
    return [{"date": r[0], "p_est": r[1], "c_prev": r[2]} for r in rows]


def _get_validation_row(date: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT p_est, c_prev FROM validation WHERE date=?", (date,)
    ).fetchone()
    conn.close()
    return {"p_est": row[0], "c_prev": row[1]} if row else None


def get_validation_stats() -> dict:
    """汇总验证统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT p_est_deviation, entry_return, forward_return, sbi, "
        "p_est, ndx_actual_open, c_prev, ndx_actual_close, date "
        "FROM validation WHERE p_est_deviation IS NOT NULL"
    ).fetchall()
    conn.close()
    if not rows:
        return {"count": 0, "details": []}

    deviations = [r[0] for r in rows]
    entry_rets = [r[1] for r in rows]
    fwd_rets = [r[2] for r in rows if r[2] is not None and r[2] != 0]
    sbis = [r[3] for r in rows]

    details = []
    for r in rows:
        detail = {
            "date": r[8],
            "p_est": r[4], "actual_open": r[5],
            "c_prev": r[6], "actual_close": r[7],
            "deviation": r[0], "entry_return": r[1],
            "forward_return": r[2], "sbi": r[3],
        }
        # 计算过程文案
        detail["deviation_calc"] = (
            f"({r[5]:.1f} - {r[4]:.1f}) / {r[4]:.1f} * 100 = {r[0]:+.2f}%"
        )
        detail["entry_calc"] = (
            f"({r[7]:.1f} - {r[6]:.1f}) / {r[6]:.1f} * 100 = {r[1]:+.2f}%"
        )
        details.append(detail)

    buckets = {"low": [], "mid": [], "high": []}
    for s, ret in zip(sbis, entry_rets):
        if s < 30: buckets["low"].append(ret)
        elif s < 70: buckets["mid"].append(ret)
        else: buckets["high"].append(ret)

    return {
        "count": len(rows),
        "p_est_mae": sum(abs(d) for d in deviations) / len(deviations),
        "p_est_bias": sum(deviations) / len(deviations),
        "avg_entry_return": sum(entry_rets) / len(entry_rets),
        "avg_forward_return": sum(fwd_rets) / len(fwd_rets) if fwd_rets else 0,
        "sbi_buckets": {
            k: {"count": len(v), "avg_return": sum(v)/len(v) if v else 0}
            for k, v in buckets.items()
        },
        "details": details,
    }


# ---- CSV 导入 ----

def import_csv(csv_path):
    """从 CSV 导入历史数据

    支持两种 CSV 格式:
      1. date,open,high,low,close,volume
      2. 日期,开盘,最高,最低,收盘,成交量 (东方财富格式)

    Returns:
        导入行数
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    conn = _get_conn()
    n = 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("date") or row.get("日期", "")
            op = float(row.get("open") or row.get("开盘", 0))
            hi = float(row.get("high") or row.get("最高", 0))
            lo = float(row.get("low") or row.get("最低", 0))
            cl = float(row.get("close") or row.get("收盘", 0))
            vol = int(float(row.get("volume") or row.get("成交量", 0)))

            if date and op > 0 and cl > 0:
                conn.execute(INSERT_NDX, (date, op, hi, lo, cl, vol))
                n += 1

    conn.commit()
    conn.close()
    return n
