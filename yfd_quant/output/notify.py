"""企业微信推送通知"""

import requests
from yfd_quant.types import ModelResult


def _post_markdown(webhook_url: str, content: str) -> bool:
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={
            "msgtype": "markdown", "markdown": {"content": content},
        }, timeout=10)
        if resp.status_code != 200:
            return False
        return resp.json().get("errcode") == 0
    except (requests.RequestException, ValueError):
        return False


def _fmt(v, fmt=".2f"):
    return format(v, fmt) if v else "--"


def _trend(v):
    return "📈" if v and v > 0 else ("📉" if v and v < 0 else "➖")


def _day_label(d):
    import datetime
    try:
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        cn = ["周一","周二","周三","周四","周五","周六","周日"]
        return f"{d}（{cn[dt.weekday()]}）"
    except Exception:
        return d


# ====== 主模型推送 ======

def send_model_result(result: ModelResult, webhook_url: str) -> bool:
    sbi = result.sbi
    amount = result.recommended_amount
    color = "warning" if sbi >= 70 else "comment" if sbi >= 40 else "info"

    if sbi >= 70:        action = f"<font color=\"warning\">【强烈建议买入】</font>"
    elif sbi >= 40:      action = f"<font color=\"comment\">【建议适当买入】</font>"
    elif sbi >= 30:      action = f"<font color=\"info\">【少量买入】</font>"
    else:                action = f"<font color=\"info\">【仅买底仓】</font>"

    l1 = result.layer1
    f_cpo, f_nq, f_fx = l1["f_cpo"], l1["f_nq"], l1["f_fx"]

    def _ac(score):
        if score >= 70: return "便宜，加分"
        elif score >= 40: return "中等"
        elif score >= 10: return "偏贵，扣分"
        else: return "很贵，大幅扣分"

    alpha = result.alpha
    bias_val = abs(alpha.bias_pct)

    if alpha.omega_ext > 0:
        bias_note = "（血洗日触发，乖离率互斥关闭）"
    elif alpha.omega_bias > 0:
        bias_note = f"（向下偏离 {bias_val:.1f}%，超卖反弹 +{alpha.omega_bias:.1f}分）"
    elif alpha.bias_pct > 0:
        bias_note = f"（向上偏离 {bias_val:.1f}%，不追高，不加分）"
    else:
        bias_note = f"（乖离率 {bias_val:.1f}%，未触发阈值）"

    tech = result.tech
    if tech.strong_downtrend:
        adx_note = f"ADX={result.indicators.adx:.1f} 强空头 → 打6折，避飞刀"
    elif tech.tau_adx == 0.8:
        adx_note = f"ADX={result.indicators.adx:.1f} 年线下 → 打8折"
    else:
        adx_note = f"ADX={result.indicators.adx:.1f} 正常，不打折"

    content = f"""# 易方达全球成长精选（012922）量化决策
> 理念：不预测涨跌，只对"恐慌与贪婪"做数学反应
> 今日申购窗口：{action}

---
**🧮 最终得分：{sbi}/100**
**💰 建议投入：{amount:.2f} 元**

---
**🌍 底层资产吸引力**（涨跌幅→0~100分，跌越多分越高=越便宜）
- A股光模块（35%）：{result.r_cpo:+.2f}% → {_ac(f_cpo)}（{f_cpo:.0f}分）
  <font color="comment">主跌浪折扣：{'已触发，打8折' if l1['tau_cpo']==0.8 else '未触发'}</font>
- 纳指期货（55%）：{result.r_nq:+.2f}% → {_ac(f_nq)}（{f_nq:.0f}分）
- 人民币汇率（10%）：{result.r_fx:+.2f}% → {_ac(f_fx)}（{f_fx:.0f}分）

**🦅 聪明钱提前反应**
- 预估今晚开盘 P_est={result.p_est:.1f}（昨收{result.ndx_close_prev:.1f}×期货变化）
  <font color="comment">{bias_note}</font>
- 极端崩盘：{'未触发' if alpha.omega_ext==0 else f'+{alpha.omega_ext:.0f}分'}
- 一年水位：{f'底部{alpha.p_pos:.1f}% +{alpha.omega_pos:.1f}分' if alpha.omega_pos>0 else '未跌入底部20%，不加分'}

**🛡️ 风险过滤器**
- 跳空缺口：{'缺口>2倍ATR→打7折' if tech.omega_vol==0.7 else '正常，不打折'}
- 趋势判定：{adx_note}
- 恐慌指数：VIX={result.vix:.1f} → 放大 **{tech.phi:.2f} 倍**

---
**⚖️ 最终逻辑：** 底仓雷打不动，加仓按二次方曲线，再因下午3点至美股开盘的6.5小时不确定性打85折。"""

    return _post_markdown(webhook_url, content)


