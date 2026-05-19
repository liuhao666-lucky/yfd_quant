"""易方达量化定投 Agent —— CLI 入口

用法:
  python -m yfd_quant.main                     # 运行模型
  python -m yfd_quant.main --notify            # 运行 + 推送通知
  python -m yfd_quant.main --import-csv data.csv  # 导入 NDX 历史数据
  python -m yfd_quant.main -M 100 -m 20        # 自定义金额
  python -m yfd_quant.main --backfill-all       # 批量补录 validation 实际数据
  python -m yfd_quant.main --capture-nq         # 抓取收盘数据(05:15定时任务)
  python -m yfd_quant.main --stats              # 查看模型验证统计
  python -m yfd_quant.main --recalc-snapshot 2026-05-12  # 重算快照指标
"""

import argparse
import logging
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

from yfd_quant.config import load_config
from yfd_quant.data.orchestrator import fetch_all, DataUnavailableError
from yfd_quant.data.db import (
    import_csv, import_from_sina_kline, count as db_count,
    insert_nq_daily, get_nq_prev_close,
    save_validation, save_snapshot, get_snapshot, snapshot_to_result,
    snapshot_to_market_snapshot, update_snapshot_derived,
    update_actual, get_pending_validations, backfill_all_pending, fix_forward_returns,
    get_validation_stats,
    insert_fund_nav, get_fund_navs,
)
from yfd_quant.model.engine import QuantEngine
from yfd_quant.output.console import render as console_render, render_debug
from yfd_quant.output.json_writer import write_single, append_history
from yfd_quant.fund_info import get_latest_nav
from yfd_quant.output.notify import (
    send_model_result, send_capture_result, send_error_notify,
)


