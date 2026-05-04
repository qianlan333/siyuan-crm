from __future__ import annotations

from typing import Any


class CRMError(Exception):
    def __init__(self, code: str, message: str = "", *, detail: str = "", retryable: bool = False) -> None:
        info = ERROR_REGISTRY.get(code, {})
        self.code = code
        self.message = message or info.get("message", code)
        self.detail = detail
        self.retryable = retryable if retryable else info.get("retryable", False)
        self.category = info.get("category", "unknown")
        super().__init__(f"[{code}] {self.message}")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "error_code": self.code,
            "message": self.message,
            "category": self.category,
            "retryable": self.retryable,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


# --- 企微 API 类 (E1xxx) ---
WECOM_TOKEN_EXPIRED = "E1001"
WECOM_PERMISSION_DENIED = "E1002"
WECOM_RATE_LIMITED = "E1003"
WECOM_CONTACT_NOT_FOUND = "E1004"
WECOM_API_ERROR = "E1005"
WECOM_NETWORK_ERROR = "E1006"
WECOM_CIRCUIT_OPEN = "E1007"

# --- 配置类 (E2xxx) ---
CONFIG_MISSING_REQUIRED = "E2001"
CONFIG_INVALID_VALUE = "E2002"
CONFIG_CONNECTION_FAILED = "E2003"

# --- 同步类 (E3xxx) ---
SYNC_ARCHIVE_FAILED = "E3001"
SYNC_CONTACT_FAILED = "E3002"
SYNC_GROUP_CHAT_FAILED = "E3003"

# --- 任务类 (E4xxx) ---
TASK_QUEUE_FULL = "E4001"
TASK_RETRY_EXHAUSTED = "E4002"
TASK_EXECUTION_FAILED = "E4003"

# --- 回调类 (E5xxx) ---
CALLBACK_DECRYPT_FAILED = "E5001"
CALLBACK_EVENT_NOT_FOUND = "E5002"
CALLBACK_PROCESSING_FAILED = "E5003"

# --- 业务逻辑类 (E6xxx) ---
CUSTOMER_NOT_FOUND = "E6001"
QUESTIONNAIRE_NOT_FOUND = "E6002"
AUTOMATION_RULE_INVALID = "E6003"


