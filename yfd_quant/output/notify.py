"""企业微信推送通知 —— 小白话解释所有指标"""

import requests
from yfd_quant.types import ModelResult


def _post_markdown(webhook_url: str, content: str) -> bool:
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={
            "msgtype": "markdown", "markdown": {"content": content},
        }, timeout=10)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
    except requests.RequestException:
        return False


def send_model_result(result: ModelResult, webhook_url: str) -> bool:
    """主模型运行结果推送 —— 完整六层分解 + 小白话解释"""
    sbi = result.sbi
    amount = result.recommended_amount
    color = "warning" if sbi >= 70 else "comment" if sbi >= 40 else "info"

    # 建议买入文案
    if sbi >= 70:
        action = f"<font color=\"warning\">【强烈建议买入】</font>"
    elif sbi >= 40:
        action = f"<font color=\"comment\">【建议适当买入】</font>"
    elif sbi >= 30:
        action = f"<font color=\"info\">【少量买入】</font>"
    else:
        action = f"<font color=\"info\">【仅买底仓】</font>"

    # 模块一：吸引力分数
    l1 = result.layer1
    f_cpo = l1["f_cpo"]
    f_nq = l1["f_nq"]
    f_fx = l1["f_fx"]

    def _attract_comment(score):
        if score >= 70:
            return "便宜，加分"
        elif score >= 40:
            return "中等"
        elif score >= 10:
            return "偏贵，扣分"
        else:
            return "很贵，大幅扣分"

    # 模块三
    alpha = result.alpha
    bias_val = abs(alpha.bias_pct)
    bias_msg = ""
    if alpha.omega_ext > 0:
        bias_msg = f"\n  <font color=\"warning\">（血洗日触发，乖离率互斥关闭）</font>"
    elif alpha.omega_bias > 0:
        direction = "超卖" if alpha.bias_pct < 0 else "强势突破"
        bias_msg = f"\n  <font color=\"comment\">（偏离均线 {bias_val:.1f}%，属于{direction}，额外+{alpha.omega_bias:.1f}分）</font>"
    else:
        bias_msg = f"\n  <font color=\"comment\">（乖离率 {bias_val:.1f}%，未超 2.5% 阈值，不加分）</font>"

    # RSI 互斥说明
    rsi_msg = ""
    if alpha.omega_ext > 0:
        rsi_msg = "\n  <font color=\"comment\">（血洗日触发，RSI互斥关闭）</font>"
    elif bias_val >= 2.5:
        rsi_msg = "\n  <font color=\"comment\">（乖离率够大，RSI互斥关闭）</font>"
    elif alpha.rsi_bonus > 0:
        rsi_msg = f"\n  <font color=\"comment\">（RSI={result.indicators.rsi:.1f}，超卖衰竭，奖励+{alpha.rsi_bonus:.1f}分）</font>"
    else:
        rsi_msg = f"\n  <font color=\"comment\">（RSI={result.indicators.rsi:.1f}，未触发衰竭信号）</font>"

    # 模块四
    tech = result.tech
    adx_msg = ""
    if tech.strong_downtrend:
        adx_msg = f"\n  <font color=\"warning\">（ADX={result.indicators.adx:.1f} 强趋势+空头主导 → 打6折，避飞刀）</font>"
    elif tech.tau_adx == 0.8:
        adx_msg = f"\n  <font color=\"comment\">（ADX={result.indicators.adx:.1f} 价格在年线下 → 打8折，熊市谨慎）</font>"
    else:
        adx_msg = f"\n  <font color=\"comment\">（ADX={result.indicators.adx:.1f} 正常，不打折）</font>"

    # 金额分解
    if sbi >= 30:
        ratio = (sbi - 30) / 70
        full_dynamic = result.M * ratio ** 2
        extra_after = max(0, full_dynamic - result.M_min) * 0.85
        amount_breakdown = (
            f"底仓 {result.M_min:.0f} 元 + "
            f"(最大 {result.M:.0f} × {ratio:.2f}^2 - 底仓) × 0.85"
            f" = **{amount:.2f} 元**"
        )
    else:
        amount_breakdown = f"仅买入底仓 **{amount:.2f} 元**"

    content = f"""# 易方达全球成长精选（012922）量化决策
> 理念：不预测涨跌，只对"恐慌与贪婪"做数学反应
> 今日申购窗口：{action}

---
**🧮 最终得分：{sbi}/100**
**💰 建议投入：{amount:.2f} 元**（{amount_breakdown}）

---
**🌍 底层资产吸引力**（涨跌幅→0~100分，跌越多分越高=越便宜）
- A股光模块（35%权重）：{result.r_cpo:+.2f}% → {_attract_comment(f_cpo)}（{f_cpo:.0f}分）
  <font color="comment">（主跌浪折扣：{'已触发，打8折' if l1['tau_cpo']==0.8 else '未触发，不打折'}）</font>
- 纳指期货（55%权重）：{result.r_nq:+.2f}% → {_attract_comment(f_nq)}（{f_nq:.0f}分）
- 人民币汇率（10%权重）：{result.r_fx:+.2f}% → {_attract_comment(f_fx)}（{f_fx:.0f}分）
  <font color="comment">（美元跌=人民币升值=海外资产变便宜）</font>

**🦅 聪明钱提前反应**（用期货偷看今晚美股走向）
- 预估今晚开盘：P_est = {result.p_est:.1f}（昨收 {result.ndx_close_prev:.1f} × 期货变化）{bias_msg}
- 极端崩盘双杀：{'未触发' if alpha.omega_ext==0 else f'+{alpha.omega_ext:.0f}分'}
  <font color="comment">（中美同时暴跌超5%才触发，平时不启动）</font>
- 一年水位位置：{'已跌入底部' + str(alpha.p_pos) + '%区间，+{alpha.omega_pos:.1f}分' if alpha.omega_pos>0 else '未跌入底部20%，不加分'}
  <font color="comment">（价格越低越靠近历史大坑，越加分）</font>
- RSI衰竭信号：{rsi_msg}

**🛡️ 风险过滤器**（防止在错误时机重仓）
- 跳空缺口：{'缺口 > 2倍日常振幅 → 打7折' if tech.omega_vol==0.7 else '正常，不打折'}
  <font color="comment">（盘前突然暴涨暴跌说明出大事了，自动防御）</font>
- 趋势判定：{adx_msg}
- 恐慌指数：VIX={result.vix:.1f} → 放大 **{tech.phi:.2f} 倍**
  <font color="comment">（别人恐慌时我们贪婪，VIX越高买入越多）</font>

---
**⚖️ 最终逻辑：** 底仓雷打不动，加仓按二次方曲线加速，再因下午3点至美股开盘的6.5小时不确定性打85折。"""

    return _post_markdown(webhook_url, content)


