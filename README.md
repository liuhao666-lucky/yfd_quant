# 易方达全球成长精选 (012922) 量化定投 Agent
## ⚠️ 重要声明

**本模型仅为个人量化研究工具，不构成任何投资建议。**

- 所有输出结果（包括 SBI 分数、建议买入金额）仅代表模型基于历史数据的数学计算，**不保证未来收益，也不代表市场真实走势**。
- 使用者需自行承担所有投资风险。作者不对因使用本模型产生的任何直接或间接损失负责。
- 模型依赖的因子可能会失效，回测结果不代表实际业绩。投资前请务必独立判断，并咨询专业持牌机构。
- 本仓库公开的代码、数据和说明仅用于交流学习，**严禁用于商业用途或向他人提供付费投资建议**。

## 📊 数据来源

| 数据项 | 来源 | 说明 |
|--------|------|------|
| A股光模块板块涨跌幅 | 新浪财经 `hq.sinajs.cn` | 实时行情，仅供参考，无担保 |
| 纳指100期货涨跌幅 | 新浪财经 `hq.sinajs.cn` | 实时行情，无担保 |
| VIX 指数 | 新浪财经 `hq.sinajs.cn` | 实时行情，无担保 |
| 美元/离岸人民币汇率 | 新浪财经 `hq.sinajs.cn` | 实时行情，无担保 |
| 纳斯达克100日线数据 | 百度股市通（历史数据） / 新浪财经（补录） | 已内置示例数据 |
| CPO概念板块历史 | 新浪财经 `hq.sinajs.cn` | 实时抓取，首次需积累数据 |
| 基金净值 | 手工录入 `--update-nav` | 从基金公司官网或第三方平台获取 |

> **注意**：所有数据均来自公开免费接口，仅供学习研究，不保证准确性。**勿将数据用于商业分发**。
---

## 1. 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows / macOS / Linux |
| Python | 3.9 或更高 |
| 网络 | 能访问 `hq.sinajs.cn`（国内网络即可） |
| 硬盘 | < 50MB |

### 安装依赖

在项目根目录打开终端，执行：

```bash
pip install pandas requests pyyaml rich pytest
```

验证安装：

```bash
python -c "import pandas, requests, yaml, rich; print('OK')"
```

---

## 2. 从零到运行（5 步）

### 步骤 1：复制配置文件

```bash
copy config.example.yaml config.yaml    # Windows
# 或
cp config.example.yaml config.yaml      # Mac/Linux
```

### 步骤 2：配置投资参数

打开 `config.yaml`，修改前两行：

```yaml
M: 20.0           # 你每天最多投多少钱（元）
M_min: 0.0        # 每天至少投多少钱（元），0 表示可以某天不投
```

### 步骤 3：配置企业微信通知（可选但推荐）

