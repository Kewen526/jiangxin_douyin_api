"""
配置文件 — 抖音来客商家数据下载上传工具
"""

from datetime import datetime, timedelta

# ─────────────────────────────────────────
#  Cookie API 配置
# ─────────────────────────────────────────
COOKIE_API_URL = "https://kewenai.asia/api/cookies/getByCookie"
COOKIE_ACCOUNT = "17746543996"

# ─────────────────────────────────────────
#  抖音来客账号配置
# ─────────────────────────────────────────
ACCOUNT_ID = "1839870566685127"
AC_APP = "10159"

# 留空则自动通过 Playwright 拦截获取
SECSDK_CSRF_TOKEN = ""

# ─────────────────────────────────────────
#  导出配置
# ─────────────────────────────────────────
# 导出日期范围（默认近 30 天：从 30 天前到昨天）
START_DATE = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
END_DATE = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

# 导出字段
DISPLAY_FIELD = [
    "merchant_id", "life_account_name", "industry_name", "service_type",
    "merchant_industry", "follower_name", "merchant_manage_score",
    "pay_amount", "confirm_amount", "refund_amount",
    "item_pay_amount", "room_pay_amount",
    "ledger_commission", "ledger_smc_commission",
]

# ─────────────────────────────────────────
#  输出目录 & 日志文件
# ─────────────────────────────────────────
OUTPUT_DIR = "./downloads"
LOG_FILE = "./app.log"

# ─────────────────────────────────────────
#  轮询参数（等待抖音生成文件）
# ─────────────────────────────────────────
POLL_MAX_TIMES = 20
POLL_INTERVAL = 3  # 秒

# ─────────────────────────────────────────
#  上传 API 配置
# ─────────────────────────────────────────
UPLOAD_API_URL = "https://kewenai.asia/api/douyin/merchant/batchSave"
UPLOAD_BATCH_SIZE = 50  # 每批最多上传条数

# ─────────────────────────────────────────
#  登录状态上报 API
# ─────────────────────────────────────────
LOGIN_STATUS_API_URL = "https://kewenai.asia/api/douyin-login-status/update"
LOGIN_STATUS_ID = 1

# ─────────────────────────────────────────
#  重试配置
# ─────────────────────────────────────────
EMPTY_DATA_RETRY_INTERVAL = 1800  # 30 分钟（秒）
COOKIE_EXPIRED_RETRY_INTERVAL = 3600  # 1 小时（秒）

# ─────────────────────────────────────────
#  定时任务配置
# ─────────────────────────────────────────
SCHEDULE_HOUR = 9   # 每天几点执行
SCHEDULE_MINUTE = 0

# ─────────────────────────────────────────
#  Excel 列名 → API 字段映射
# ─────────────────────────────────────────
EXCEL_COLUMN_MAPPING = {
    # 当前抖音导出列名（完整匹配）
    "商家名称": "merchant_name",
    "商家ID": "merchant_id",
    "行业": "industry",
    "类目": "category",
    "合作模式": "cooperation_mode",
    "跟进人": "follower_name",
    "商家经营分": "merchant_manage_score",
    "支付GMV": "pay_amount",
    "核销GMV": "confirm_amount",
    "退款GMV": "refund_amount",
    "视频直接支付GMV": "item_pay_amount",
    "直播支付GMV": "room_pay_amount",
    "总预估佣金": "ledger_commission",
    "服务商预估佣金": "ledger_smc_commission",
    # 旧版列名（兼容）
    "生活服务账号名称": "merchant_name",
    "服务类型": "category",
    "商家行业": "cooperation_mode",
    "商家管理分": "merchant_manage_score",
    "支付金额": "pay_amount",
    "核销金额": "confirm_amount",
    "退款金额": "refund_amount",
    "商品支付金额": "item_pay_amount",
    "直播间支付金额": "room_pay_amount",
    "分账佣金": "ledger_commission",
    "分账服务商佣金": "ledger_smc_commission",
}

# 不在映射中的列也保留（使用原始列名），确保不丢失数据
KEEP_UNMAPPED_COLUMNS = True

# 金额类字段（需转为数值类型）
NUMERIC_FIELDS = [
    "pay_amount", "confirm_amount", "refund_amount",
    "item_pay_amount", "room_pay_amount",
    "ledger_commission", "ledger_smc_commission",
]
