"""量化引擎 —— 串联六层滤网，从 MarketSnapshot 到 ModelResult"""

import logging
from datetime import datetime

from yfd_quant.types import MarketSnapshot, IndicatorBundle, ModelResult, AlphaComponents, TechComponents
from yfd_quant.indicators.calculator import compute_all as compute_indicators
from yfd_quant.model.layer1_attraction import attraction_score
from yfd_quant.model.layer2_base import compute_base, TAU_CPO_DISCOUNT
from yfd_quant.model.layer3_alpha import compute_all as compute_alpha
from yfd_quant.model.layer4_technical import compute_all as compute_tech
from yfd_quant.model.layer5_sbi import compute_sbi
from yfd_quant.model.layer6_position import compute_amount

logger = logging.getLogger(__name__)


class QuantEngine:
    """易方达量化定投引擎"""

    def run(self, snapshot: MarketSnapshot,
            M: float = 50.0, M_min: float = 10.0,
            timezone_discount: float = 0.85) -> ModelResult:
        """执行完整六层滤网计算

        Args:
            snapshot: 市场数据快照
            M: 单日最大申购额
            M_min: 强制底仓
            timezone_discount: 时区敬畏折扣

        Returns:
            ModelResult 包含 SBI、建议金额和完整分解
        """
        # ---- 输入校验 ----
        if snapshot.ndx_close_prev <= 0:
            raise ValueError(f"NDX 昨收={snapshot.ndx_close_prev}，数据异常，拒绝运行")
        if M < M_min:
            raise ValueError(f"M={M} < M_min={M_min}，配置错误")

        # ---- 计算技术指标 ----
        if snapshot.ndx_historical is not None and not snapshot.ndx_historical.empty:
            indicators = compute_indicators(snapshot.ndx_historical)
        else:
            raise ValueError("NDX 历史数据为空，无法计算技术指标")

        # ---- 模块一：单指标吸引力 ----
        f_cpo = attraction_score(snapshot.r_cpo)
        f_nq = attraction_score(snapshot.r_nq)
        f_fx = attraction_score(snapshot.r_fx)

        # ---- 模块二：底仓 ----
        tau_cpo = TAU_CPO_DISCOUNT if snapshot.cpo_downtrend else 1.0
        base = compute_base(f_cpo, tau_cpo, f_nq, f_fx)

        # ---- 模块三：聪明资金 Alpha ----
        alpha = compute_alpha(
            r_cpo=snapshot.r_cpo,
            r_nq=snapshot.r_nq,
            ndx_close_prev=snapshot.ndx_close_prev,
            ma20=indicators.ma20,
            high_52w=indicators.high_52w,
            low_52w=indicators.low_52w,
            rsi_val=indicators.rsi,
        )

        # ---- 模块四：技术修正 ----
        tech = compute_tech(
            p_est=alpha.p_est,
            close_prev=snapshot.ndx_close_prev,
            atr14=indicators.atr14,
            adx=indicators.adx,
            di_plus=indicators.di_plus,
            di_minus=indicators.di_minus,
            ma200=indicators.ma200,
            vix=snapshot.vix,
        )

        # ---- 模块五：SBI 汇聚 ----
        sbi, raw_score = compute_sbi(
            base=base,
            omega_ext=alpha.omega_ext,
            omega_bias=alpha.omega_bias,
            omega_pos=alpha.omega_pos,
            rsi_bonus=alpha.rsi_bonus,
            phi=tech.phi,
            tau_adx=tech.tau_adx,
            omega_vol=tech.omega_vol,
        )

        # ---- 模块六：金额映射 ----
        amount, amount_detail = compute_amount(sbi, M, M_min, timezone_discount)

        # ---- 组装结果 ----
        l1 = {"f_cpo": round(f_cpo, 2), "f_nq": round(f_nq, 2),
              "f_fx": round(f_fx, 2), "tau_cpo": tau_cpo}
        l2 = base

        alpha_comp = AlphaComponents(
            omega_ext=alpha.omega_ext, omega_bias=alpha.omega_bias,
            omega_pos=alpha.omega_pos, rsi_bonus=alpha.rsi_bonus,
            bias_pct=alpha.bias_pct, p_pos=alpha.p_pos,
        )
        tech_comp = TechComponents(
            omega_vol=tech.omega_vol, tau_adx=tech.tau_adx,
            phi=tech.phi, gap=tech.gap,
            strong_downtrend=tech.strong_downtrend,
        )

        # 生成摘要
        summary = (
            f"SBI={sbi}/100 | 建议买入=¥{amount} | "
            f"CPO={snapshot.r_cpo:+.2f}% NQ={snapshot.r_nq:+.2f}% "
            f"VIX={snapshot.vix:.1f} | "
            f"Base={base:.1f} Φ={tech.phi:.3f} τ_ADX={tech.tau_adx}"
        )

        detail = (
            f"Base={base:.2f} | Ω_ext={alpha.omega_ext} | "
            f"Ω_bias={alpha.omega_bias:.2f} | Ω_pos={alpha.omega_pos:.2f} | "
            f"RSI奖={alpha.rsi_bonus:.1f} | Φ(VIX)={tech.phi:.3f} | "
            f"τ_ADX={tech.tau_adx} | Ω_VOL={tech.omega_vol} | "
            f"乖离率={alpha.bias_pct:.2f}%"
        )

        return ModelResult(
            timestamp=datetime.now(),
            sbi=sbi,
            recommended_amount=amount,
            M=M, M_min=M_min,
            r_cpo=snapshot.r_cpo, r_nq=snapshot.r_nq, r_fx=snapshot.r_fx,
            vix=snapshot.vix,
            ndx_close_prev=snapshot.ndx_close_prev,
            p_est=alpha.p_est,
            cpo_downtrend=snapshot.cpo_downtrend,
            indicators=indicators,
            layer1=l1, layer2_base=l2,
            alpha=alpha_comp, tech=tech_comp,
            raw_score=round(raw_score, 2),
            summary=summary, detail=detail,
        )
