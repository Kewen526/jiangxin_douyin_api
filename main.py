"""
抖音来客 — 商家数据自动下载上传工具

每天定时执行：
  1. 从抖音来客下载商家数据 xlsx
  2. 解析 xlsx，检查是否有实际数据（非空表）
  3. 如果只有标题行（无数据），10 分钟后重试，直到成功
  4. 分批上传到后台 API（每批最多 50 条）
"""

import time
import traceback
from datetime import datetime, timedelta

import config
from downloader import run_download
from parser import parse_xlsx
from uploader import upload_data


def get_today_date():
    """返回当天日期字符串，如 2026-03-04"""
    return datetime.now().strftime("%Y-%m-%d")


def seconds_until_next_run(hour, minute):
    """计算距离下一个 hour:minute 还有多少秒"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        # 今天已过，等明天
        target += timedelta(days=1)
    delta = (target - now).total_seconds()
    return delta


def run_once():
    """
    执行一次完整的 下载 → 解析 → 上传 流程。
    如果下载数据为空（只有标题行），返回 False 表示需要重试。
    成功则返回 True。
    """
    today = get_today_date()
    print(f"\n{'=' * 50}")
    print(f"  开始执行  {today}")
    print(f"{'=' * 50}")

    # ── 下载 ──
    print("\n>>> 下载数据 ...")
    downloaded_files = run_download()

    if not downloaded_files:
        print("\n  没有下载到任何文件")
        return False

    # ── 解析 & 上传（逐个文件处理）──
    all_success = True
    for file_path in downloaded_files:
        print(f"\n>>> 解析文件：{file_path}")
        data_rows, raw_row_count = parse_xlsx(file_path)

        if raw_row_count == 0:
            print("  数据为空（仅标题行），需要稍后重试")
            all_success = False
            continue

        print(f"\n>>> 上传数据（{len(data_rows)} 条） ...")
        success_count, fail_count = upload_data(data_rows, today)

        if fail_count > 0:
            print(f"  有 {fail_count} 条上传失败")

    return all_success


def run_with_retry():
    """
    执行 run_once，如果数据为空则每 10 分钟重试，直到成功。
    """
    attempt = 0
    while True:
        attempt += 1
        print(f"\n{'#' * 50}")
        print(f"  第 {attempt} 次尝试")
        print(f"{'#' * 50}")

        try:
            success = run_once()
            if success:
                print("\n任务完成！")
                return
            else:
                retry_min = config.EMPTY_DATA_RETRY_INTERVAL // 60
                print(f"\n数据尚未就绪，{retry_min} 分钟后重试 ...")
                time.sleep(config.EMPTY_DATA_RETRY_INTERVAL)
        except Exception as e:
            print(f"\n执行出错：{e}")
            traceback.print_exc()
            retry_min = config.EMPTY_DATA_RETRY_INTERVAL // 60
            print(f"\n{retry_min} 分钟后重试 ...")
            time.sleep(config.EMPTY_DATA_RETRY_INTERVAL)


def main():
    """
    主入口：定时循环，每天指定时间执行。
    """
    print("=" * 50)
    print("  抖音来客数据自动下载上传工具")
    print(f"  每天 {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} 自动执行")
    print("=" * 50)

    while True:
        wait_seconds = seconds_until_next_run(
            config.SCHEDULE_HOUR, config.SCHEDULE_MINUTE
        )
        next_time = datetime.now() + timedelta(seconds=wait_seconds)
        print(f"\n下次执行时间：{next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"等待 {wait_seconds:.0f} 秒 ...")
        time.sleep(wait_seconds)

        run_with_retry()


if __name__ == "__main__":
    main()