ERROR_REGISTRY: dict[str, dict[str, Any]] = {
    WECOM_TOKEN_EXPIRED: {
        "message": "企微 Token 已过期",
        "category": "wecom_api",
        "retryable": True,
        "troubleshoot": "系统会自动刷新 Token 并重试。如果持续出现，请检查 WECOM_SECRET 是否正确。",
    },
    WECOM_PERMISSION_DENIED: {
        "message": "企微 API 权限不足",
        "category": "wecom_api",
        "retryable": False,
        "troubleshoot": "检查应用权限配置，确认已授权所需的 API 接口范围。",
    },
    WECOM_RATE_LIMITED: {
        "message": "企微 API 频率限制",
        "category": "wecom_api",
        "retryable": True,
        "troubleshoot": "系统会自动退避重试。如果频繁出现，考虑降低并发操作频率。",
    },
    WECOM_CONTACT_NOT_FOUND: {
        "message": "外部联系人不存在",
        "category": "wecom_api",
        "retryable": False,
        "troubleshoot": "联系人可能已被删除或未同步，尝试重新同步通讯录。",
    },
    WECOM_API_ERROR: {
        "message": "企微 API 返回错误",
        "category": "wecom_api",
        "retryable": True,
        "troubleshoot": "查看具体 errcode 和 errmsg，参照企微开发文档。",
    },
    WECOM_NETWORK_ERROR: {
        "message": "企微 API 网络连接失败",
        "category": "wecom_api",
        "retryable": True,
        "troubleshoot": "检查服务器网络连接和防火墙配置，确认能访问 qyapi.weixin.qq.com。",
    },
    WECOM_CIRCUIT_OPEN: {
        "message": "企微 API 熔断保护已触发",
        "category": "wecom_api",
        "retryable": True,
        "troubleshoot": "连续多次 API 调用失败，系统暂停请求 60 秒后自动恢复。",
    },
    CONFIG_MISSING_REQUIRED: {
        "message": "缺少必填配置项",
        "category": "config",
        "retryable": False,
        "troubleshoot": "前往配置检查清单 /admin/config/checklist 查看缺失项。",
    },
    CONFIG_INVALID_VALUE: {
        "message": "配置值无效",
        "category": "config",
        "retryable": False,
        "troubleshoot": "检查配置值格式是否符合要求。",
    },
    CONFIG_CONNECTION_FAILED: {
        "message": "配置连通性测试失败",
        "category": "config",
        "retryable": True,
        "troubleshoot": "检查网络连接和填写的凭据是否正确。",
    },
    SYNC_ARCHIVE_FAILED: {
        "message": "会话归档同步失败",
        "category": "sync",
        "retryable": True,
        "troubleshoot": "检查会话存档 SDK 配置和私钥是否正确，查看 archive_sync 日志。",
    },
    SYNC_CONTACT_FAILED: {
        "message": "联系人同步失败",
        "category": "sync",
        "retryable": True,
        "troubleshoot": "检查通讯录 Secret 权限配置，查看 contacts_sync 日志。",
    },
    SYNC_GROUP_CHAT_FAILED: {
        "message": "群聊同步失败",
        "category": "sync",
        "retryable": True,
        "troubleshoot": "检查应用权限中是否包含「客户群」读取权限。",
    },
    TASK_QUEUE_FULL: {
        "message": "任务队列已满",
        "category": "task",
        "retryable": True,
        "troubleshoot": "当前有大量后台任务排队，等待一段时间后重试或检查 Worker 是否正常运行。",
    },
    TASK_RETRY_EXHAUSTED: {
        "message": "任务重试次数已用尽",
        "category": "task",
        "retryable": False,
        "troubleshoot": "任务已多次重试仍然失败，已移入 dead_letter 队列。查看错误日志定位根因。",
    },
    TASK_EXECUTION_FAILED: {
        "message": "后台任务执行失败",
        "category": "task",
        "retryable": True,
        "troubleshoot": "查看任务日志获取具体异常信息。",
    },
    CALLBACK_DECRYPT_FAILED: {
        "message": "回调消息解密失败",
        "category": "callback",
        "retryable": False,
        "troubleshoot": "检查回调 Token 和 AES Key 配置是否与企微后台一致。",
    },
    CALLBACK_EVENT_NOT_FOUND: {
        "message": "回调事件日志未找到",
        "category": "callback",
        "retryable": False,
        "troubleshoot": "事件可能已被清理或 ID 不正确。",
    },
    CALLBACK_PROCESSING_FAILED: {
        "message": "回调事件处理失败",
        "category": "callback",
        "retryable": True,
        "troubleshoot": "查看 callback 日志获取具体异常信息，补偿扫描器会自动重试。",
    },
    CUSTOMER_NOT_FOUND: {
        "message": "客户记录不存在",
        "category": "business",
        "retryable": False,
        "troubleshoot": "客户可能尚未同步或已被删除，尝试重新同步通讯录。",
    },
    QUESTIONNAIRE_NOT_FOUND: {
        "message": "问卷不存在",
        "category": "business",
        "retryable": False,
        "troubleshoot": "检查问卷 ID 是否正确。",
    },
    AUTOMATION_RULE_INVALID: {
        "message": "自动化规则配置无效",
        "category": "business",
        "retryable": False,
        "troubleshoot": "检查规则配置参数是否完整和正确。",
    },
}


def get_error_info(code: str) -> dict[str, Any] | None:
    return ERROR_REGISTRY.get(code)


def classify_wecom_errcode(errcode: int) -> str:
    if errcode in {42001, 40014, 40001}:
        return WECOM_TOKEN_EXPIRED
    if errcode in {60011, 60020, 48002, 48004, 84061, 84074}:
        return WECOM_PERMISSION_DENIED
    if errcode in {45009, 45033}:
        return WECOM_RATE_LIMITED
    if errcode in {84069}:
        return WECOM_CONTACT_NOT_FOUND
    return WECOM_API_ERROR