# ====== 收盘抓取推送 ======

def send_capture_result(sina_data, backfill_msgs: list[str],
                        webhook_url: str) -> bool:
    """05:15 收盘抓取结果推送 —— 完整市场数据 + 验证 + 统计"""
    from yfd_quant.data.db import (
        get_validation_stats, get_fund_navs, get_pending_validations, count,
    )
    from datetime import datetime

    now = datetime.now()
    date_label = _day_label(now.strftime("%Y-%m-%d"))

    # ---- 区块1: 收盘数据总览 ----
    rows = []
    assets = [
        ("📈 NQ 期货", sina_data.nq_price,
         "美股科技股期货收盘价，代表今晚预期走势"),
        ("📊 NDX 现货", sina_data.ndx_price,
         "纳斯达克100指数实际收盘"),
        ("😨 VIX 期货", sina_data.vix,
         "恐慌指数，<20正常 20-30警惕 >30恐慌"),
        ("💡 CPO 概念", sina_data.cpo_price,
         "A股光模块板块收盘"),
        ("💱 离岸人民币", sina_data.fx_price,
         "USDCNH收盘价"),
    ]
    for name, val, desc in assets:
        v = f"**{val:.2f}**" if val and val > 0 else "暂未获取"
        rows.append(f"| {name} | {v} | {desc} |")

    # ---- 区块2: 验证补录 ----
    pending = get_pending_validations()
    val_block = ""
    if pending:
        val_block = "| 项目 | 数值 |\n|------|------|\n"
        latest = pending[-1]
        val_block += f"| 模型预估 P_est | **{latest['p_est']:.1f}** |\n"
        val_block += f"| 实际开盘 | **{sina_data.ndx_open:.1f}** |\n"
        dev = ((sina_data.ndx_open - latest['p_est']) / latest['p_est'] * 100
               ) if latest['p_est'] > 0 else 0
        val_block += f"| 偏差 | **{dev:+.2f}%** |\n"
        if dev < 0:
            comment = "实际开盘比预估**低** → 买入更划算（买到更低价格）✅"
        else:
            comment = "实际开盘比预估**高** → 模型低估了开盘价"
        val_block += f"\n> {comment}"
    else:
        val_block = "无待补录数据"

    # ---- 区块3: 统计 ----
    stats = get_validation_stats()
    stat_block = ""
    if stats["count"] >= 5:
        mae = stats["p_est_mae"]
        bias = stats["p_est_bias"]
        mae_word = "很准 ✅" if mae < 0.5 else ("良好" if mae < 1.5 else "一般")
        bias_word = "低估" if bias > 0 else "高估"
        fwd_avg = stats["avg_forward_return"]
        fwd_s = f"**{fwd_avg:+.2f}%**" if fwd_avg != 0 else "待补录"

        stat_block = f"""| 指标 | 数值 | 白话解释 |
|------|------|----------|
| 预测偏差 (MAE) | {mae:.2f}% {mae_word} | 平均每次预测误差 |
| 方向偏差 | {bias:+.2f}% | 整体略微**{bias_word}**开盘价 |
| 入场日收益 | {stats['avg_entry_return']:+.2f}% | 买入当天基金平均涨跌 |
| 买入后收益 | {fwd_s} | 买入后次日涨跌（次日补录） |"""
    elif stats["count"] > 0:
        stat_block = f"样本较少（{stats['count']}天），暂不统计"
    else:
        stat_block = "暂无检验数据，积累中"

    # ---- 组装 ----
    content = f"""# 收盘数据总览

📅 **数据日期**：{date_label}
⏰ 抓取时间：{now.strftime('%H:%M')}（美股收盘后自动执行）

---

### 🌙 市场收盘数据

| 品种 | 收盘价 | 说明 |
|------|--------|------|
{chr(10).join(rows)}

> 这些价格将用于下午模型的"多因子底仓"计算。

---

### 🔍 模型预测验证（昨日 vs 实际开盘）

{val_block}

---

### 📈 模型近期表现

{stat_block}

---

### 💡 下一步

下午 **14:50** 主模型将根据以上数据计算 **今日 SBI 总分** 和 **建议买入金额**，届时会自动推送。

---

🔁 每日 05:15 自动运行 | 为 14:50 模型提供收盘数据"""

    return _post_markdown(webhook_url, content)


# ====== 错误通知 ======

def send_error_notify(webhook_url: str, error_msg: str) -> bool:
    content = f"## 易方达量化 Agent 异常\n> 错误: {error_msg}\n> 时间: 请检查日志"
    return _post_markdown(webhook_url, content)
