"""Rich 终端输出 —— 精简版，只展示模型相关数据"""

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from yfd_quant.types import ModelResult

console = Console()


def sbi_color(sbi: float) -> str:
    if sbi >= 70:
        return "green"
    elif sbi >= 40:
        return "yellow"
    return "red"


def render(result: ModelResult, weekend: bool = False) -> None:
    ind = result.indicators
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if weekend:
        from yfd_quant.data.db import get_nq_prev_close
        nq_close = get_nq_prev_close()
        mode_text = f"\n[周末模式] 以下为周五收盘数据 | NQ期货昨收: {nq_close:.1f}" if nq_close > 0 else "\n[周末模式] 以下为周五收盘数据"
    else:
        mode_text = ""

    # ---- 标题 ----
    console.print()
    console.print(Panel(
        Text(f"易方达全球成长精选 · 量化定投决策\nV2.0  |  {ts}{mode_text}",
             justify="center", style="bold cyan"),
        box=box.DOUBLE,
    ))

    # ---- 三因子原始数据（一行） ----
    console.print(f"  [dim]CPO[/dim] {result.r_cpo:+.2f}%  |  "
                  f"[dim]纳指期货[/dim] {result.r_nq:+.2f}%  |  "
                  f"[dim]汇率[/dim] {result.r_fx:+.2f}%  |  "
                  f"[dim]VIX期货[/dim] {result.vix:.1f}  |  "
                  f"[dim]纳指100昨收[/dim] {result.ndx_close_prev:.0f}  |  "
                  f"[dim]P_est[/dim] {result.p_est:.0f}")

    # CPO 主跌浪警告
    if result.cpo_downtrend:
        console.print("  [yellow][!] CPO 主跌浪折扣生效 τ=0.8[/yellow]")

    # ---- 六层分解（紧凑一行） ----
    l1 = result.layer1
    console.print()
    console.print(f"  [dim]模块一:[/dim] f_CPO={l1['f_cpo']:.0f}  f_NQ={l1['f_nq']:.0f}  f_FX={l1['f_fx']:.0f}")
    console.print(f"  [dim]模块二:[/dim] Base={result.layer2_base:.1f}  "
                  f"[dim]模块三:[/dim] Ω_ext={result.alpha.omega_ext:.0f}  "
                  f"Ω_bias={result.alpha.omega_bias:.1f}  Ω_pos={result.alpha.omega_pos:.1f}  RSI={result.alpha.rsi_bonus:.1f}")
    console.print(f"  [dim]模块四:[/dim] Φ(VIX)={result.tech.phi:.3f}  "
                  f"τ_ADX={result.tech.tau_adx}  Ω_VOL={result.tech.omega_vol}  "
                  f"乖离={result.alpha.bias_pct:+.1f}%")

    # ADX 趋势判定
    if result.tech.strong_downtrend:
        trend = "[red]强趋势·空头(τ=0.6)[/red]"
    elif result.tech.tau_adx == 0.8:
        trend = "[yellow]弱趋势·年线下(τ=0.8)[/yellow]"
    else:
        trend = "[dim]正常[/dim]"
    console.print(f"  [dim]模块四:[/dim] ADX={ind.adx:.1f}  DI+={ind.di_plus:.1f}  DI-={ind.di_minus:.1f}  → {trend}")

    # ---- SBI 总分 ----
    console.print()
    color = sbi_color(result.sbi)
    sbi_text = Text(f"{result.sbi} / 100", style=f"bold {color}", justify="center")
    console.print(Panel(sbi_text, title="SBI 总分", border_style=color, padding=(1, 4)))

    # ---- 建议金额 ----
    amt_text = Text(f"CNY {result.recommended_amount:.2f}", style="bold green", justify="center")
    console.print(Panel(amt_text, title="今日建议买入", border_style="green", padding=(1, 4)))

    # 数据质量提示
    if result.indicators.adx == 0.0 and result.indicators.rsi == 50.0:
        console.print("  [dim][!] 历史数据积累中（需14天+），部分指标暂用中性值[/dim]")

    console.print()