def setup_logging(config):
    log_cfg = config.get("log", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler()]
    log_file = log_cfg.get("file")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def main():
    parser = argparse.ArgumentParser(
        description="易方达全球成长精选 (012922) 量化定投决策 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python -m yfd_quant.main                # 运行模型\n"
               "  python -m yfd_quant.main --notify       # 运行并推送通知\n"
               "  python -m yfd_quant.main --import-csv ndx_200days.csv  # 导入历史数据",
    )
    parser.add_argument("-c", "--config", default=None, help="配置文件路径")
    parser.add_argument("-M", "--max-amount", type=float, default=None, help="单日最大申购额")
    parser.add_argument("-m", "--min-amount", type=float, default=None, help="每日强制底仓")
    parser.add_argument("--notify", action="store_true", help="运行后推送通知")
    parser.add_argument("--json-only", action="store_true", help="仅输出 JSON")
    parser.add_argument("--import-csv", metavar="PATH", help="导入 NDX 历史 CSV 到 SQLite")
    parser.add_argument("--import-kline", metavar="FILE.py",
                        help="从 Sina K线格式 Python 文件导入")
    parser.add_argument("--import-cpo", metavar="FILE.json",
                        help="导入 CPO 历史数据 (中证指数 JSON)")
    parser.add_argument("--capture-nq", action="store_true",
                        help="抓取当前 NQ 期货价格存入数据库（美股收盘时运行）")
    parser.add_argument("--backfill-actual", metavar="DATE,OPEN,CLOSE",
                        help="补录某日实际纳指100开盘收盘，格式: 2026-05-08,29200,29500")
    parser.add_argument("--backfill-all", action="store_true",
                        help="从 ndx_daily 批量补录所有缺失的 validation 实际数据")
    parser.add_argument("--recalc-snapshot", metavar="DATE",
                        help="重算快照表中指定日期的模型指标（手动修改输入后使用）")
    parser.add_argument("--stats", action="store_true",
                        help="显示模型验证统计")
    parser.add_argument("--update-nav", metavar="DATE,NAV,RETURN",
                        help="录入基金净值，格式: 2026-05-08,1.2345,-0.0123")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    parser.add_argument("--debug", action="store_true", help="打印模型全部指标")
    parser.add_argument("--test", action="store_true", help="运行全功能测试（不影响数据库）")

    args = parser.parse_args()

    # 加载配置
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.verbose:
        config["log"]["level"] = "DEBUG"

    setup_logging(config)
    logger = logging.getLogger(__name__)

    # ---- YFD Quant Agent Self-Test (read-only, no DB writes) ----
    if args.test:
        print("=" * 50)
        print("  YFD Quant Agent - Self Test")
        print("=" * 50)

        errors = []

        # 1. Dependencies
        print("\n[1/5] Dependencies...")
        try:
            import pandas, requests, yaml, rich  # noqa: F401
            print("  OK: pandas, requests, pyyaml, rich")
        except ImportError as e:
            errors.append(f"Dependency missing: {e}")
            print(f"  FAIL: {e}")

        # 2. Config
        print("\n[2/5] Config file...")
        try:
            config = load_config(args.config)
            print(f"  OK: config.yaml loaded (M={config.get('M')}, M_min={config.get('M_min')})")
        except FileNotFoundError:
            errors.append("config.yaml not found. Copy config.example.yaml to config.yaml")
            print("  FAIL: config.yaml not found")

        # 3. Sina API
        print("\n[3/5] Sina API connectivity...")
        try:
            from yfd_quant.data.sina_fetcher import fetch_all as sina_fetch
            s = sina_fetch()
            if s.ok:
                print(f"  OK: NDX={s.ndx_price:.1f} CPO={s.cpo_price:.1f} VIX={s.vix:.1f} FX={s.fx_price:.4f} NQ={s.nq_price:.1f}")
            else:
                errors.append(f"Sina data error: {s.error}")
                print(f"  FAIL: {s.error}")
        except Exception as e:
            errors.append(f"Sina connection failed: {e}")
            print(f"  FAIL: {e}")

        # 4. Database
        print("\n[4/5] Database...")
        try:
            from yfd_quant.data.db import get_all, cpo_count
            ndx_n = db_count()
            cpo_n = cpo_count()
            if ndx_n > 0:
                df = get_all()
                latest = df.iloc[-1]
                print(f"  OK: NDX {ndx_n} rows (latest {df.index[-1].date()} close={latest['close']:.1f}) CPO {cpo_n} rows")
            else:
                errors.append("NDX history empty. Run: --import-kline ndx_history_raw.py")
                print("  FAIL: NDX history empty")
        except Exception as e:
            errors.append(f"Database error: {e}")
            print(f"  FAIL: {e}")

        # 5. Unit tests
        print("\n[5/5] Unit tests...")
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", "yfd_quant/tests/", "-q"],
            cwd=str(Path(__file__).parent.parent), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            passed = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else "OK"
            print(f"  OK: {passed}")
        else:
            errors.append("Unit tests failed")
            print(f"  FAIL:\n{result.stdout[-300:]}{result.stderr[-200:]}")

        # Notify config
        wc = config.get("notify", {}).get("wecom_webhook", "")
        print(f"\nNotify: {'configured' if wc else 'not set (optional)'}")

        # Summary
        print("\n" + "=" * 50)
        if errors:
            print(f"  {len(errors)} FAILED:")
            for e in errors:
                print(f"    - {e}")
        else:
            print("  ALL PASSED")
        print("=" * 50)
        return

    # ---- NQ 期货收盘抓取 + 自动补录昨日验证 ----
    if args.capture_nq:
        from yfd_quant.data.sina_fetcher import (
            fetch_all as sina_fetch,
            get_us_equity_trade_date, get_cpo_trade_date, get_fx_trade_date,
            is_us_close_window,
        )
        from yfd_quant.data.db import has_final_record
        s = sina_fetch()
        if not s.ok:
            print("Sina fetch failed")
            sys.exit(1)

        now = datetime.now()
        op_time = now.strftime("%Y-%m-%d %H:%M:%S")
        # 收盘后窗口: 夏令时 04-06, 冬令时 05-07
        in_close_window = is_us_close_window(now)
        close_mode = in_close_window
        is_final = 1 if in_close_window else 0

        us_date = get_us_equity_trade_date(now, is_close_mode=close_mode)
        cpo_date = get_cpo_trade_date(now, is_close_mode=close_mode)
        fx_date = get_fx_trade_date(now)
        print(f"window={'close' if in_close_window else 'open'} is_final={is_final} "
              f"us={us_date} cpo={cpo_date} fx={fx_date}")
        if not in_close_window:
            print("WARNING: 非美股收盘窗口，is_final=0（盘中临时数据）")

        from yfd_quant.data.db import (
            insert_daily, insert_cpo_daily, insert_fx_daily, insert_vix_daily,
        )

        def _should_write(table, date):
            if in_close_window:
                return True
            return not has_final_record(table, date)

        n = 0
        # 1. NQ
        if s.nq_price > 0 and _should_write("nq_daily", us_date):
            insert_nq_daily(us_date, s.nq_open, s.nq_high, s.nq_low,
                            s.nq_price, op_time, is_final=is_final)
            print(f"[{n+1}/5] NQ: {us_date} C={s.nq_price:.1f} is_final={is_final}")
            n += 1

        # 2. NDX
        if s.ndx_open > 0 and s.ndx_price > 0:
            insert_daily(us_date, s.ndx_open, s.ndx_high,
                         s.ndx_low, s.ndx_price, s.ndx_volume, op_time)
            print(f"[{n+1}/5] NDX: {us_date} C={s.ndx_price:.1f} V={s.ndx_volume}")
            n += 1

        # 3. CPO (中证指数)
        if s.cpo_price > 0:
            insert_cpo_daily(cpo_date, s.cpo_open, s.cpo_price, s.cpo_price,
                             s.cpo_price, s.cpo_change, s.cpo_change_pct, op_time)
            print(f"[{n+1}/5] CPO: {cpo_date} C={s.cpo_price:.1f} chg={s.cpo_change_pct:+.2f}%")
            n += 1

        # 4. FX
        if s.fx_price > 0 and _should_write("fx_daily", us_date):
            insert_fx_daily(us_date, s.fx_price, op_time, is_final=is_final)
            print(f"[{n+1}/5] FX: {us_date} C={s.fx_price:.4f} is_final={is_final}")
            n += 1

        # 5. VIX
        if s.vix > 0 and _should_write("vix_daily", us_date):
            insert_vix_daily(us_date, s.vix_open, s.vix_high, s.vix_low,
                             s.vix, op_time, is_final=is_final)
            print(f"[{n+1}/5] VIX: {us_date} C={s.vix:.2f} is_final={is_final}")
            n += 1

        # validation 补录：先用 ndx_daily 创建缺失行，再用实时数据更新
        filled = backfill_all_pending()
        if filled:
            print(f"[4/4] 从 ndx_daily 补录 validation: {filled}")
        # 修复 forward_return=0 但下一天数据已有的记录
        fixed_fwd = fix_forward_returns()
        if fixed_fwd:
            print(f"[4/4] 修复 forward_return: {fixed_fwd}")
        pending = get_pending_validations()
        msg_parts = []
        if pending and s.ndx_open > 0 and s.ndx_price > 0:
            latest_pending = pending[-1]
            update_actual(latest_pending["date"], s.ndx_open, s.ndx_price)
            msg = f"{latest_pending['date']}: 开={s.ndx_open:.1f} 收={s.ndx_price:.1f}"
            print(f"[4/4] 已补录 {msg}")
            msg_parts.append(msg)
            # 如果还有更早的未补录，提示用户手动处理
            if len(pending) > 1:
                old_dates = [p["date"] for p in pending[:-1]]
                print(f"[!] 尚有 {len(old_dates)} 条断档未补: {old_dates}")
                print(f"    手动: --backfill-actual 日期,开盘,收盘")
        elif pending:
            print(f"[4/4] 跳过补录 ({len(pending)}条待补录)")

        # 6. 基金净值（自动从接口获取）
        try:
            nav_data = get_latest_nav(config.get("fund_code", "012922"))
            if nav_data:
                insert_fund_nav(nav_data["date"], nav_data["nav"],
                                nav_data["daily_return"])
                print(f"[6] 基金净值: {nav_data['date']} NAV={nav_data['nav']:.4f}")
        except Exception as e:
            print(f"[6] 基金净值获取失败: {e}")

        # 推送
        wc = config.get("notify", {}).get("wecom_webhook", "")
        if wc:
            ok = send_capture_result(s, msg_parts, wc)
            print(f"企业微信推送: {'成功' if ok else '失败'}")
        return

    # ---- 录入基金净值 ----
    if args.update_nav:
        parts = args.update_nav.split(",")
        if len(parts) < 2:
            print("格式: --update-nav 2026-05-08,1.2345,-0.0123")
            sys.exit(1)
        date = parts[0].strip()
        nav = float(parts[1])
        ret = float(parts[2]) if len(parts) > 2 else 0.0
        insert_fund_nav(date, nav, ret)
        print(f"已录入: {date} 净值={nav:.4f} 日收益={ret:+.2%}")
        navs = get_fund_navs()
        print(f"现有 {len(navs)} 条净值记录")
        return

    # ---- 补录实际数据 ----
    if args.backfill_actual:
        parts = args.backfill_actual.split(",")
        if len(parts) != 3:
            print("格式错误。示例: --backfill-actual 2026-05-08,29200,29500")
            sys.exit(1)
        update_actual(parts[0].strip(), float(parts[1]), float(parts[2]))
        print(f"已补录 {parts[0]}: 开盘={parts[1]} 收盘={parts[2]}")
        pending = get_pending_validations()
        if pending:
            print(f"尚有 {len(pending)} 条待补录")
            for p in pending:
                print(f"  {p['date']}: P_est={p['p_est']:.1f}")
        return

    # ---- 批量补录所有缺失的 validation ----
    if args.backfill_all:
        filled = backfill_all_pending()
        if filled:
            print(f"已从 ndx_daily 补录 {len(filled)} 条: {filled}")
        else:
            print("无需补录（所有 validation 已有 actual 数据或 ndx_daily 无对应记录）")
        pending = get_pending_validations()
        if pending:
            print(f"仍有 {len(pending)} 条因 ndx_daily 缺数据无法补录:")
            for p in pending:
                print(f"  {p['date']}: P_est={p['p_est']:.1f}")
        return

    # ---- 重算快照指标 ----
    if args.recalc_snapshot:
        from yfd_quant.data.db import get_all as get_ndx
        date = args.recalc_snapshot.strip()
        snap = get_snapshot(date)
        if not snap:
            print(f"快照表中无 {date} 的记录")
            sys.exit(1)

        # 加载 NDX 历史数据（截止到该日期）
        ndx_df = get_ndx()
        if ndx_df.empty:
            print("NDX 历史数据为空")
            sys.exit(1)
        ndx_hist = ndx_df[ndx_df.index <= pd.Timestamp(date)]
        if len(ndx_hist) < 200:
            print(f"NDX 历史截止 {date} 仅 {len(ndx_hist)} 行，不足 200 行")
            sys.exit(1)

        # 重建 MarketSnapshot 并跑模型
        ms = snapshot_to_market_snapshot(snap, ndx_hist)
        engine = QuantEngine()
        try:
            result = engine.run(ms, M=snap["M"], M_min=snap["M_min"])
        except ValueError as e:
            print(f"模型计算失败: {e}")
            sys.exit(1)

        # 更新快照表中的计算指标
        update_snapshot_derived(date, result)
        print(f"已重算 {date} 快照指标: SBI={result.sbi:.1f}, Amount={result.recommended_amount:.2f}")
        print(f"  P_est={result.p_est:.2f}, Base={result.layer2_base:.2f}")
        print(f"  Ω_EXT={result.alpha.omega_ext}, Ω_BIAS={result.alpha.omega_bias:.2f}, Ω_POS={result.alpha.omega_pos:.2f}")
        return

    # ---- 验证统计 ----
    if args.stats:
        stats = get_validation_stats()
        navs = get_fund_navs()

        print("=== 模型验证统计 ===\n")
        if stats["count"] == 0:
            print("暂无验证数据。每天 05:15 --capture-nq 自动补录。")
        else:
            for d in stats["details"]:
                sbi_label = "强烈买入" if d["sbi"] >= 70 else ("适当买入" if d["sbi"] >= 40 else "仅底仓")
                fwd = d["forward_return"]
                fwd_str = f"{fwd:+.2f}%" if fwd and fwd != 0 else "待次日补录"
                fund_entry = d.get("fund_entry_return")
                fund_fwd = d.get("fund_forward_return")
                fund_entry_str = f"{fund_entry:+.2f}%" if fund_entry else "--"
                fund_fwd_str = f"{fund_fwd:+.2f}%" if fund_fwd else "待T+2补录"
                print(f"--- {d['date']} (SBI={d['sbi']:.0f} {sbi_label}) ---")
                print(f"  P_est 偏差: {d['deviation_calc']}")
                print(f"    正=低估(实际>预估)  负=高估(实际<预估)")
                print(f"  NDX entry_return(入场日涨跌): {d['entry_calc']}")
                print(f"  NDX forward_return(买入后涨跌): {fwd_str}")
                print(f"  基金 entry_return(入场日涨跌): {fund_entry_str}")
                print(f"  基金 forward_return(买入后涨跌): {fund_fwd_str}")
                print()

            print(f"[汇总] P_est 平均绝对偏差: {stats['p_est_mae']:.2f}% | 方向偏差: {stats['p_est_bias']:+.2f}%")
            print(f"[汇总] NDX 入场日均收益: {stats['avg_entry_return']:+.2f}% | 买入后均收益: {stats['avg_forward_return']:+.2f}%")
            print(f"[汇总] 基金入场日均收益: {stats['avg_fund_entry_return']:+.2f}% | 买入后均收益: {stats['avg_fund_forward_return']:+.2f}%")
            print(f"[分桶] SBI<30: {stats['sbi_buckets']['low']['count']}天 | 30-70: {stats['sbi_buckets']['mid']['count']}天 | >=70: {stats['sbi_buckets']['high']['count']}天")

        if navs:
            print(f"\n[基金净值] ({len(navs)} 条)")
            for n in navs[-5:]:
                print(f"  {n['date']}  净值={n['nav']:.4f}  日收益={n['daily_return']:+.2%}")
        else:
            print(f"\n[基金净值] 暂无。录入: --update-nav 日期,净值,日收益率")
        return

    # ---- 导入模式 ----
    if args.import_csv or args.import_kline:
        if args.import_csv:
            try:
                n = import_csv(args.import_csv)
            except FileNotFoundError as e:
                print(f"错误: {e}")
                sys.exit(1)
        else:
            # 从 Python 文件读取 raw_data 字符串
            import importlib.util
            spec = importlib.util.spec_from_file_location("data_mod", args.import_kline)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "raw_data"):
                print("错误: 文件中未找到 raw_data 变量")
                sys.exit(1)
            n = import_from_sina_kline(mod.raw_data)
        print(f"已导入 {n} 条 NDX 历史数据")
        print(f"数据库现有 {db_count()} 条记录")
        return

    # ---- 导入 CPO 历史 ----
    if args.import_cpo:
        import json
        from yfd_quant.data.db import insert_cpo_daily
        with open(args.import_cpo, encoding="utf-8") as f:
            data = json.load(f)
        n = 0
        for row in data:
            dr = row["tradeDate"]
            d = f"{dr[:4]}-{dr[4:6]}-{dr[6:]}"
            insert_cpo_daily(d, row["open"], row["high"], row["low"],
                            row["close"], row["change"], row["changePct"])
            n += 1
        print(f"Imported {n} CPO records")
        return

    # 合并 CLI 参数
    M = args.max_amount if args.max_amount is not None else config.get("M", 50.0)
    M_min = args.min_amount if args.min_amount is not None else config.get("M_min", 10.0)
    tz_discount = config.get("timezone_discount", 0.85)

    logger.info(f"参数: M={M}, M_min={M_min}")

    # ---- 优先使用今日快照（跳过 Sina 请求和模型计算） ----
    today_str = datetime.now().strftime("%Y-%m-%d")
    snap = get_snapshot(today_str)

    if snap:
        # 快照已存在，直接使用，不请求接口
        display_result = snapshot_to_result(snap)
        weekend = datetime.now().weekday() >= 5
        logger.info(f"使用今日快照 (SBI={display_result.sbi}, Amount={display_result.recommended_amount})")
    else:
        # 无快照，正常流程：抓取数据 → 跑模型 → 存快照
        logger.info(f"数据源: Sina hq.sinajs.cn 批量请求")

        try:
            market_snapshot, weekend = fetch_all()
            logger.info(f"数据就绪, NDX历史: {db_count()} 天, 周末: {weekend}")
        except DataUnavailableError as e:
            logger.error(f"数据获取失败: {e}")
            if args.notify:
                send_error_notify(config.get("notify", {}).get("wecom_webhook", ""), str(e))
            sys.exit(1)

        from yfd_quant.data.db import get_nq_prev_close, get_fx_prev_close
        logger.info(f"NQ 当前={market_snapshot.r_nq:+.2f}% | 昨收(DB)={get_nq_prev_close():.1f}")
        logger.info(f"FX 当前={market_snapshot.r_fx:+.4f}% | 昨收(DB)={get_fx_prev_close():.4f}")

        engine = QuantEngine()
        try:
            display_result = engine.run(market_snapshot, M=M, M_min=M_min, timezone_discount=tz_discount)
        except ValueError as e:
            logger.error(f"模型计算失败: {e}")
            sys.exit(1)

        # 写入快照（仅工作日）
        if not weekend:
            save_snapshot(today_str, display_result)

    out_cfg = config.get("output", {})
    out_dir = Path(out_cfg.get("dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if out_cfg.get("json", True):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        write_single(display_result, out_dir / f"{ts}.json")
        append_history(display_result, Path(out_cfg.get("history_file", "./output/history.json")))

    if not args.json_only:
        console_render(display_result, weekend)
        if args.debug:
            render_debug(display_result)
    else:
        import json
        from yfd_quant.output.json_writer import result_to_dict
        print(json.dumps(result_to_dict(display_result), ensure_ascii=False))

    # 推送（用快照数据）
    if args.notify:
        wc = config.get("notify", {}).get("wecom_webhook", "")
        ok = send_model_result(display_result, wc)
        logger.info(f"企业微信推送: {'成功' if ok else '失败'}")

    logger.info(f"完成: SBI={display_result.sbi}, Amount={display_result.recommended_amount:.2f}")


if __name__ == "__main__":
    main()
