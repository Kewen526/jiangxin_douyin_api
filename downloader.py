"""
下载模块 — 从抖音来客平台导出商家数据 xlsx
"""

import json
import os
import random
import time
from datetime import datetime

import requests as std_requests

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    USE_CURL_CFFI = False
    print("警告：未安装 curl_cffi，将使用普通 requests（可能被 CDN 拦截）")

import config


class CookieExpiredError(RuntimeError):
    """Cookie 或 secsdk_csrf_token 过期"""
    pass


# ─────────────────────────────────────────
#  Cookie
# ─────────────────────────────────────────

def fetch_cookies_from_api(api_url, account):
    """从 API 获取 Cookie，返回 (cookie_dict, raw_cookies_list)"""
    print(f"  请求 Cookie API：{api_url}")
    resp = std_requests.post(
        api_url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"account": account}),
        timeout=15,
    )
    print(f"  API 状态码：{resp.status_code}")
    resp.raise_for_status()

    body = resp.json()
    if not body.get("success"):
        raise ValueError(f"Cookie API 返回失败：{body}")

    cookie_json = body["data"]["cookie_json"]
    print(f"  获取到 {len(cookie_json)} 个 Cookie")

    raw_cookies = [
        {"name": k, "value": v, "domain": ".life-partner.cn", "path": "/"}
        for k, v in cookie_json.items()
    ]
    return cookie_json, raw_cookies


# ─────────────────────────────────────────
#  secsdk_csrf_token
# ─────────────────────────────────────────