def render_debug(result: ModelResult) -> None:
    """打印全部模型指标（调试模式）"""
    ind = result.indicators
    l1 = result.layer1

    console.print()
    console.rule("[bold yellow]模型全部指标")

    console.print(f"  [bold]输入因子[/bold]")
    console.print(f"    R_CPO = {result.r_cpo:+.4f}%  (A股光模块涨跌幅)")
    console.print(f"    R_NQ  = {result.r_nq:+.4f}%  (纳指期货涨跌幅)")
    console.print(f"    R_FX  = {result.r_fx:+.4f}%  (USDCNH涨跌幅)")
    console.print(f"    VIX   = {result.vix:.2f}      (恐慌指数)")
    console.print(f"    C_prev= {result.ndx_close_prev:.2f} (纳指100昨收)")
    console.print(f"    P_est = {result.p_est:.2f} (预估开盘价)")
    console.print(f"    CPO主跌浪 = {'是' if result.cpo_downtrend else '否'}")

    console.print(f"  [bold]模块一: 吸引力分数[/bold]")
    console.print(f"    f_CPO = attraction_score({result.r_cpo:+.2f}%) = {l1['f_cpo']:.1f}")
    console.print(f"    f_NQ  = attraction_score({result.r_nq:+.2f}%) = {l1['f_nq']:.1f}")
    console.print(f"    f_FX  = attraction_score({result.r_fx:+.2f}%) = {l1['f_fx']:.1f}")

    console.print(f"  [bold]模块二: 底仓[/bold]")
    console.print(f"    tau_CPO = {l1['tau_cpo']} {'(主跌浪折扣)' if l1['tau_cpo'] == 0.8 else ''}")
    console.print(f"    Base = 0.25*({l1['f_cpo']:.1f}*{l1['tau_cpo']}) + 0.65*{l1['f_nq']:.1f} + 0.10*{l1['f_fx']:.1f}")
    console.print(f"         = {result.layer2_base:.2f}")

    console.print(f"  [bold]模块三: Alpha 补偿[/bold]")
    console.print(f"    P_est = C_prev*(1+R_NQ/100) = {result.ndx_close_prev:.2f}*{1+result.r_nq/100:.4f} = {result.p_est:.2f}")
    console.print(f"    Omega_EXT={result.alpha.omega_ext:.1f}  (血洗: CPO={result.r_cpo:+.1f}% NQ={result.r_nq:+.1f}%)")
    console.print(f"    Omega_BIAS={result.alpha.omega_bias:.2f}  (乖离={result.alpha.bias_pct:+.2f}% |>=2.5%|?)")
    console.print(f"    Omega_POS={result.alpha.omega_pos:.2f}  (P_pos={result.alpha.p_pos:.1f}% <=20%?)")
    console.print(f"    RSI_Bonus={result.alpha.rsi_bonus:.1f}  (RSI={ind.rsi:.1f})")

    console.print(f"  [bold]模块四: 技术修正[/bold]")
    console.print(f"    Omega_VOL={result.tech.omega_vol}  (gap={result.tech.gap:.1f} vs 2*ATR14={2*ind.atr14:.1f})")
    console.print(f"    tau_ADX={result.tech.tau_adx}  (ADX={ind.adx:.1f} DI+={ind.di_plus:.1f} DI-={ind.di_minus:.1f})")
    console.print(f"    Phi(VIX)={result.tech.phi:.4f}  =0.6+1.6/(1+e^(-0.7*({result.vix:.2f}-14)))")
    console.print(f"    MA20={ind.ma20:.1f} MA200={ind.ma200:.1f}")
    console.print(f"    52w: H={ind.high_52w:.1f} L={ind.low_52w:.1f} ATR14={ind.atr14:.1f}")

    console.print(f"  [bold]模块五: SBI 汇聚[/bold]")
    alpha_sum = result.alpha.omega_ext + result.alpha.omega_bias + result.alpha.omega_pos + result.alpha.rsi_bonus
    console.print(f"    raw = ({result.layer2_base:.2f} + {alpha_sum:.2f}) * {result.tech.phi:.4f} * {result.tech.tau_adx} * {result.tech.omega_vol}")
    console.print(f"        = {(result.layer2_base + alpha_sum):.2f} * {result.tech.phi:.4f}")
    console.print(f"        = {result.raw_score:.2f} -> SBI={result.sbi}")

    console.print(f"  [bold]模块六: 金额[/bold]")
    if result.sbi >= 30:
        ratio = (result.sbi - 30) / 70
        console.print(f"    ratio=({result.sbi}-30)/70={ratio:.4f}")
        console.print(f"    二次曲线={result.M}*{ratio:.4f}^2={result.M*ratio**2:.2f}")
    console.print(f"    最终=CNY {result.recommended_amount:.2f}")

    console.rule()
    console.print()