def send_capture_result(nq_price: float, backfill_info: list[str],
                        webhook_url: str, stats_summary: str = "") -> bool:
    """NQ 收盘抓取结果推送"""
    backfill_text = "\n> ".join(backfill_info) if backfill_info else "无待补录记录"
    stats_text = stats_summary if stats_summary else "\n> 验证数据积累中，暂无法检验"

    content = f"""## NQ 期货收盘抓取完成
> 收盘价: **{nq_price:.2f}**
> 时间: 美股收盘后自动抓取

**📊 昨日验证补录：**
> {backfill_text}

**📈 模型检验情况：**
{stats_text}

---
<font color=\"comment\">每日 05:15 自动运行 | 为 14:50 模型提供 NQ 昨收数据</font>"""

    return _post_markdown(webhook_url, content)


def send_error_notify(webhook_url: str, error_msg: str) -> bool:
    """错误通知"""
    content = f"## 易方达量化 Agent 异常\n> 错误: {error_msg}\n> 时间: 请检查日志"
    return _post_markdown(webhook_url, content)


def build_stats_text() -> str:
    """构建检验统计摘要文案（小白话）"""
    from yfd_quant.data.db import get_validation_stats, get_fund_navs
    stats = get_validation_stats()
    navs = get_fund_navs()

    parts = []

    if stats["count"] > 0:
        mae = stats["p_est_mae"]
        bias = stats["p_est_bias"]
        bias_word = "高估(预估>实际)" if bias < 0 else "低估(预估<实际)"
        if mae < 1: quality = "优秀"
        elif mae < 2: quality = "良好"
        else: quality = "偏差较大"

        parts.append(f"**P_est 预测**: 均偏差 {mae:.1f}%（{quality}）方向 {bias:+.1f}% {bias_word}")

        for d in stats.get("details", [])[:3]:
            fwd = d.get("forward_return")
            fwd_s = f"{fwd:+.1f}%" if fwd and fwd != 0 else "待补录"
            parts.append(f"> {d['date']}: P_est={d['p_est']:.0f} 实际开={d['actual_open']:.0f} "
                        f"偏差={d['deviation']:+.1f}% | 入场{d['entry_return']:+.1f}% "
                        f"买入后{fwd_s}")

        fwd_avg = stats["avg_forward_return"]
        if fwd_avg != 0:
            parts.append(f"> 买入后平均: {fwd_avg:+.2f}%（正=买入后涨了=赚了）")
    else:
        parts.append("**检验数据**: 积累中，暂无法检验（需1个交易日后自动补录）")

    if navs:
        latest = navs[-1]
        parts.append(f"**基金净值**: {latest['date']} 净值 {latest['nav']:.4f} 日收益 {latest['daily_return']:+.2%}")
    else:
        parts.append("**基金净值**: 暂无，录入: --update-nav 日期,净值,日收益率")

    return "\n".join(parts)