def capture_secsdk_token_via_playwright(raw_cookies, account_id, ac_app):
    """通过 Playwright 打开浏览器自动拦截 secsdk_csrf_token"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  未安装 playwright，跳过自动获取")
        return None

    print("  启动浏览器自动获取 secsdk_csrf_token ...")
    captured_token = {"value": None}

    playwright_cookies = []
    for c in raw_cookies:
        pc = {
            "name":   str(c["name"]),
            "value":  str(c.get("value", "")),
            "domain": c.get("domain", ".life-partner.cn"),
            "path":   c.get("path", "/"),
        }
        same_site = c.get("sameSite", "")
        if same_site in ("Strict", "Lax", "None"):
            pc["sameSite"] = same_site
        playwright_cookies.append(pc)

    target_url = (
        "https://www.life-partner.cn/subapp/dp-life-service-provider-pro/"
        "businessData?from_page=order_management"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(playwright_cookies)

        def on_request(request):
            token = request.headers.get("x-secsdk-csrf-token")
            if token and not captured_token["value"]:
                captured_token["value"] = token
                print(f"  拦截到 secsdk_csrf_token：{token[:20]}...")

        page = context.new_page()
        page.on("request", on_request)

        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  页面加载超时或出错（不影响结果）：{e}")

        browser.close()

    return captured_token["value"]


def get_secsdk_token(cookie_dict, raw_cookies, account_id, ac_app):
    """按优先级获取 secsdk_csrf_token"""
    token = (
        cookie_dict.get("secsdk_csrf_token")
        or config.SECSDK_CSRF_TOKEN
        or capture_secsdk_token_via_playwright(raw_cookies, account_id, ac_app)
    )
    return token


# ─────────────────────────────────────────
#  HTTP 工具
# ─────────────────────────────────────────

def build_cookie_header(cookie_dict):
    return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())


def make_headers(cookie_dict, secsdk_token):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json",
        "cookie": build_cookie_header(cookie_dict),
        "origin": "https://www.life-partner.cn",
        "referer": (
            "https://www.life-partner.cn/subapp/dp-life-service-provider-pro/"
            "businessData?from_page=order_management"
        ),
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        ),
        "x-secsdk-csrf-token": secsdk_token,
        "priority": "u=1, i",
    }


def do_post(url, headers, body):
    if USE_CURL_CFFI:
        return curl_requests.post(
            url, headers=headers, json=body, timeout=30, impersonate="chrome120"
        )
    return std_requests.post(
        url, headers=headers, json=body, timeout=30,
        proxies={"http": None, "https": None},
    )


# ─────────────────────────────────────────
#  文件列表 / 创建任务 / 轮询 / 下载
# ─────────────────────────────────────────

def extract_download_urls(data):
    """递归提取所有下载链接"""
    urls = []

    def _find(obj):
        if isinstance(obj, dict):
            for key in ("download_url", "url", "file_url", "link"):
                val = obj.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    urls.append({
                        "url": val,
                        "name": obj.get("file_name", obj.get("name", "")),
                    })
            for v in obj.values():
                _find(v)
        elif isinstance(obj, list):
            for item in obj:
                _find(item)

    _find(data)
    return urls


def get_existing_urls(cookie_dict, account_id, ac_app, secsdk_token):
    """获取当前已有文件的 URL 集合（用于排除旧文件）"""
    url = (
        f"https://www.life-partner.cn/data/life_partner/download/center/v3/"
        f"list_panel?ac_app={ac_app}&accountId={account_id}"
    )
    headers = make_headers(cookie_dict, secsdk_token)
    body = {"download_type": 6, "rand": random.random()}
    resp = do_post(url, headers, body)
    if resp.status_code != 200:
        return set()
    items = extract_download_urls(resp.json())
    existing = {item["url"] for item in items}
    print(f"  当前已有文件数：{len(existing)}")
    return existing


def create_job(cookie_dict, account_id, ac_app, secsdk_token,
               start_date, end_date, display_field):
    """创建导出任务"""
    url = (
        f"https://www.life-partner.cn/data/life_partner/download/center/v3/"
        f"create_job?ac_app={ac_app}&accountId={account_id}"
    )
    body = {
        "download_type": 6,
        "param": {
            "data_type": "cooperation_merchant_cnt",
            "page": 1,
            "limit": 10,
            "start_date": start_date,
            "end_date": end_date,
            "display_field": display_field,
        },
        "@rand": random.random(),
    }
    resp = do_post(url, make_headers(cookie_dict, secsdk_token), body)
    print(f"  create_job 状态码：{resp.status_code}")
    if resp.status_code != 200:
        print(f"  响应：{resp.text[:500]}")
        resp.raise_for_status()
    result = resp.json()
    print(f"  create_job 响应：{json.dumps(result, ensure_ascii=False)}")
    return result


def poll_list_panel(cookie_dict, account_id, ac_app, secsdk_token,
                    existing_urls, max_times=20, interval=3):
    """轮询等待新文件生成"""
    url = (
        f"https://www.life-partner.cn/data/life_partner/download/center/v3/"
        f"list_panel?ac_app={ac_app}&accountId={account_id}"
    )
    headers = make_headers(cookie_dict, secsdk_token)
    for i in range(max_times):
        body = {"download_type": 6, "rand": random.random()}
        resp = do_post(url, headers, body)
        print(f"  [{i + 1}/{max_times}] list_panel 状态码：{resp.status_code}")
        if resp.status_code != 200:
            print(f"  响应：{resp.text[:500]}")
            resp.raise_for_status()
        data = resp.json()
        all_items = extract_download_urls(data)
        new_items = [item for item in all_items if item["url"] not in existing_urls]
        if new_items:
            print(f"  检测到 {len(new_items)} 个新文件"
                  f"（忽略 {len(all_items) - len(new_items)} 个旧文件）")
            return data, new_items
        print(f"  新文件尚未生成，{interval} 秒后重试...")
        time.sleep(interval)
    raise TimeoutError("轮询超时，新文件未能生成")


def _make_download_headers():
    """构造下载文件时的浏览器 Headers，绕过 CDN 空数据限制"""
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "accept-encoding": "gzip, deflate, br, zstd",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.life-partner.cn/",
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "cross-site",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    }


def download_file(url, save_path):
    """下载单个文件（带浏览器 Headers 绕过 CDN 限制）"""
    headers = _make_download_headers()
    if USE_CURL_CFFI:
        resp = curl_requests.get(
            url, headers=headers, timeout=60, impersonate="chrome120"
        )
    else:
        resp = std_requests.get(
            url, headers=headers, timeout=60,
            proxies={"http": None, "https": None},
        )
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(resp.content)
    size_kb = len(resp.content) / 1024
    print(f"  已下载：{save_path}  ({size_kb:.1f} KB)")
    return save_path


# ─────────────────────────────────────────
#  完整下载流程
# ─────────────────────────────────────────

def run_download(start_date=None, end_date=None):
    """
    执行完整下载流程，返回下载的 xlsx 文件路径列表。
    如果任何步骤失败，抛出异常。

    - start_date / end_date: 可选，覆盖 config 中的默认日期范围。
      补全缺失日期时，会传入单天日期。
    """
    use_start = start_date or config.START_DATE
    use_end = end_date or config.END_DATE

    print("\n[1/5] 从 API 获取 Cookie ...")
    cookie_dict, raw_cookies = fetch_cookies_from_api(
        config.COOKIE_API_URL, config.COOKIE_ACCOUNT
    )
    print(f"  accountId = {config.ACCOUNT_ID}")
    print(f"  日期范围  = {use_start} ~ {use_end}")

    print("\n[2/5] 获取 secsdk_csrf_token ...")
    secsdk_token = get_secsdk_token(
        cookie_dict, raw_cookies, config.ACCOUNT_ID, config.AC_APP
    )
    if not secsdk_token:
        raise RuntimeError("无法获取 secsdk_csrf_token，请手动填入 config.SECSDK_CSRF_TOKEN")
    print(f"  secsdk = {secsdk_token[:20]}...")

    print("\n[3/5] 记录现有文件列表 ...")
    existing_urls = get_existing_urls(
        cookie_dict, config.ACCOUNT_ID, config.AC_APP, secsdk_token
    )

    print("\n[4/5] 创建导出任务 ...")
    result = create_job(
        cookie_dict, config.ACCOUNT_ID, config.AC_APP, secsdk_token,
        use_start, use_end, config.DISPLAY_FIELD,
    )
    if result.get("code") != 0:
        raise CookieExpiredError("创建任务失败，请检查 Cookie 或 secsdk_csrf_token 是否过期")

    print("\n[5/5] 等待新文件生成 ...")
    raw_data, new_items = poll_list_panel(
        cookie_dict, config.ACCOUNT_ID, config.AC_APP, secsdk_token,
        existing_urls,
        max_times=config.POLL_MAX_TIMES,
        interval=config.POLL_INTERVAL,
    )

    # 保存原始响应
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(
        config.OUTPUT_DIR,
        f"list_panel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"  原始响应已保存：{json_path}")

    # 下载所有新文件
    print(f"\n下载新文件（共 {len(new_items)} 个）...")
    downloaded_files = []
    for i, item in enumerate(new_items):
        dl_url = item["url"]
        name = item.get("name") or (
            f"抖音来客_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i + 1}.xlsx"
        )
        if not name.endswith(".xlsx"):
            name += ".xlsx"
        save_path = os.path.join(config.OUTPUT_DIR, name)
        try:
            download_file(dl_url, save_path)
            downloaded_files.append(save_path)
        except Exception as e:
            print(f"  下载失败：{e}")
            print(f"  手动下载链接：{dl_url}")

    return downloaded_files
