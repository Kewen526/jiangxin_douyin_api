"""
上传模块 — 分批将商家数据上传到后台 API
"""

import json
import time

import requests

import config


def upload_data(data_rows, data_date):
    """
    分批上传数据。

    - data_rows: list[dict]，parser 解析出的完整数据列表
    - data_date: str，数据日期，如 "2026-03-04"

    返回 (success_count, fail_count)
    """
    total = len(data_rows)
    batch_size = config.UPLOAD_BATCH_SIZE
    batch_count = (total + batch_size - 1) // batch_size

    print(f"\n  共 {total} 条数据，分 {batch_count} 批上传（每批 {batch_size} 条）")

    success_count = 0
    fail_count = 0

    for batch_idx in range(batch_count):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = data_rows[start:end]

        print(f"\n  [{batch_idx + 1}/{batch_count}] 上传第 {start + 1}-{end} 条 ...")

        payload = {
            "data_date": data_date,
            "list": batch,
        }

        try:
            resp = requests.post(
                config.UPLOAD_API_URL,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=30,
            )
            print(f"  状态码：{resp.status_code}")
            print(f"  响应：{resp.text[:500]}")

            if resp.status_code == 200:
                body = resp.json()
                if body.get("success") or body.get("code") == 0:
                    success_count += len(batch)
                    print(f"  本批上传成功：{len(batch)} 条")
                else:
                    fail_count += len(batch)
                    print(f"  本批上传失败（业务错误）：{body}")
            else:
                fail_count += len(batch)
                print(f"  本批上传失败（HTTP {resp.status_code}）")

        except Exception as e:
            fail_count += len(batch)
            print(f"  本批上传异常：{e}")

        # 批次间短暂等待，避免请求过快
        if batch_idx < batch_count - 1:
            time.sleep(1)

    print(f"\n  上传完成：成功 {success_count} 条，失败 {fail_count} 条")
    return success_count, fail_count
