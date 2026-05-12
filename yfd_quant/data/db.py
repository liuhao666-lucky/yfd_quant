"""SQLite 数据库 —— 所有表统含 operate_time 操作时间戳

表:
  ndx_daily   - 纳指100日线 (O/H/L/C/V)
  cpo_daily   - A股光模块收盘
  nq_daily    - 纳指期货收盘
  validation  - 模型检验
  fund_nav    - 基金净值

规则: date=交易日期, operate_time=实际入库北京时间 YYYY-MM-DD HH:MM:SS
  T日收盘 → T+1 05:15 抓取 → date=T, operate_time=T+1 05:15
"""

import sqlite3
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

DB_PATH = Path(__file__).parent.parent.parent / "output" / "quant.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ========== NDX 纳指100日线 ==========
CREATE_NDX = (
    "CREATE TABLE IF NOT EXISTS ndx_daily ("
    "date TEXT PRIMARY KEY, "
    "open REAL NOT NULL, "
    "high REAL NOT NULL, "
    "low REAL NOT NULL, "
    "close REAL NOT NULL, "
    "volume INTEGER DEFAULT 0, "
    "operate_time TEXT NOT NULL)"
)
INSERT_NDX = (
    "INSERT OR REPLACE INTO ndx_daily "
    "(date, open, high, low, close, volume, operate_time) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

# ========== CPO A股光模块 ==========
CREATE_CPO = (
    "CREATE TABLE IF NOT EXISTS cpo_daily ("
    "date TEXT PRIMARY KEY, "
    "open REAL NOT NULL, "
    "high REAL NOT NULL, "
    "low REAL NOT NULL, "
    "close REAL NOT NULL, "
    "change REAL NOT NULL, "
    "change_pct REAL NOT NULL, "
    "operate_time TEXT NOT NULL)"
)
INSERT_CPO = (
    "INSERT OR REPLACE INTO cpo_daily "
    "(date, open, high, low, close, change, change_pct, operate_time) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

# ========== NQ 纳指期货 ==========
CREATE_NQ = (
    "CREATE TABLE IF NOT EXISTS nq_daily ("
    "date TEXT PRIMARY KEY, "
    "open REAL NOT NULL, "
    "high REAL NOT NULL, "
    "low REAL NOT NULL, "
    "close REAL NOT NULL, "
    "operate_time TEXT NOT NULL, "
    "is_final INTEGER DEFAULT 0)"
)
INSERT_NQ = (
    "INSERT OR REPLACE INTO nq_daily "
    "(date, open, high, low, close, operate_time, is_final) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

# ========== USDCNH 离岸人民币 ==========
CREATE_FX = (
    "CREATE TABLE IF NOT EXISTS fx_daily ("
    "date TEXT PRIMARY KEY, "
    "close REAL NOT NULL, "
    "operate_time TEXT NOT NULL, "
    "is_final INTEGER DEFAULT 0)"
)
INSERT_FX = (
    "INSERT OR REPLACE INTO fx_daily (date, close, operate_time, is_final) "
    "VALUES (?, ?, ?, ?)"
)

# ========== VIX 恐慌指数期货 ==========
CREATE_VIX = (
    "CREATE TABLE IF NOT EXISTS vix_daily ("
    "date TEXT PRIMARY KEY, "
    "open REAL NOT NULL, "
    "high REAL NOT NULL, "
    "low REAL NOT NULL, "
    "close REAL NOT NULL, "
    "operate_time TEXT NOT NULL, "
    "is_final INTEGER DEFAULT 0)"
)
INSERT_VIX = (
    "INSERT OR REPLACE INTO vix_daily "
    "(date, open, high, low, close, operate_time, is_final) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

# ========== 验证表 ==========
CREATE_VALIDATION = (
    "CREATE TABLE IF NOT EXISTS validation ("
    "date TEXT PRIMARY KEY, "
    "sbi REAL, amount REAL, "
    "r_cpo REAL, r_nq REAL, r_fx REAL, vix REAL, "
    "c_prev REAL, p_est REAL, "
    "base REAL, omega_ext REAL, omega_bias REAL, omega_pos REAL, rsi_bonus REAL, "
    "phi REAL, tau_adx REAL, omega_vol REAL, "
    "bias_pct REAL, rsi REAL, adx REAL, "
    "ndx_actual_open REAL, ndx_actual_close REAL, "
    "p_est_deviation REAL, entry_return REAL, forward_return REAL, "
    "operate_time TEXT NOT NULL)"
)
INSERT_VALIDATION = (
    "INSERT OR REPLACE INTO validation "
    "(date, sbi, amount, r_cpo, r_nq, r_fx, vix, c_prev, p_est, "
    "base, omega_ext, omega_bias, omega_pos, rsi_bonus, "
    "phi, tau_adx, omega_vol, bias_pct, rsi, adx, operate_time) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
UPDATE_VALIDATION = (
    "UPDATE validation SET ndx_actual_open=?, ndx_actual_close=?, "
    "p_est_deviation=?, entry_return=?, forward_return=?, "
    "operate_time=? WHERE date=?"
)

# ========== 基金净值 ==========
CREATE_FUND = (
    "CREATE TABLE IF NOT EXISTS fund_nav ("
    "date TEXT PRIMARY KEY, "
    "nav REAL NOT NULL, "
    "daily_return REAL, "
    "operate_time TEXT NOT NULL)"
)
INSERT_FUND = (
    "INSERT OR REPLACE INTO fund_nav (date, nav, daily_return, operate_time) "
    "VALUES (?, ?, ?, ?)"
)


# ========== 底层操作 ==========

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_NDX)
    conn.execute(CREATE_CPO)
    conn.execute(CREATE_NQ)
    conn.execute(CREATE_FX)
    conn.execute(CREATE_VIX)
    conn.execute(CREATE_VALIDATION)
    conn.execute(CREATE_FUND)
    conn.commit()
    return conn


# ========== NDX ==========

def insert_daily(date, open_, high, low, close, volume=0, operate_time=None):
    conn = _get_conn()
    conn.execute(INSERT_NDX, (date, open_, high, low, close, volume,
                              operate_time or _now()))
    conn.commit()
    conn.close()


def get_all():
    conn = _get_conn()
    df = pd.read_sql("SELECT date, open, high, low, close, volume FROM ndx_daily ORDER BY date", conn)
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


# ========== CPO ==========

def insert_cpo_daily(date, open_, high, low, close, change, change_pct,
                      operate_time=None):
    conn = _get_conn()
    conn.execute(INSERT_CPO, (date, open_, high, low, close, change, change_pct,
                              operate_time or _now()))
    conn.commit()
    conn.close()


def get_cpo_ma20() -> tuple[float, float]:
    conn = _get_conn()
    rows = conn.execute("SELECT date, close FROM cpo_daily ORDER BY date DESC LIMIT 25").fetchall()
    conn.close()
    if len(rows) < 21:
        return 0.0, 0.0
    closes = [r[1] for r in rows]
    ma20_yesterday = sum(closes[1:21]) / 20
    ma20_5days_ago = sum(closes[5:25]) / 20 if len(closes) >= 25 else 0.0
    return ma20_yesterday, ma20_5days_ago


def cpo_count() -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM cpo_daily").fetchone()
    conn.close()
    return row[0] if row else 0


# ========== NQ ==========

def insert_nq_daily(date, open_, high, low, close, operate_time=None,
                     is_final=1):
    conn = _get_conn()
    conn.execute(INSERT_NQ, (date, open_, high, low, close,
                              operate_time or _now(), is_final))
    conn.commit()
    conn.close()


def insert_fx_daily(date, close, operate_time=None, is_final=1):
    conn = _get_conn()
    conn.execute(INSERT_FX, (date, close, operate_time or _now(), is_final))
    conn.commit()
    conn.close()


def has_final_record(table: str, date: str) -> bool:
    """检查某表某日期是否已有 is_final=1 的记录"""
    conn = _get_conn()
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE date = ? AND is_final = 1",
        (date,)
    ).fetchone()
    conn.close()
    return row is not None


def get_fx_prev_close() -> float:
    """最近交易日 FX 收盘价（is_final=1, date < today → 周一→周五）"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_conn()
    row = conn.execute(
        "SELECT close FROM fx_daily "
        "WHERE date < ? AND is_final = 1 ORDER BY date DESC LIMIT 1",
        (today,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


def insert_vix_daily(date, open_, high, low, close, operate_time=None,
                      is_final=1):
    conn = _get_conn()
    conn.execute(INSERT_VIX, (date, open_, high, low, close,
                               operate_time or _now(), is_final))
    conn.commit()
    conn.close()


def get_nq_last_two() -> list[float]:
    conn = _get_conn()
    rows = conn.execute("SELECT close FROM nq_daily ORDER BY date DESC LIMIT 2").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_nq_prev_close() -> float:
    """最近交易日 NQ 收盘价（is_final=1, date < today → 周一→周五）"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_conn()
    row = conn.execute(
        "SELECT close FROM nq_daily "
        "WHERE date < ? AND is_final = 1 ORDER BY date DESC LIMIT 1",
        (today,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


# ========== Validation ==========

def save_validation(date: str, result) -> None:
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
        _now(),
    ))
    conn.commit()
    conn.close()


def update_actual(date: str, actual_open: float, actual_close: float) -> None:
    prev = _get_validation_row(date)
    if not prev:
        return
    p_est = prev["p_est"]
    c_prev = prev["c_prev"]
    deviation = ((actual_open - p_est) / p_est * 100) if p_est > 0 else 0
    entry_ret = ((actual_close - c_prev) / c_prev * 100) if c_prev > 0 else 0

    conn = _get_conn()
    next_row = conn.execute(
        "SELECT close FROM ndx_daily WHERE date > ? ORDER BY date LIMIT 1", (date,)
    ).fetchone()
    fwd_ret = 0.0
    if next_row and actual_close > 0:
        fwd_ret = ((next_row[0] - actual_close) / actual_close * 100)

    conn.execute(UPDATE_VALIDATION, (
        actual_open, actual_close,
        round(deviation, 2), round(entry_ret, 2), round(fwd_ret, 2),
        _now(), date))
    conn.commit()
    conn.close()


def get_pending_validations() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date, p_est, c_prev FROM validation "
        "WHERE ndx_actual_open IS NULL ORDER BY date"
    ).fetchall()
    conn.close()
    return [{"date": r[0], "p_est": r[1], "c_prev": r[2]} for r in rows]


def _get_validation_row(date: str):
    conn = _get_conn()
    row = conn.execute("SELECT p_est, c_prev FROM validation WHERE date=?", (date,)).fetchone()
    conn.close()
    return {"p_est": row[0], "c_prev": row[1]} if row else None


def get_validation_stats() -> dict:
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
        details.append({
            "date": r[8], "p_est": r[4], "actual_open": r[5],
            "c_prev": r[6], "actual_close": r[7],
            "deviation": r[0], "entry_return": r[1],
            "forward_return": r[2], "sbi": r[3],
            "deviation_calc": f"({r[5]:.1f} - {r[4]:.1f}) / {r[4]:.1f} * 100 = {r[0]:+.2f}%",
            "entry_calc": f"({r[7]:.1f} - {r[6]:.1f}) / {r[6]:.1f} * 100 = {r[1]:+.2f}%",
        })

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
        "sbi_buckets": {k: {"count": len(v), "avg_return": sum(v)/len(v) if v else 0}
                        for k, v in buckets.items()},
        "details": details,
    }


# ========== Fund NAV ==========

def insert_fund_nav(date: str, nav: float, daily_return: float = 0):
    conn = _get_conn()
    conn.execute(INSERT_FUND, (date, nav, daily_return, _now()))
    conn.commit()
    conn.close()


def get_fund_navs() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT date, nav, daily_return FROM fund_nav ORDER BY date").fetchall()
    conn.close()
    return [{"date": r[0], "nav": r[1], "daily_return": r[2]} for r in rows]


# ========== Import ==========

def import_from_sina_kline(raw_data: str) -> int:
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
                conn.execute(INSERT_NDX, (date, op, hi, lo, cl, vol, _now()))
                n += 1
        except (ValueError, IndexError):
            continue
    conn.commit()
    conn.close()
    return n


def import_csv(csv_path):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
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
                conn.execute(INSERT_NDX, (date, op, hi, lo, cl, vol, _now()))
                n += 1
    conn.commit()
    conn.close()
    return n
