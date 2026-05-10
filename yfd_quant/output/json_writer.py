"""JSON 导出与历史记录"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from yfd_quant.types import ModelResult


def result_to_dict(result: ModelResult) -> dict:
    """将 ModelResult 转为可序列化的字典"""
    ind = result.indicators
    return {
        "timestamp": result.timestamp.isoformat(),
        "sbi": result.sbi,
        "recommended_amount_cny": result.recommended_amount,
        "config": {"M": result.M, "M_min": result.M_min},
        "inputs": {
            "r_cpo": result.r_cpo, "r_nq": result.r_nq, "r_fx": result.r_fx,
            "vix": result.vix, "ndx_close_prev": result.ndx_close_prev,
            "p_est": result.p_est, "cpo_downtrend": result.cpo_downtrend,
        },
        "indicators": {
            "ma20": ind.ma20, "ma200": ind.ma200,
            "high_52w": ind.high_52w, "low_52w": ind.low_52w,
            "atr14": ind.atr14, "rsi": ind.rsi,
            "adx": ind.adx, "di_plus": ind.di_plus, "di_minus": ind.di_minus,
        },
        "decomposition": {
            "layer1": result.layer1,
            "layer2_base": result.layer2_base,
            "layer3": {
                "omega_ext": result.alpha.omega_ext,
                "omega_bias": result.alpha.omega_bias,
                "omega_pos": result.alpha.omega_pos,
                "rsi_bonus": result.alpha.rsi_bonus,
                "bias_pct": result.alpha.bias_pct,
                "p_pos": result.alpha.p_pos,
            },
            "layer4": {
                "omega_vol": result.tech.omega_vol,
                "tau_adx": result.tech.tau_adx,
                "phi": result.tech.phi,
                "gap": result.tech.gap,
            },
            "layer5": {"raw_score": result.raw_score, "sbi": result.sbi},
        },
    }


def write_single(result: ModelResult, filepath: Path) -> None:
    """写入单次结果 JSON"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_to_dict(result), f, ensure_ascii=False, indent=2)


def append_history(result: ModelResult, history_path: Path,
                   max_records: int = 365) -> None:
    """追加记录到历史 JSON 文件"""
    history_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError):
            records = []

    records.insert(0, result_to_dict(result))
    if len(records) > max_records:
        records = records[:max_records]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
