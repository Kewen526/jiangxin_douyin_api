"""
抖音来客 — 商家数据自动下载上传工具

每天定时执行：
  1. 从抖音来客下载商家数据 xlsx
  2. 解析 xlsx，检查是否有实际数据（非空表）
  3. 如果只有标题行（无数据），10 分钟后重试，直到成功
  4. 分批上传到后台 API（每批最多 50 条）
"""

import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta

import requests

import config
from downloader import run_download, CookieExpiredError
from parser import parse_xlsx
from uploader import upload_data


def report_login_status(is_valid):
    """上报登录状态：is_valid=1 有效，is_valid=0 无效"""
    try:
        resp = requests.post(
            config.LOGIN_STATUS_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": config.LOGIN_STATUS_ID, "is_valid": is_valid}),
            timeout=10,
        )
        print(f"  上报登录状态 is_valid={is_valid}，响应：{resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"  上报登录状态失败：{e}")


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
    执行 run_once：
      - 成功 → 上报 is_valid=1，结束
      - 数据为空 → 30 分钟后重试
      - Cookie 失效 → 上报 is_valid=0，1 小时后重试
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
                report_login_status(1)
                print("\n任务完成！")
                return
            else:
                retry_min = config.EMPTY_DATA_RETRY_INTERVAL // 60
                print(f"\n数据尚未就绪，{retry_min} 分钟后重试 ...")
                time.sleep(config.EMPTY_DATA_RETRY_INTERVAL)
        except CookieExpiredError as e:
            print(f"\n执行出错：{e}")
            traceback.print_exc()
            report_login_status(0)
            retry_min = config.COOKIE_EXPIRED_RETRY_INTERVAL // 60
            print(f"\nCookie 已失效，{retry_min} 分钟后重试 ...")
            time.sleep(config.COOKIE_EXPIRED_RETRY_INTERVAL)
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


# ─────────────────────────────────────────
#  CLI 日志检查命令
# ─────────────────────────────────────────

def _read_log_lines(log_file=None):
    """读取日志文件全部行"""
    path = log_file or config.LOG_FILE
    if not os.path.isfile(path):
        print(f"日志文件不存在：{path}")
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def cmd_log(n=50, log_file=None):
    """显示最近 N 行日志"""
    lines = _read_log_lines(log_file)
    if not lines:
        return
    tail = lines[-n:]
    print(f"--- 最近 {len(tail)} 行日志（共 {len(lines)} 行）---\n")
    for line in tail:
        print(line, end="")


def cmd_errors(n=20, log_file=None):
    """显示最近 N 条错误/异常"""
    lines = _read_log_lines(log_file)
    if not lines:
        return
    error_patterns = re.compile(
        r"(Error|Exception|Traceback|错误|失败|出错|过期|超时)", re.IGNORECASE
    )
    matched = []
    for i, line in enumerate(lines):
        if error_patterns.search(line):
            # 包含上下文：前 2 行 + 后 5 行
            start = max(0, i - 2)
            end = min(len(lines), i + 6)
            block = "".join(lines[start:end])
            matched.append(block)
    if not matched:
        print("未发现错误或异常记录。")
        return
    # 去重相邻重叠块，只保留最后 N 条
    unique = []
    for block in matched:
        if not unique or block != unique[-1]:
            unique.append(block)
    recent = unique[-n:]
    print(f"--- 最近 {len(recent)} 条错误（共发现 {len(unique)} 条）---\n")
    for i, block in enumerate(recent, 1):
        print(f"[{i}] {block}")
        print()


def cmd_status(log_file=None):
    """检查进程运行状态和最近活动"""
    # 检查进程
    try:
        result = subprocess.run(
            ["pgrep", "-af", "python.*main.py"],
            capture_output=True, text=True, timeout=5,
        )
        procs = [
            line for line in result.stdout.strip().split("\n")
            if line and "pgrep" not in line
        ]
    except Exception:
        procs = []

    if procs:
        print(f"运行状态：运行中（{len(procs)} 个进程）")
        for p in procs:
            print(f"  PID {p}")
    else:
        print("运行状态：未运行")

    # 日志文件信息
    path = log_file or config.LOG_FILE
    if os.path.isfile(path):
        stat = os.stat(path)
        size_mb = stat.st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n日志文件：{path}")
        print(f"文件大小：{size_mb:.2f} MB")
        print(f"最后修改：{mtime}")
    else:
        print(f"\n日志文件不存在：{path}")
        return

    # 最后几行日志
    lines = _read_log_lines(log_file)
    if lines:
        print(f"\n--- 最后 10 行 ---")
        for line in lines[-10:]:
            print(line, end="")

    # 统计错误数
    error_count = sum(
        1 for line in lines
        if re.search(r"(Error|Exception|失败|出错|过期)", line, re.IGNORECASE)
    )
    print(f"\n\n错误/异常总数：{error_count}")


def print_usage():
    """打印帮助信息"""
    print("用法：python main.py [命令]")
    print()
    print("命令：")
    print("  (无参数)        正常启动定时任务")
    print("  log   [N]       显示最近 N 行日志（默认 50）")
    print("  errors [N]      显示最近 N 条错误记录（默认 20）")
    print("  status          查看进程运行状态和日志摘要")
    print("  help            显示此帮助信息")
    print()
    print("示例：")
    print("  python main.py               # 启动服务")
    print("  python main.py log 100       # 查看最近 100 行日志")
    print("  python main.py errors        # 查看最近错误")
    print("  python main.py status        # 查看运行状态")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        main()
    elif args[0] == "log":
        n = int(args[1]) if len(args) > 1 else 50
        cmd_log(n)
    elif args[0] == "errors":
        n = int(args[1]) if len(args) > 1 else 20
        cmd_errors(n)
    elif args[0] == "status":
        cmd_status()
    elif args[0] in ("help", "-h", "--help"):
        print_usage()
    else:
        print(f"未知命令：{args[0]}")
        print_usage()
