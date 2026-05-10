"""定时调度器 —— 每日自动运行模型

用法:
  python run_scheduler.py          # 前台运行（Ctrl+C 停止）
  python run_scheduler.py --once   # 仅运行一次主模型
  python run_scheduler.py --nq     # 仅抓取 NQ 收盘价

定时:
  05:15  抓取 NQ 期货收盘价（CME 结算 ~16:15 ET = 夏令时 05:15 / 冬令时 04:15 北京）
  14:50  运行主模型 + 推送通知

电脑要求: 必须保持开机且此脚本在运行。
替代方案: Windows 任务计划程序、云服务器、树莓派。
"""

import time
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("scheduler")

PROJECT_DIR = Path(__file__).parent


def run_nq_capture():
    """抓取 NQ 期货收盘价"""
    logger.info(">>> 抓取 NQ 期货收盘价...")
    try:
        subprocess.run(
            [sys.executable, "-m", "yfd_quant.main", "--capture-nq"],
            cwd=str(PROJECT_DIR), check=True, timeout=30,
            capture_output=True, text=True,
        )
        logger.info("NQ 抓取完成")
    except Exception as e:
        logger.error(f"NQ 抓取失败: {e}")


def run_main_model():
    """运行主模型 + 通知"""
    logger.info(">>> 运行主模型...")
    try:
        subprocess.run(
            [sys.executable, "-m", "yfd_quant.main", "--notify"],
            cwd=str(PROJECT_DIR), check=True, timeout=60,
            capture_output=True, text=True,
        )
        logger.info("主模型完成")
    except Exception as e:
        logger.error(f"主模型失败: {e}")


def is_weekday():
    return datetime.now().weekday() < 5


def scheduler_loop():
    """主循环：每分钟检查一次，到时间执行"""
    logger.info("=" * 50)
    logger.info("易方达量化定投 Agent 调度器已启动")
    logger.info("  05:15 - NQ 期货收盘抓取 (夏令时, 冬令时改 04:15)")
    logger.info("  14:50 - 主模型运行 + 推送")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 50)

    last_nq_date = None
    last_main_date = None

    while True:
        now = datetime.now()
        hm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        # NQ 抓取 — 每天 05:15-05:17 (夏令时) / 冬令时改 04:15
        if hm in ("05:15", "05:16") and last_nq_date != today:
            run_nq_capture()
            last_nq_date = today

        # 主模型 — 工作日 14:50-14:52 窗口内触发
        if hm in ("14:50", "14:51") and last_main_date != today:
            if is_weekday():
                run_main_model()
            else:
                logger.info(f"周末跳过主模型 ({today})")
            last_main_date = today

        time.sleep(30)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_main_model()
    elif "--nq" in sys.argv:
        run_nq_capture()
    else:
        scheduler_loop()
