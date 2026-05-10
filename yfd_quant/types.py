"""核心数据类型定义"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IndicatorBundle:
    """从 NDX 日线计算的所有技术指标"""
    ma20: float
    ma200: float
    high_52w: float
    low_52w: float
    atr14: float
    rsi: float
    adx: float
    di_plus: float
    di_minus: float


@dataclass
class MarketSnapshot:
    """一次运行所需的全部市场原始数据"""
    timestamp: datetime

    # Layer 1 输入（涨跌幅 %）
    r_cpo: float
    r_nq: float
    r_fx: float

    # Layer 2 CPO 折扣判断
    cpo_close_today: float      # CPO 板块今日收盘点位
    cpo_ma20_yesterday: float   # 昨日的 20 日均线值
    cpo_ma20_5days_ago: float   # 5 天前的 20 日均线值
    cpo_downtrend: bool         # 是否触发主跌浪折扣

    # Layer 3/4 纳斯达克参考数据
    ndx_close_prev: float       # C_{t-1}：纳指100昨收
    ndx_historical: "pd.DataFrame | None" = None  # 纳指日线 OHLCV

    # VIX
    vix: float = 0.0

    # 状态标记
    indicators_ready: bool = False
    data_quality: str = "unknown"  # full / degraded / skip


@dataclass
class AlphaComponents:
    """Layer 3 聪明资金 Alpha 计算结果"""
    omega_ext: float = 0.0
    omega_bias: float = 0.0
    omega_pos: float = 0.0
    rsi_bonus: float = 0.0
    bias_pct: float = 0.0
    p_pos: float = 0.0


@dataclass
class TechComponents:
    """Layer 4 技术修正计算结果"""
    omega_vol: float = 1.0
    tau_adx: float = 1.0
    phi: float = 1.0
    gap: float = 0.0
    strong_downtrend: bool = False


@dataclass
class ModelResult:
    """最终模型输出"""
    timestamp: datetime
    sbi: float
    recommended_amount: float

    # 配置
    M: float
    M_min: float

    # 输入快照
    r_cpo: float
    r_nq: float
    r_fx: float
    vix: float
    ndx_close_prev: float
    p_est: float
    cpo_downtrend: bool

    # 技术指标
    indicators: IndicatorBundle

    # 各层分解
    layer1: dict = field(default_factory=dict)
    layer2_base: float = 0.0
    alpha: AlphaComponents = field(default_factory=AlphaComponents)
    tech: TechComponents = field(default_factory=TechComponents)
    raw_score: float = 0.0

    # 详情摘要
    summary: str = ""
    detail: str = ""
