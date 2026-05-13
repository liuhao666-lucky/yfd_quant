"""SQLite 数据库 —— 所有表统含 operate_time 操作时间戳

表:
  ndx_daily   - 纳指100日线 (O/H/L/C/V)
  cpo_daily   - A股光模块收盘
  nq_daily    - 纳指期货收盘
  snapshot    - 14:50 模型决策快照（冻结输入+输出，防回测幻觉）
  validation  - 模型检验（实际验证数据，从 snapshot 读决策数据）
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

# ========== 快照表（14:50 模型决策冻结） ==========
CREATE_SNAPSHOT = (
    "CREATE TABLE IF NOT EXISTS snapshot ("
    "date TEXT PRIMARY KEY, "
    "r_cpo REAL, r_nq REAL, r_fx REAL, vix REAL, "
    "ndx_close_prev REAL, "
    "cpo_downtrend INTEGER, "
    "sbi REAL, amount REAL, p_est REAL, base REAL, "
    "omega_ext REAL, omega_bias REAL, omega_pos REAL, rsi_bonus REAL, "
    "phi REAL, tau_adx REAL, omega_vol REAL, "
    "bias_pct REAL, p_pos REAL, "
    "raw_score REAL, gap REAL, strong_downtrend INTEGER, "
    "M REAL, M_min REAL, "
    "rsi REAL, adx REAL, ma20 REAL, ma200 REAL, "
    "high_52w REAL, low_52w REAL, atr14 REAL, di_plus REAL, di_minus REAL, "
    "f_cpo REAL, f_nq REAL, f_fx REAL, tau_cpo REAL, "
    "operate_time TEXT NOT NULL)"
)
INSERT_SNAPSHOT = (
    "INSERT OR REPLACE INTO snapshot "
    "(date, r_cpo, r_nq, r_fx, vix, ndx_close_prev, "
    "cpo_downtrend, "
    "sbi, amount, p_est, base, "
    "omega_ext, omega_bias, omega_pos, rsi_bonus, "
    "phi, tau_adx, omega_vol, "
    "bias_pct, p_pos, raw_score, gap, strong_downtrend, M, M_min, "
    "rsi, adx, ma20, ma200, high_52w, low_52w, atr14, di_plus, di_minus, "
    "f_cpo, f_nq, f_fx, tau_cpo, operate_time) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
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

def _migrate_snapshot(conn: sqlite3.Connection) -> None:
    """迁移：删除快照表中已废弃的 CPO 中间变量列"""
    obsolete = ["cpo_close_today", "cpo_ma20_yesterday", "cpo_ma20_5days_ago"]
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(snapshot)").fetchall()}
        for col in obsolete:
            if col in existing:
                conn.execute(f"ALTER TABLE snapshot DROP COLUMN {col}")
    except Exception:
        # ALTER TABLE DROP COLUMN 不支持时，重建表
        rows = conn.execute("SELECT * FROM snapshot").fetchall()
        col_names = [row[1] for row in conn.execute("PRAGMA table_info(snapshot)").fetchall()]
        conn.execute("DROP TABLE IF EXISTS snapshot")
        conn.execute(CREATE_SNAPSHOT)
        if rows:
            new_cols = [row[1] for row in conn.execute("PRAGMA table_info(snapshot)").fetchall()]
            keep_idx = [i for i, c in enumerate(col_names) if c in new_cols]
            for row in rows:
                filtered = [row[i] for i in keep_idx]
                placeholders = ",".join(["?"] * len(filtered))
                conn.execute(f"INSERT OR REPLACE INTO snapshot VALUES ({placeholders})", filtered)


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_NDX)
    conn.execute(CREATE_CPO)
    conn.execute(CREATE_NQ)
    conn.execute(CREATE_FX)
    conn.execute(CREATE_VIX)
    conn.execute(CREATE_SNAPSHOT)
    conn.execute(CREATE_VALIDATION)
    conn.execute(CREATE_FUND)
    conn.commit()
    _migrate_snapshot(conn)
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


def get_ndx_prev_close() -> float:
    """最近交易日 NDX 收盘价（date < today，取自 ndx_daily 表）"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_conn()
    row = conn.execute(
        "SELECT close FROM ndx_daily "
        "WHERE date < ? ORDER BY date DESC LIMIT 1",
        (today,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


# ========== Snapshot ==========

def save_snapshot(date: str, result) -> None:
    """将 14:50 模型运行的完整输入+输出冻结到快照表"""
    l1 = result.layer1 if hasattr(result, "layer1") else {}
    conn = _get_conn()
    conn.execute(INSERT_SNAPSHOT, (
        date,
        result.r_cpo, result.r_nq, result.r_fx, result.vix,
        result.ndx_close_prev,
        int(result.cpo_downtrend),
        result.sbi, result.recommended_amount, result.p_est, result.layer2_base,
        result.alpha.omega_ext, result.alpha.omega_bias,
        result.alpha.omega_pos, result.alpha.rsi_bonus,
        result.tech.phi, result.tech.tau_adx, result.tech.omega_vol,
        result.alpha.bias_pct, result.alpha.p_pos,
        result.raw_score, result.tech.gap, int(result.tech.strong_downtrend),
        result.M, result.M_min,
        result.indicators.rsi, result.indicators.adx,
        result.indicators.ma20, result.indicators.ma200,
        result.indicators.high_52w, result.indicators.low_52w,
        result.indicators.atr14, result.indicators.di_plus, result.indicators.di_minus,
        l1.get("f_cpo", 0.0), l1.get("f_nq", 0.0),
        l1.get("f_fx", 0.0), l1.get("tau_cpo", 1.0),
        _now(),
    ))
    conn.commit()
    conn.close()


def get_snapshot(date: str) -> Optional[dict]:
    """读取某日快照，返回 dict 或 None"""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM snapshot WHERE date=?", (date,)).fetchone()
    conn.close()
    return dict(row) if row else None


def snapshot_to_result(snap: dict):
    """将快照 dict 转回 ModelResult，供 --notify/--debug 使用"""
    from yfd_quant.types import (
        ModelResult, AlphaComponents, TechComponents, IndicatorBundle,
    )
    from datetime import datetime as dt
    return ModelResult(
        timestamp=dt.strptime(snap["date"], "%Y-%m-%d"),
        sbi=snap["sbi"],
        recommended_amount=snap["amount"],
        M=snap["M"], M_min=snap["M_min"],
        r_cpo=snap["r_cpo"], r_nq=snap["r_nq"], r_fx=snap["r_fx"],
        vix=snap["vix"],
        ndx_close_prev=snap["ndx_close_prev"],
        p_est=snap["p_est"],
        cpo_downtrend=bool(snap["cpo_downtrend"]),
        indicators=IndicatorBundle(
            ma20=snap["ma20"], ma200=snap["ma200"],
            high_52w=snap["high_52w"], low_52w=snap["low_52w"],
            atr14=snap["atr14"], rsi=snap["rsi"], adx=snap["adx"],
            di_plus=snap["di_plus"], di_minus=snap["di_minus"],
        ),
        layer1={"f_cpo": snap["f_cpo"], "f_nq": snap["f_nq"],
                "f_fx": snap["f_fx"], "tau_cpo": snap["tau_cpo"]},
        layer2_base=snap["base"],
        alpha=AlphaComponents(
            omega_ext=snap["omega_ext"], omega_bias=snap["omega_bias"],
            omega_pos=snap["omega_pos"], rsi_bonus=snap["rsi_bonus"],
            bias_pct=snap["bias_pct"], p_pos=snap["p_pos"],
        ),
        tech=TechComponents(
            omega_vol=snap["omega_vol"], tau_adx=snap["tau_adx"],
            phi=snap["phi"], gap=snap["gap"],
            strong_downtrend=bool(snap["strong_downtrend"]),
        ),
        raw_score=snap["raw_score"],
        summary="", detail="",
    )


def snapshot_to_market_snapshot(snap: dict, ndx_hist):
    """将快照 dict 转回 MarketSnapshot，供 --recalc-snapshot 重跑模型用"""
    from yfd_quant.types import MarketSnapshot
    from datetime import datetime as dt
    cpo_ma20_y, cpo_ma20_5d = get_cpo_ma20()
    return MarketSnapshot(
        timestamp=dt.strptime(snap["date"], "%Y-%m-%d"),
        r_cpo=snap["r_cpo"], r_nq=snap["r_nq"], r_fx=snap["r_fx"],
        cpo_close_today=0.0,
        cpo_ma20_yesterday=cpo_ma20_y,
        cpo_ma20_5days_ago=cpo_ma20_5d,
        cpo_downtrend=bool(snap["cpo_downtrend"]),
        ndx_close_prev=snap["ndx_close_prev"],
        ndx_historical=ndx_hist,
        vix=snap["vix"],
    )


def update_snapshot_derived(date: str, result) -> None:
    """更新快照表中的模型计算指标（输入字段不变）"""
    l1 = result.layer1 if hasattr(result, "layer1") else {}
    conn = _get_conn()
    conn.execute(
        "UPDATE snapshot SET "
        "sbi=?, amount=?, p_est=?, base=?, "
        "omega_ext=?, omega_bias=?, omega_pos=?, rsi_bonus=?, "
        "phi=?, tau_adx=?, omega_vol=?, "
        "bias_pct=?, p_pos=?, raw_score=?, gap=?, strong_downtrend=?, "
        "rsi=?, adx=?, ma20=?, ma200=?, "
        "high_52w=?, low_52w=?, atr14=?, di_plus=?, di_minus=?, "
        "f_cpo=?, f_nq=?, f_fx=?, tau_cpo=?, "
        "M=?, M_min=?, operate_time=? "
        "WHERE date=?",
        (result.sbi, result.recommended_amount, result.p_est, result.layer2_base,
         result.alpha.omega_ext, result.alpha.omega_bias,
         result.alpha.omega_pos, result.alpha.rsi_bonus,
         result.tech.phi, result.tech.tau_adx, result.tech.omega_vol,
         result.alpha.bias_pct, result.alpha.p_pos,
         result.raw_score, result.tech.gap, int(result.tech.strong_downtrend),
         result.indicators.rsi, result.indicators.adx,
         result.indicators.ma20, result.indicators.ma200,
         result.indicators.high_52w, result.indicators.low_52w,
         result.indicators.atr14, result.indicators.di_plus, result.indicators.di_minus,
         l1.get("f_cpo", 0.0), l1.get("f_nq", 0.0),
         l1.get("f_fx", 0.0), l1.get("tau_cpo", 1.0),
         result.M, result.M_min, _now(),
         date))
    conn.commit()
    conn.close()


# ========== Validation ==========

def save_validation(date: str, result) -> None:
    """写入 validation 表（仅回测使用，主流程用 save_snapshot）"""
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
    """补录实际数据：从 snapshot 读 p_est/c_prev，写入 validation"""
    snap = get_snapshot(date)
    if snap:
        p_est = snap["p_est"]
        c_prev = snap["ndx_close_prev"]
    else:
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
    """查找快照中有但 validation 实际数据缺失的记录"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT s.date, s.p_est, s.ndx_close_prev "
        "FROM snapshot s "
        "LEFT JOIN validation v ON s.date = v.date "
        "WHERE v.date IS NULL OR v.ndx_actual_open IS NULL OR v.p_est_deviation IS NULL "
        "ORDER BY s.date"
    ).fetchall()
    conn.close()
    return [{"date": r[0], "p_est": r[1], "c_prev": r[2]} for r in rows]


def backfill_all_pending() -> list[str]:
    """从 ndx_daily 补录所有缺失 actual 的 validation 记录，返回已补录的日期列表"""
    pending = get_pending_validations()
    if not pending:
        return []
    conn = _get_conn()
    filled = []
    for p in pending:
        date = p["date"]
        row = conn.execute(
            "SELECT open, close FROM ndx_daily WHERE date = ?", (date,)
        ).fetchone()
        if not row:
            continue
        actual_open, actual_close = float(row[0]), float(row[1])
        p_est = p["p_est"]
        c_prev = p["c_prev"]
        deviation = ((actual_open - p_est) / p_est * 100) if p_est > 0 else 0
        entry_ret = ((actual_close - c_prev) / c_prev * 100) if c_prev > 0 else 0
        next_row = conn.execute(
            "SELECT close FROM ndx_daily WHERE date > ? ORDER BY date LIMIT 1", (date,)
        ).fetchone()
        fwd_ret = 0.0
        if next_row and actual_close > 0:
            fwd_ret = ((next_row[0] - actual_close) / actual_close * 100)
        # INSERT OR REPLACE 确保无论 validation 有无该日期都能写入
        conn.execute(
            "INSERT OR REPLACE INTO validation "
            "(date, sbi, amount, r_cpo, r_nq, r_fx, vix, c_prev, p_est, "
            "base, omega_ext, omega_bias, omega_pos, rsi_bonus, "
            "phi, tau_adx, omega_vol, bias_pct, rsi, adx, "
            "ndx_actual_open, ndx_actual_close, "
            "p_est_deviation, entry_return, forward_return, operate_time) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, 0, 0, 0, 0, 0, 0, c_prev, p_est,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
             actual_open, actual_close,
             round(deviation, 2), round(entry_ret, 2), round(fwd_ret, 2),
             _now()))
        filled.append(date)
    conn.commit()
    conn.close()
    return filled


def _get_validation_row(date: str):
    conn = _get_conn()
    row = conn.execute("SELECT p_est, c_prev FROM validation WHERE date=?", (date,)).fetchone()
    conn.close()
    return {"p_est": row[0], "c_prev": row[1]} if row else None


def get_validation_stats() -> dict:
    """从 snapshot + validation JOIN 读取验证统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT v.p_est_deviation, v.entry_return, v.forward_return, "
        "s.sbi, s.p_est, v.ndx_actual_open, s.ndx_close_prev, v.ndx_actual_close, v.date "
        "FROM validation v "
        "JOIN snapshot s ON v.date = s.date "
        "WHERE v.p_est_deviation IS NOT NULL"
    ).fetchall()
    # 回退：旧数据可能只在 validation 表中（无 snapshot）
    if not rows:
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