见[第 3 节](#3-企业微信通知配置)。

### 步骤 4：导入纳斯达克 100 历史数据

你需要至少 200 个交易日的 NDX 日线数据来初始化。项目已包含示例数据文件,数据来源百度股市通 `ndx_history_raw.py`：

```bash
python -m yfd_quant.main --import-kline ndx_history_raw.py
```

输出：`已导入 257 条 NDX 历史数据，数据库现有 258 条记录`

如果你有自己的 CSV（格式 `date,open,high,low,close,volume`）：

```bash
python -m yfd_quant.main --import-csv 你的文件.csv
```

### 步骤 5：全功能测试

在首次运行模型前，先执行全功能测试确认一切正常：

```bash
python -m yfd_quant.main --test
```

输出示例：

```
==================================================
  易方达量化 Agent 全功能测试
==================================================

[1/5] 依赖检查...
  OK: pandas, requests, pyyaml, rich

[2/5] 配置文件...
  OK: config.yaml 已加载 (M=20.0, M_min=0.0)

[3/5] Sina API 连通性...
  OK: NDX=29235.0 CPO=9427.9 VIX=19.1 FX=6.7940 NQ=29338.5

[4/5] 数据库...
  OK: NDX 257行 (最新 2026-05-08 close=29235.0) CPO 1行

[5/5] 模型计算 + 单元测试...
  OK: 12 passed

==================================================
  全部通过
==================================================
```

> `--test` 只读不写，不会修改任何数据库表。如果有失败项，根据提示修复后再运行模型。

### 步骤 6：首次运行模型

```bash
python -m yfd_quant.main
```

看到类似以下输出表示成功：

```
CPO +1.26%  |  纳指期货 +2.43%  |  汇率 -0.01%  |  VIX 19.1
模块一: f_CPO=25  f_NQ=1  f_FX=50
SBI 总分: 100.0 / 100
建议买入: CNY 44.00
```

---

## 3. 企业微信通知配置

### 3.1 创建机器人

1. 打开企业微信，进入任意群聊
2. 点击群设置 → 群机器人 → 添加机器人
3. 复制 Webhook 地址（类似 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）

### 3.2 填入配置

编辑 `config.yaml`：

```yaml
notify:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"
```

### 3.3 测试通知

```bash
# 主模型推送（六层滤网完整分解 + 小白话解释）
python -m yfd_quant.main --notify

# NQ 抓取推送（收盘价 + 检验统计）
python -m yfd_quant.main --capture-nq
```

收到消息即配置成功。两个定时任务都会推送。

---

## 4. 全部命令

### 4.1 模型运行

```bash
# 全功能测试（首次使用必跑，只读不写）
python -m yfd_quant.main --test

# 标准运行（仅终端输出）
python -m yfd_quant.main

# 运行并推送到企业微信
python -m yfd_quant.main --notify

# 打印全部中间计算值（调试用）
python -m yfd_quant.main --debug

# 自定义金额
python -m yfd_quant.main -M 100 -m 20

# 仅输出 JSON（供其他程序调用）
python -m yfd_quant.main --json-only
```

### 4.2 数据抓取

```bash
# 抓取 NQ 期货收盘价（美股收盘后运行，约北京时间 05:15）
# 同时自动补录昨天的验证数据 + 推送检验统计
python -m yfd_quant.main --capture-nq
```

### 4.3 历史数据导入

```bash
# 从 Sina K 线格式导入（项目自带的示例数据）
python -m yfd_quant.main --import-kline ndx_history_raw.py

# 从标准 CSV 导入
python -m yfd_quant.main --import-csv 你的数据.csv
```

CSV 格式要求：

```
date,open,high,low,close,volume
2025-01-02,21000.0,21200.0,20900.0,21150.0,1000000
```

### 4.4 基金净值录入

```bash
# 每天基金净值公布后手动录入（T+2 约两天后）
python -m yfd_quant.main --update-nav 2026-05-08,1.2345,-0.0123
#                                      日期         净值   日收益率
```

### 4.5 验证统计

```bash
# 查看模型检验数据
python -m yfd_quant.main --stats
```

---

## 5. 定时任务

### 方案 A：内置调度器（电脑需保持开机）

```bash
python run_scheduler.py
```

定时规则：

| 时间 | 操作 | 说明 |
|------|------|------|
| 05:15 | `--capture-nq` | 抓 NQ 收盘 + 自动补录验证 + 推送检验 |
| 14:50 | `main --notify` | 跑模型 + 推送决策（仅工作日） |

按 `Ctrl+C` 停止。

### 方案 B：Windows 任务计划程序（推荐，无需全天开机）

打开管理员 PowerShell，执行：

```powershell
# NQ 收盘抓取（每天 05:15）
schtasks /create /tn "YFD_CaptureNQ" /tr "cmd /c cd /d d:\项目\基金相关\易方达 && python -m yfd_quant.main --capture-nq" /sc DAILY /st 05:15

# 主模型（工作日 14:50）
schtasks /create /tn "YFD_Main" /tr "cmd /c cd /d d:\项目\基金相关\易方达 && python -m yfd_quant.main --notify" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:50
```

> 电脑需要在 05:15 和 14:50 处于开机状态（或设置唤醒）。

---

## 6. 数据库说明

数据库文件：`output/quant.db`（SQLite 格式，无需安装任何数据库软件）。

用任意 SQLite 工具打开即可查看，推荐 [DB Browser for SQLite](https://sqlitebrowser.org/)（免费）。

### 6.1 ndx_daily — 纳斯达克 100 日线

| 列 | 类型 | 说明 |
|----|------|------|
| date | TEXT (主键) | 日期，如 2026-05-08 |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | INTEGER | 成交量 |

写入方式：凌晨 `--capture-nq` 抓取前一个美股交易日收盘价写入（主），14:50 模型运行同步写入（备，INSERT OR REPLACE 防重复），也可通过 `--import-kline` / `--import-csv` 批量导入历史。

### 6.2 cpo_daily — A 股光模块每日收盘

| 列 | 类型 | 说明 |
|----|------|------|
| date | TEXT (主键) | 日期 |
| close | REAL | CPO 概念板块收盘点位 |

写入方式：工作日模型运行时自动写入。用于计算 CPO 的 20 日均线，判断"主跌浪"折扣。

### 6.3 nq_daily — 纳指期货收盘价

| 列 | 类型 | 说明 |
|----|------|------|
| date | TEXT (主键) | 日期 |
| close | REAL | NQ 期货收盘价 |

写入方式：`--capture-nq` 命令（每日 05:15）。用于计算纳指期货实时涨跌幅 R_NQ。

### 6.4 validation — 模型检验记录

| 列 | 说明 |
|----|------|
| date | 模型运行日期（T 日） |
| sbi | 当日 SBI 得分（0~100） |
| amount | 建议买入金额 |
| r_cpo / r_nq / r_fx / vix | 输入因子（行情） |
| c_prev / p_est | 纳指昨收 / 预估开盘价 |
| base / omega_ext / omega_bias / omega_pos / rsi_bonus | 模块二~三分项得分 |
| phi / tau_adx / omega_vol | 模块四修正因子 |
| bias_pct / rsi / adx | 乖离率 / RSI / ADX 原始值 |
| ndx_actual_open / ndx_actual_close | 补录的实际开盘/收盘 |
| p_est_deviation | P_est 预测偏差 = (实际开-P_est)/P_est×100；正=低估 负=高估 |
| entry_return | 入场日涨跌 = (T收-T-1收)/T-1收×100；负=买到跌=划算 |
| forward_return | 买入后涨跌 = (T+1收-T收)/T收×100；正=买入后涨了=赚了 |

写入方式：工作日模型运行时自动写入（周末不写）。实际开盘/收盘由 `--capture-nq` 自动补录。`forward_return` 需 T+2 凌晨才有数据。

### 6.5 fund_nav — 基金净值

| 列 | 说明 |
|----|------|
| date | 日期 |
| nav | 基金单位净值 |
| daily_return | 日收益率（小数，如 -0.0123 = -1.23%） |

写入方式：手动录入 `--update-nav`。用于检验模型信号与基金实际收益的关系。

---

## 7. 验证系统说明

### 7.1 检验什么

系统追踪三个核心指标：

| 指标 | 公式 | 说明 |
|------|------|------|
| **P_est 偏差率** | (实际开盘 - P_est) / P_est × 100 | 正=低估(实际更高) 负=高估(实际更低) |
| **entry_return** | (T日收盘 - T-1日收盘) / T-1日收盘 × 100 | 入场日 NDX 涨跌；负=买到跌了=划算 |
| **forward_return** | (T+1日收盘 - T日收盘) / T日收盘 × 100 | **买入后涨跌**；正=赚了 负=亏了 |

> entry_return 只是参考（入场当天的涨跌不代表你赚了），**forward_return 才是买入后真正盈亏**。
> 基金含 A 股+美股，最终以 `fund_nav` 表净值为准。

### 7.2 自动补录流程

```
T 日 14:50  →  写入 validation（SBI、P_est，实际数据暂空）
T 日夜间    →  美股交易
T+1 05:15  →  --capture-nq 自动补录 T 日实际开盘/收盘
               → 计算 P_est 偏差 + entry_return
               → forward_return 暂空（T+1 还没收盘）
T+2 05:15  →  --capture-nq 自动补录 forward_return（T+1 已收盘）
```

### 7.3 手动查看

```bash
python -m yfd_quant.main --stats
```

输出示例（含计算过程）：

```
--- 2026-05-08 (SBI=100 强烈买入) ---
  P_est 偏差: (28768.1 - 28564.0) / 28564.0 * 100 = +0.71%
    正=低估(实际>预估)  负=高估(实际<预估)
  entry_return(入场日涨跌): (29235.0 - 28564.0) / 28564.0 * 100 = +2.35%
    负=买到跌了=划算  正=买到涨了=买贵了
  forward_return(买入后涨跌): +0.85%
    正=买入后涨了=赚了  负=买入后跌了

[汇总] P_est 平均绝对偏差: 1.67% | 方向偏差: -1.67%
[汇总] 入场日均收益: +2.35% | 买入后均收益: +0.85%
```

### 7.4 数据不足时

> 检验数据: 积累中，暂无法检验（需 1 个交易日后自动补录）
> 基金净值: 暂无，录入: --update-nav 日期,净值,日收益率

---

## 8. 项目文件结构

```
易方达/
├── config.yaml              # 配置文件（已 gitignore，不上传）
├── config.example.yaml       # 配置文件模板（可安全提交）
├── run_scheduler.py          # 定时调度器
├── ndx_history_raw.py        # NDX 历史数据（Sina K 线格式）
├── README.md                 # 本文档
│
└── yfd_quant/                # 主代码包
    ├── main.py               # CLI 入口，所有命令在这里
    ├── types.py              # 数据类定义
    ├── config.py             # 配置加载（支持环境变量覆盖）
    ├── data/
    │   ├── sina_fetcher.py   # 新浪 hq.sinajs.cn 批量请求
    │   ├── db.py             # SQLite 全部表操作
    │   └── orchestrator.py   # 数据编排：抓取→入库→组装
    ├── indicators/
    │   ├── calculator.py     # 指标计算入口
    │   ├── ma.py             # 移动平均线
    │   ├── atr.py            # 真实波幅（Wilder 平滑）
    │   ├── rsi.py            # 相对强弱（Wilder 平滑）
    │   ├── adx.py            # ADX / +DI / -DI（Wilder 平滑）
    │   └── price_extremes.py # 52 周高低、MA200
    ├── model/
    │   ├── engine.py         # 量化引擎：串联全部六层
    │   ├── layer1_attraction.py  # 模块一
    │   ├── layer2_base.py        # 模块二
    │   ├── layer3_alpha.py       # 模块三
    │   ├── layer4_technical.py   # 模块四
    │   ├── layer5_sbi.py         # 模块五
    │   └── layer6_position.py    # 模块六
    ├── output/
    │   ├── console.py        # 终端格式化输出
    │   ├── json_writer.py    # JSON 历史导出
    │   └── notify.py         # 企业微信推送
    └── tests/
        ├── test_layer1.py    # 吸引力分数测试
        └── test_model.py     # 全模块集成测试
```

---

## 9. 常见问题

**Q: 运行时终端显示乱码？**

Windows 终端默认 GBK 编码，不影响计算。解决：
```bash
python -m yfd_quant.main > result.txt 2>&1    # 重定向到文件看
# 或在 VS Code 终端中运行（默认 UTF-8）
```

**Q: 周末运行显示什么？**

显示 `[周末模式] 以下为周五收盘数据`，R_NQ 用 NQ 期货历史计算周五涨跌幅。周末不写入数据库。

**Q: NQ 昨收缺失怎么办？**

说明 `--capture-nq` 还没运行过。执行一次：
```bash
python -m yfd_quant.main --capture-nq
```
之后每天 05:15 定时运行即可。

**Q: 怎么确认模型算对了？**

```bash
python -m yfd_quant.main --debug    # 打印全部中间值
python -m pytest yfd_quant/tests/   # 运行 12 个单元测试
```

**Q: 配置文件里的 API Key 会泄露吗？**

`config.yaml` 已在 `.gitignore` 中，不会被 Git 提交。提交前执行 `git status` 确认。
