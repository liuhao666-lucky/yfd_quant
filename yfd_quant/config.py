"""配置加载模块"""

import os
import yaml
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _find_config(path: str | Path | None = None) -> Path:
    """查找配置文件路径"""
    if path:
        p = Path(path)
        if p.exists():
            return p
        raise FileNotFoundError(f"配置文件不存在: {path}")

    # 默认路径
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH

    # 搜索当前目录
    cwd = Path.cwd() / "config.yaml"
    if cwd.exists():
        return cwd

    raise FileNotFoundError("找不到 config.yaml，请创建配置文件或指定路径")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载 YAML 配置文件，支持环境变量覆盖"""
    config_path = _find_config(path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # 环境变量覆盖
    _apply_env_overrides(config)
    return config


def _apply_env_overrides(config: dict) -> None:
    """用环境变量覆盖配置值"""
    overrides = {
        "YFD_M": ("M", float),
        "YFD_M_MIN": ("M_min", float),
        "YFD_TIMEZONE_DISCOUNT": ("timezone_discount", float),
        "YFD_ALPHAVANTAGE_API_KEY": ("alphavantage.api_key", str),
        "YFD_NASDAQ_API_KEY": ("nasdaq_datalink.api_key", str),
        "YFD_BARK_URL": ("notify.bark_url", str),
        "YFD_WECOM_WEBHOOK": ("notify.wecom_webhook", str),
    }

    for env_var, (config_path, converter) in overrides.items():
        value = os.environ.get(env_var)
        if value is not None:
            _set_nested(config, config_path.split("."), converter(value))


def _set_nested(d: dict, keys: list, value: Any) -> None:
    """设置嵌套字典的值"""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value
