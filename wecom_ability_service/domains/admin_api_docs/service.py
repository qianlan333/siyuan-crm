from __future__ import annotations

# ---------------------------------------------------------------------------
# Helper: auto-generate curl example from endpoint metadata
# ---------------------------------------------------------------------------

def _curl(method: str, path: str, auth: str, body: str | None = None) -> str:
    base = "https://<YOUR_DOMAIN>"
    parts = [f"curl -X {method} '{base}{path}'"]
    if auth == "session":
        parts.append("  -H 'Cookie: session=<SESSION_COOKIE>'")
    if method in ("POST", "PUT", "DELETE") and body:
        parts.append("  -H 'Content-Type: application/json'")
        parts.append(f"  -d '{body}'")
    return " \\\n".join(parts)


# ---------------------------------------------------------------------------
# Endpoint group builders — one per business domain
# ---------------------------------------------------------------------------

def _auth_group() -> dict:
    return {
        "id": "auth",
        "title": "认证",
        "description": "企业微信 SSO 扫码登录、OAuth 登录（企业微信内打开）及 break-glass 兜底入口。",
        "endpoints": [
            {
                "id": "get-login",
                "method": "GET",
                "path": "/login",
                "summary": "后台统一登录入口",
                "description": "PC 浏览器跳转企业微信扫码，企业微信内打开则走 OAuth。登录成功后重定向到后台首页。",
                "auth": "public",
                "params": [
                    {"name": "redirect", "type": "string", "required": False, "description": "登录成功后的跳转路径，默认为后台首页"},
                ],
                "request_example": "GET /login?redirect=/admin/customers",
                "response_example": "HTTP 302 → /admin/automation-conversion",
                "curl_example": _curl("GET", "/login?redirect=/admin/customers", "public"),
            },
            {
                "id": "post-login",
                "method": "POST",
                "path": "/login",
                "summary": "Break-glass 密码登录",
                "description": "当企业微信 SSO 不可用时，使用预配置的管理员账号密码登录（需后台开启 ADMIN_BREAK_GLASS_LOGIN_ENABLED）。",
                "auth": "public",
                "params": [
                    {"name": "username", "type": "string", "required": True, "description": "管理员用户名"},
                    {"name": "password", "type": "string", "required": True, "description": "管理员密码"},
                ],
                "request_example": 'POST /login\nContent-Type: application/x-www-form-urlencoded\n\nusername=admin&password=SECRET',
                "response_example": "HTTP 302 → /admin/automation-conversion\n# 或 HTTP 403 当凭据无效",
                "curl_example": _curl("POST", "/login", "public", '{"username":"admin","password":"SECRET"}'),
            },
            {
                "id": "get-wecom-start",
                "method": "GET",
                "path": "/auth/wecom/start",
                "summary": "企业微信扫码登录发起",
                "description": "生成企业微信扫码授权 URL 并重定向。state 参数用于 CSRF 防护。",
                "auth": "public",
                "params": [],
                "request_example": None,
                "response_example": "HTTP 302 → https://open.work.weixin.qq.com/wwopen/sso/qrConnect?...",
                "curl_example": _curl("GET", "/auth/wecom/start", "public"),
            },
            {
                "id": "get-wecom-callback",
                "method": "GET",
                "path": "/auth/wecom/callback",
                "summary": "企业微信扫码回调",
                "description": "企业微信回调，校验 code + state，拉取 UserId 后写入 session。若该 UserId 未在 admin_users 中授权，返回 403。",
                "auth": "public",
                "params": [
                    {"name": "code", "type": "string", "required": True, "description": "企业微信下发的临时授权码"},
                    {"name": "state", "type": "string", "required": True, "description": "CSRF 防护用的随机态值"},
                ],
                "request_example": "GET /auth/wecom/callback?code=abc123&state=xyz789",
                "response_example": "HTTP 302 → /admin/automation-conversion\n# 或 HTTP 403 当该企微成员未被授权",
                "curl_example": _curl("GET", "/auth/wecom/callback?code=abc123&state=xyz789", "public"),
            },
            {
                "id": "get-logout",
                "method": "GET",
                "path": "/logout",
                "summary": "退出后台登录",
                "description": "清除当前登录 session，重定向到登录页。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": "HTTP 302 → /login",
                "curl_example": _curl("GET", "/logout", "session"),
            },
        ],
    }


def _dashboard_group() -> dict:
    return {
        "id": "dashboard",
        "title": "后台仪表盘",
        "description": "后台首页数据概览，包括系统状态、业务摘要及待办事项。",
        "endpoints": [
            {
                "id": "get-dashboard-shell-context",
                "method": "GET",
                "path": "/api/admin/dashboard/shell-context",
                "summary": "获取后台 Shell 上下文",
                "description": "返回当前登录用户的后台 Shell 全局上下文，包括导航菜单、角色信息等。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "shell_status": {...}, "dashboard_cards": [...]}',
                "curl_example": _curl("GET", "/api/admin/dashboard/shell-context", "session"),
            },
            {
                "id": "get-dashboard-system-status",
                "method": "GET",
                "path": "/api/admin/dashboard/system-status",
                "summary": "获取系统状态",
                "description": "返回系统运行状态，包括数据库连接、企业微信 API 凭据、消息队列等健康指标。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "system_status": {"db": "ok", "wecom_api": "ok", "queue": "ok"}}',
                "curl_example": _curl("GET", "/api/admin/dashboard/system-status", "session"),
            },
            {
                "id": "get-dashboard-summary",
                "method": "GET",
                "path": "/api/admin/dashboard/summary",
                "summary": "获取业务摘要",
                "description": "返回后台首页的业务数据摘要，包括客户总数、近期转化等关键指标。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "summary": {"total_contacts": 1200, "recent_conversions": 15}}',
                "curl_example": _curl("GET", "/api/admin/dashboard/summary", "session"),
            },
            {
                "id": "get-dashboard-todos",
                "method": "GET",
                "path": "/api/admin/dashboard/todos",
                "summary": "获取待办事项",
                "description": "返回当前管理员的待办事项列表（待审核话术、待处理任务等）。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "todos": [{"type": "review_output", "count": 3}]}',
                "curl_example": _curl("GET", "/api/admin/dashboard/todos", "session"),
            },
        ],
    }


def _customers_group() -> dict:
    return {
        "id": "customers",
        "title": "客户管理",
        "description": "客户列表查询、详情画像、标签、脉搏、问卷答案、消息记录及联系人同步。external_userid 为企业微信外部联系人唯一标识。",
        "endpoints": [
            {
                "id": "get-customers-list",
                "method": "GET",
                "path": "/api/customers",
                "summary": "获取客户列表",
                "description": "分页返回客户列表，支持多维度筛选。",
                "auth": "session",
                "params": [
                    {"name": "owner_userid", "type": "string", "required": False, "description": "按负责人企微 UserID 过滤"},
                    {"name": "tag", "type": "string", "required": False, "description": "按标签过滤"},
                    {"name": "status", "type": "string", "required": False, "description": "客户状态过滤"},
                    {"name": "marketing_segment", "type": "string", "required": False, "description": "营销分层过滤"},
                    {"name": "mobile", "type": "string", "required": False, "description": "按手机号搜索"},
                    {"name": "keyword", "type": "string", "required": False, "description": "关键词搜索（姓名/备注）"},
                    {"name": "limit", "type": "int", "required": False, "description": "每页条数，默认 50"},
                    {"name": "offset", "type": "int", "required": False, "description": "偏移量"},
                ],
                "request_example": "GET /api/customers?owner_userid=zhangsan&limit=20",
                "response_example": '{"ok": true, "customers": [{"external_userid": "wmXXX", "name": "张三"}], "total": 120}',
                "curl_example": _curl("GET", "/api/customers?limit=20", "session"),
            },
            {
                "id": "get-customer-detail",
                "method": "GET",
                "path": "/api/customers/<external_userid>",
                "summary": "获取客户详情",
                "description": "返回单个客户的完整信息。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string (path)", "required": True, "description": "企业微信外部联系人 ID"},
                ],
                "request_example": "GET /api/customers/wmXXXXXXXX",
                "response_example": '{"ok": true, "customer": {"external_userid": "wmXXX", "name": "张三", "mobile": "138****0000"}}',
                "curl_example": _curl("GET", "/api/customers/wmXXXXXXXX", "session"),
            },
            {
                "id": "get-customer-timeline",
                "method": "GET",
                "path": "/api/customers/<external_userid>/timeline",
                "summary": "获取客户时间线",
                "description": "返回客户的事件时间线（添加、标签变更、问卷提交、消息等）。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string (path)", "required": True, "description": "外部联系人 ID"},
                    {"name": "event_type", "type": "string", "required": False, "description": "按事件类型过滤"},
                    {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 50"},
                    {"name": "offset", "type": "int", "required": False, "description": "偏移量，默认 0"},
                ],
                "request_example": "GET /api/customers/wmXXX/timeline?limit=20",
                "response_example": '{"ok": true, "timeline": [{"event_type": "tag_added", "created_at": "2026-04-27 09:00:00"}]}',
                "curl_example": _curl("GET", "/api/customers/wmXXX/timeline?limit=20", "session"),
            },
            {
                "id": "get-customer-profile",
                "method": "GET",
                "path": "/api/admin/customers/profile",
                "summary": "获取客户画像",
                "description": "返回客户的综合画像信息，包含联系人基础资料和 CRM 记录。支持通过 external_userid、mobile 或 user_id 查找。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": False, "description": "企业微信外部联系人 ID"},
                    {"name": "mobile", "type": "string", "required": False, "description": "手机号"},
                    {"name": "user_id", "type": "string", "required": False, "description": "内部用户 ID"},
                ],
                "request_example": "GET /api/admin/customers/profile?external_userid=wmXXX",
                "response_example": '{"ok": true, "customer": {"name": "张三", "mobile": "138****0000"}, "contact": {"external_userid": "wmXXX"}}',
                "curl_example": _curl("GET", "/api/admin/customers/profile?external_userid=wmXXX", "session"),
            },
            {
                "id": "get-customer-profile-tags",
                "method": "GET",
                "path": "/api/admin/customers/profile/tags",
                "summary": "获取客户标签",
                "description": "返回指定客户当前的所有标签。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                ],
                "request_example": "GET /api/admin/customers/profile/tags?external_userid=wmXXX",
                "response_example": '{"ok": true, "tags": [{"tag_id": "tag_abc", "name": "意向高"}]}',
                "curl_example": _curl("GET", "/api/admin/customers/profile/tags?external_userid=wmXXX", "session"),
            },
            {
                "id": "get-customer-profile-pulse",
                "method": "GET",
                "path": "/api/admin/customers/profile/pulse",
                "summary": "获取客户脉搏数据",
                "description": "返回客户的脉搏评分和分层信息。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"},
                    {"name": "mobile", "type": "string", "required": False, "description": "手机号"},
                ],
                "request_example": "GET /api/admin/customers/profile/pulse?external_userid=wmXXX",
                "response_example": '{"ok": true, "pulse": {"score": 85, "stage": "active"}}',
                "curl_example": _curl("GET", "/api/admin/customers/profile/pulse?external_userid=wmXXX", "session"),
            },
            {
                "id": "get-customer-profile-questionnaire-answers",
                "method": "GET",
                "path": "/api/admin/customers/profile/questionnaire-answers",
                "summary": "获取客户问卷答案",
                "description": "返回客户提交的所有问卷答案记录。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"},
                    {"name": "mobile", "type": "string", "required": False, "description": "手机号"},
                ],
                "request_example": "GET /api/admin/customers/profile/questionnaire-answers?external_userid=wmXXX",
                "response_example": '{"ok": true, "answers": [{"questionnaire_id": 1, "submitted_at": "2026-04-20"}]}',
                "curl_example": _curl("GET", "/api/admin/customers/profile/questionnaire-answers?external_userid=wmXXX", "session"),
            },
            {
                "id": "get-customer-profile-messages",
                "method": "GET",
                "path": "/api/admin/customers/profile/messages",
                "summary": "获取客户消息记录",
                "description": "返回与客户的聊天消息记录。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"},
                    {"name": "mobile", "type": "string", "required": False, "description": "手机号"},
                    {"name": "limit", "type": "int", "required": False, "description": "返回条数"},
                    {"name": "fetch_all", "type": "string", "required": False, "description": "是否拉取全部 (true/false)"},
                ],
                "request_example": "GET /api/admin/customers/profile/messages?external_userid=wmXXX&limit=20",
                "response_example": '{"ok": true, "messages": [{"content": "你好", "direction": "incoming", "sent_at": "2026-04-27"}]}',
                "curl_example": _curl("GET", "/api/admin/customers/profile/messages?external_userid=wmXXX&limit=20", "session"),
            },
            {
                "id": "get-contacts-list",
                "method": "GET",
                "path": "/api/contacts",
                "summary": "获取联系人列表",
                "description": "返回所有外部联系人，支持按负责人过滤。",
                "auth": "session",
                "params": [
                    {"name": "owner_staff_id", "type": "string", "required": False, "description": "按负责人工号过滤"},
                    {"name": "limit", "type": "int", "required": False, "description": "每页条数，默认 50"},
                    {"name": "cursor", "type": "string", "required": False, "description": "分页游标"},
                ],
                "request_example": "GET /api/contacts?limit=50",
                "response_example": '{"ok": true, "contacts": [...], "next_cursor": null, "total": 120}',
                "curl_example": _curl("GET", "/api/contacts?limit=50", "session"),
            },
            {
                "id": "get-contact-detail",
                "method": "GET",
                "path": "/api/contacts/<external_userid>",
                "summary": "获取联系人详情",
                "description": "返回单个外部联系人的完整信息，包含企业微信基础资料和本地备注。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string (path)", "required": True, "description": "外部联系人 ID"},
                ],
                "request_example": "GET /api/contacts/wmXXXXXXXX",
                "response_example": '{"ok": true, "contact": {"external_userid": "wmXXX", "name": "张三", "description": ""}}',
                "curl_example": _curl("GET", "/api/contacts/wmXXXXXXXX", "session"),
            },
            {
                "id": "post-contact-description",
                "method": "POST",
                "path": "/api/contacts/description",
                "summary": "更新联系人备注",
                "description": "更新指定联系人的本地备注字段。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    {"name": "description", "type": "string", "required": True, "description": "新备注内容"},
                ],
                "request_example": 'POST /api/contacts/description\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "description": "高意向，跟进中"}',
                "response_example": '{"ok": true}',
                "curl_example": _curl("POST", "/api/contacts/description", "session", '{"external_userid":"wmXXX","description":"高意向，跟进中"}'),
            },
            {
                "id": "post-contacts-full-sync",
                "method": "POST",
                "path": "/api/contacts/full-sync",
                "summary": "全量同步联系人",
                "description": "从企业微信拉取全量外部联系人数据并同步到本地数据库。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "synced_count": 500}',
                "curl_example": _curl("POST", "/api/contacts/full-sync", "session"),
            },
            {
                "id": "post-contacts-sync-new",
                "method": "POST",
                "path": "/api/contacts/sync-new",
                "summary": "增量同步新联系人",
                "description": "仅同步企业微信侧新增的外部联系人。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "synced_count": 5}',
                "curl_example": _curl("POST", "/api/contacts/sync-new", "session"),
            },
            {
                "id": "get-identity-resolve",
                "method": "GET",
                "path": "/api/identity/resolve",
                "summary": "身份解析",
                "description": "通过 external_userid、mobile 或 unionid 查找并关联客户身份。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"},
                    {"name": "mobile", "type": "string", "required": False, "description": "手机号"},
                    {"name": "unionid", "type": "string", "required": False, "description": "微信 UnionID"},
                ],
                "request_example": "GET /api/identity/resolve?mobile=13800000000",
                "response_example": '{"ok": true, "is_bound": true, "person_id": 42, "external_userid": "wmXXX", "mobile": "13800000000"}',
                "curl_example": _curl("GET", "/api/identity/resolve?mobile=13800000000", "session"),
            },
        ],
    }


def _tags_group() -> dict:
    return {
        "id": "tags",
        "title": "标签管理",
        "description": "企业微信标签的查询、创建及标记/取消标记操作。",
        "endpoints": [
            {
                "id": "get-tags",
                "method": "GET",
                "path": "/api/tags",
                "summary": "获取标签列表",
                "description": "返回当前企业所有可用的外部联系人标签。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "tags": [{"tag_id": "tag_abc", "name": "意向高"}]}',
                "curl_example": _curl("GET", "/api/tags", "session"),
            },
            {
                "id": "post-tags-create",
                "method": "POST",
                "path": "/api/tags",
                "summary": "创建标签",
                "description": "在企业微信侧创建新的外部联系人标签并同步到本地。",
                "auth": "session",
                "params": [
                    {"name": "name", "type": "string", "required": True, "description": "标签名称"},
                ],
                "request_example": 'POST /api/tags\nContent-Type: application/json\n\n{"name": "意向高"}',
                "response_example": '{"ok": true, "tag": {"tag_id": "tag_new", "name": "意向高"}}',
                "curl_example": _curl("POST", "/api/tags", "session", '{"name":"意向高"}'),
            },
            {
                "id": "post-tags-mark",
                "method": "POST",
                "path": "/api/tags/mark",
                "summary": "给联系人打标签",
                "description": "为指定外部联系人打上一个或多个标签。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    {"name": "tag_ids", "type": "array", "required": True, "description": "要打上的标签 ID 列表"},
                ],
                "request_example": 'POST /api/tags/mark\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "tag_ids": ["tag_abc", "tag_def"]}',
                "response_example": '{"ok": true}',
                "curl_example": _curl("POST", "/api/tags/mark", "session", '{"external_userid":"wmXXX","tag_ids":["tag_abc"]}'),
            },
            {
                "id": "post-tags-unmark",
                "method": "POST",
                "path": "/api/tags/unmark",
                "summary": "移除联系人标签",
                "description": "移除指定外部联系人身上的一个或多个标签。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    {"name": "tag_ids", "type": "array", "required": True, "description": "要移除的标签 ID 列表"},
                ],
                "request_example": 'POST /api/tags/unmark\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "tag_ids": ["tag_abc"]}',
                "response_example": '{"ok": true}',
                "curl_example": _curl("POST", "/api/tags/unmark", "session", '{"external_userid":"wmXXX","tag_ids":["tag_abc"]}'),
            },
            {
                "id": "get-wecom-tags",
                "method": "GET",
                "path": "/api/admin/wecom/tags",
                "summary": "获取企微原始标签",
                "description": "直接从企业微信 API 拉取原始标签组和标签列表（含标签组结构）。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "tag_groups": [{"group_name": "客户分层", "tags": [...]}]}',
                "curl_example": _curl("GET", "/api/admin/wecom/tags", "session"),
            },
        ],
    }


def _messages_tasks_group() -> dict:
    return {
        "id": "messages-tasks",
        "title": "消息与任务",
        "description": "创建企业微信消息任务（私聊、朋友圈、群发）及聊天记录归档查询。任务创建后由企业微信提醒对应员工确认发送。",
        "endpoints": [
            {
                "id": "post-task-private-message",
                "method": "POST",
                "path": "/api/tasks/private-message",
                "summary": "创建私聊消息任务",
                "description": "创建一条发给指定外部联系人的私聊消息任务。员工需在企业微信客户端确认后发送。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "目标外部联系人 ID"},
                    {"name": "content", "type": "string", "required": True, "description": "消息文本内容"},
                    {"name": "staff_id", "type": "string", "required": False, "description": "指定发送员工，默认为该联系人负责人"},
                ],
                "request_example": 'POST /api/tasks/private-message\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "content": "您好，关于您咨询的问题..."}',
                "response_example": '{"ok": true, "task_id": "task_abc123"}',
                "curl_example": _curl("POST", "/api/tasks/private-message", "session", '{"external_userid":"wmXXX","content":"您好"}'),
            },
            {
                "id": "post-task-moment",
                "method": "POST",
                "path": "/api/tasks/moment",
                "summary": "创建朋友圈任务",
                "description": "创建一条朋友圈发布任务。员工需在企业微信确认后发布到朋友圈。",
                "auth": "session",
                "params": [
                    {"name": "content", "type": "string", "required": True, "description": "朋友圈文字内容"},
                    {"name": "staff_ids", "type": "array", "required": False, "description": "指定发布的员工列表，默认全部"},
                ],
                "request_example": 'POST /api/tasks/moment\nContent-Type: application/json\n\n{"content": "今日好课推荐..."}',
                "response_example": '{"ok": true, "task_id": "task_moment_abc"}',
                "curl_example": _curl("POST", "/api/tasks/moment", "session", '{"content":"今日好课推荐..."}'),
            },
            {
                "id": "post-task-group-message",
                "method": "POST",
                "path": "/api/tasks/group-message",
                "summary": "创建群发任务",
                "description": "向一批外部联系人创建批量群发消息任务。",
                "auth": "session",
                "params": [
                    {"name": "external_userids", "type": "array", "required": True, "description": "目标外部联系人 ID 列表"},
                    {"name": "content", "type": "string", "required": True, "description": "消息内容"},
                ],
                "request_example": 'POST /api/tasks/group-message\nContent-Type: application/json\n\n{"external_userids": ["wmAAA", "wmBBB"], "content": "您好..."}',
                "response_example": '{"ok": true, "task_id": "task_group_abc", "accepted_count": 2}',
                "curl_example": _curl("POST", "/api/tasks/group-message", "session", '{"external_userids":["wmAAA","wmBBB"],"content":"您好"}'),
            },
            {
                "id": "get-archive-health",
                "method": "GET",
                "path": "/api/archive/health",
                "summary": "归档服务健康检查",
                "description": "检查消息归档适配器（会话存档）的连接状态。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "adapter": {"type": "wecom", "status": "connected"}}',
                "curl_example": _curl("GET", "/api/archive/health", "session"),
            },
            {
                "id": "post-archive-sync",
                "method": "POST",
                "path": "/api/archive/sync",
                "summary": "同步归档消息",
                "description": "从会话存档拉取指定时间范围和负责人的消息并入库。",
                "auth": "session",
                "params": [
                    {"name": "start_time", "type": "string", "required": True, "description": "起始时间，格式 YYYY-MM-DD HH:MM:SS"},
                    {"name": "end_time", "type": "string", "required": True, "description": "结束时间"},
                    {"name": "owner_userid", "type": "string", "required": True, "description": "负责人企微 UserID"},
                    {"name": "cursor", "type": "string", "required": False, "description": "分页游标"},
                ],
                "request_example": 'POST /api/archive/sync\nContent-Type: application/json\n\n{"start_time": "2026-04-01 00:00:00", "end_time": "2026-04-30 23:59:59", "owner_userid": "zhangsan"}',
                "response_example": '{"ok": true, "sync_result": {"synced": 150, "cursor": null}}',
                "curl_example": _curl("POST", "/api/archive/sync", "session", '{"start_time":"2026-04-01 00:00:00","end_time":"2026-04-30 23:59:59","owner_userid":"zhangsan"}'),
            },
            {
                "id": "get-messages",
                "method": "GET",
                "path": "/api/messages/<external_userid>",
                "summary": "获取消息记录",
                "description": "返回与指定客户的全部聊天消息。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string (path)", "required": True, "description": "外部联系人 ID"},
                    {"name": "chat_type", "type": "string", "required": False, "description": "聊天类型过滤"},
                ],
                "request_example": "GET /api/messages/wmXXX",
                "response_example": '{"ok": true, "messages": [{"content": "你好", "direction": "incoming", "sent_at": "2026-04-27"}]}',
                "curl_example": _curl("GET", "/api/messages/wmXXX", "session"),
            },
            {
                "id": "get-messages-recent",
                "method": "GET",
                "path": "/api/messages/<external_userid>/recent",
                "summary": "获取近期消息",
                "description": "返回与指定客户的最近 N 条消息。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string (path)", "required": True, "description": "外部联系人 ID"},
                    {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 20"},
                    {"name": "chat_type", "type": "string", "required": False, "description": "聊天类型过滤"},
                ],
                "request_example": "GET /api/messages/wmXXX/recent?limit=10",
                "response_example": '{"ok": true, "messages": [...]}',
                "curl_example": _curl("GET", "/api/messages/wmXXX/recent?limit=10", "session"),
            },
            {
                "id": "get-messages-search",
                "method": "GET",
                "path": "/api/messages/search",
                "summary": "搜索消息",
                "description": "按关键词搜索与指定客户的聊天记录。",
                "auth": "session",
                "params": [
                    {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    {"name": "keyword", "type": "string", "required": True, "description": "搜索关键词"},
                ],
                "request_example": "GET /api/messages/search?external_userid=wmXXX&keyword=报名",
                "response_example": '{"ok": true, "messages": [...]}',
                "curl_example": _curl("GET", "/api/messages/search?external_userid=wmXXX&keyword=报名", "session"),
            },
        ],
    }


def _questionnaire_group() -> dict:
    return {
        "id": "questionnaire",
        "title": "问卷",
        "description": "问卷的前台提交（公开）和后台管理（需登录态）接口。",
        "endpoints": [
            {
                "id": "get-h5-questionnaire",
                "method": "GET",
                "path": "/api/h5/questionnaires/<slug>",
                "summary": "获取问卷定义（前台）",
                "description": "前台问卷页面加载时调用，返回题目列表、问卷配置及展示文案。",
                "auth": "public",
                "params": [
                    {"name": "slug", "type": "string (path)", "required": True, "description": "问卷唯一标识，如 intent-survey"},
                ],
                "request_example": "GET /api/h5/questionnaires/intent-survey",
                "response_example": '{"ok": true, "questionnaire": {"id": 1, "slug": "intent-survey", "title": "意向调查", "questions": [...]}}',
                "curl_example": _curl("GET", "/api/h5/questionnaires/intent-survey", "public"),
            },
            {
                "id": "post-h5-questionnaire-submit",
                "method": "POST",
                "path": "/api/h5/questionnaires/<slug>/submit",
                "summary": "提交问卷答案（前台）",
                "description": "前台用户提交问卷。提交成功后返回 submission_id 及可选跳转 URL。",
                "auth": "public",
                "params": [
                    {"name": "slug", "type": "string (path)", "required": True, "description": "问卷唯一标识"},
                    {"name": "answers", "type": "array", "required": True, "description": "答案列表，每项包含 question_id 和 value"},
                    {"name": "mobile", "type": "string", "required": True, "description": "用户手机号"},
                    {"name": "external_userid", "type": "string", "required": False, "description": "企业微信外部联系人 ID"},
                ],
                "request_example": 'POST /api/h5/questionnaires/intent-survey/submit\nContent-Type: application/json\n\n{"answers": [{"question_id": 1, "value": "价格"}], "mobile": "13800000000"}',
                "response_example": '{"ok": true, "submission_id": 123, "redirect_url": ""}',
                "curl_example": _curl("POST", "/api/h5/questionnaires/intent-survey/submit", "public", '{"answers":[{"question_id":1,"value":"价格"}],"mobile":"13800000000"}'),
            },
            {
                "id": "post-h5-questionnaire-diagnostics",
                "method": "POST",
                "path": "/api/h5/questionnaires/<slug>/client-diagnostics",
                "summary": "上报前台诊断信息",
                "description": "前台页面上报客户端环境信息，用于排查兼容性问题。",
                "auth": "public",
                "params": [
                    {"name": "slug", "type": "string (path)", "required": True, "description": "问卷标识"},
                ],
                "request_example": None,
                "response_example": '{"ok": true}',
                "curl_example": _curl("POST", "/api/h5/questionnaires/intent-survey/client-diagnostics", "public"),
            },
            {
                "id": "get-h5-wechat-oauth-start",
                "method": "GET",
                "path": "/api/h5/wechat/oauth/start",
                "summary": "微信 OAuth 授权发起",
                "description": "H5 页面在微信内打开时发起 OAuth 授权，获取用户身份。",
                "auth": "public",
                "params": [],
                "request_example": None,
                "response_example": "HTTP 302 → 微信授权页",
                "curl_example": _curl("GET", "/api/h5/wechat/oauth/start", "public"),
            },
            {
                "id": "get-h5-wechat-oauth-callback",
                "method": "GET",
                "path": "/api/h5/wechat/oauth/callback",
                "summary": "微信 OAuth 回调",
                "description": "微信授权回调，获取用户 openid 并写入 session。",
                "auth": "public",
                "params": [],
                "request_example": None,
                "response_example": "HTTP 302 → 原始问卷页",
                "curl_example": _curl("GET", "/api/h5/wechat/oauth/callback", "public"),
            },
            {
                "id": "get-admin-questionnaires",
                "method": "GET",
                "path": "/api/admin/questionnaires",
                "summary": "获取问卷列表（后台）",
                "description": "返回所有问卷及其状态、提交数等。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "questionnaires": [{"id": 1, "slug": "intent-survey", "title": "意向调查", "enabled": true, "submission_count": 42}]}',
                "curl_example": _curl("GET", "/api/admin/questionnaires", "session"),
            },
            {
                "id": "post-admin-questionnaire-create",
                "method": "POST",
                "path": "/api/admin/questionnaires",
                "summary": "创建问卷",
                "description": "创建一份新问卷，包含题目定义和配置。",
                "auth": "session",
                "params": [
                    {"name": "title", "type": "string", "required": True, "description": "问卷标题"},
                    {"name": "slug", "type": "string", "required": True, "description": "问卷唯一标识（URL 友好）"},
                    {"name": "questions", "type": "array", "required": True, "description": "题目列表"},
                ],
                "request_example": 'POST /api/admin/questionnaires\nContent-Type: application/json\n\n{"title": "满意度调查", "slug": "satisfaction", "questions": [...]}',
                "response_example": '{"ok": true, "questionnaire": {"id": 2, "slug": "satisfaction"}}',
                "curl_example": _curl("POST", "/api/admin/questionnaires", "session", '{"title":"满意度调查","slug":"satisfaction","questions":[]}'),
            },
            {
                "id": "get-admin-questionnaire-detail",
                "method": "GET",
                "path": "/api/admin/questionnaires/<int:questionnaire_id>",
                "summary": "获取问卷详情",
                "description": "返回单个问卷的完整定义和配置。",
                "auth": "session",
                "params": [
                    {"name": "questionnaire_id", "type": "int (path)", "required": True, "description": "问卷 ID"},
                ],
                "request_example": "GET /api/admin/questionnaires/1",
                "response_example": '{"ok": true, "questionnaire": {"id": 1, "title": "意向调查", "questions": [...]}}',
                "curl_example": _curl("GET", "/api/admin/questionnaires/1", "session"),
            },
            {
                "id": "put-admin-questionnaire-update",
                "method": "PUT",
                "path": "/api/admin/questionnaires/<int:questionnaire_id>",
                "summary": "更新问卷",
                "description": "更新问卷的标题、题目或配置。",
                "auth": "session",
                "params": [
                    {"name": "questionnaire_id", "type": "int (path)", "required": True, "description": "问卷 ID"},
                    {"name": "title", "type": "string", "required": False, "description": "问卷标题"},
                    {"name": "questions", "type": "array", "required": False, "description": "题目列表"},
                ],
                "request_example": 'PUT /api/admin/questionnaires/1\nContent-Type: application/json\n\n{"title": "新标题"}',
                "response_example": '{"ok": true, "questionnaire": {"id": 1}}',
                "curl_example": _curl("PUT", "/api/admin/questionnaires/1", "session", '{"title":"新标题"}'),
            },
            {
                "id": "post-admin-questionnaire-disable",
                "method": "POST",
                "path": "/api/admin/questionnaires/<int:questionnaire_id>/disable",
                "summary": "禁用问卷",
                "description": "禁用指定问卷，前台将无法访问。",
                "auth": "session",
                "params": [
                    {"name": "questionnaire_id", "type": "int (path)", "required": True, "description": "问卷 ID"},
                ],
                "request_example": "POST /api/admin/questionnaires/1/disable",
                "response_example": '{"ok": true}',
                "curl_example": _curl("POST", "/api/admin/questionnaires/1/disable", "session"),
            },
            {
                "id": "delete-admin-questionnaire",
                "method": "DELETE",
                "path": "/api/admin/questionnaires/<int:questionnaire_id>",
                "summary": "删除问卷",
                "description": "永久删除指定问卷及其所有提交记录。",
                "auth": "session",
                "params": [
                    {"name": "questionnaire_id", "type": "int (path)", "required": True, "description": "问卷 ID"},
                ],
                "request_example": "DELETE /api/admin/questionnaires/1",
                "response_example": '{"ok": true}',
                "curl_example": _curl("DELETE", "/api/admin/questionnaires/1", "session"),
            },
            {
                "id": "get-admin-questionnaire-export",
                "method": "GET",
                "path": "/api/admin/questionnaires/<int:questionnaire_id>/export",
                "summary": "导出问卷答案",
                "description": "以 Excel 文件格式导出指定问卷的所有提交答案。",
                "auth": "session",
                "params": [
                    {"name": "questionnaire_id", "type": "int (path)", "required": True, "description": "问卷 ID"},
                ],
                "request_example": "GET /api/admin/questionnaires/1/export",
                "response_example": "Excel 文件下载 (application/vnd.ms-excel)",
                "curl_example": _curl("GET", "/api/admin/questionnaires/1/export", "session"),
            },
            {
                "id": "get-admin-questionnaire-preflight",
                "method": "GET",
                "path": "/api/admin/questionnaires/preflight",
                "summary": "问卷预检",
                "description": "检查创建/编辑问卷所需的前置条件（标签、渠道配置等）。",
                "auth": "session",
                "params": [],
                "request_example": None,
                "response_example": '{"ok": true, "preflight": {"tags_ready": true, "channel_configured": true}}',
                "curl_example": _curl("GET", "/api/admin/questionnaires/preflight", "session"),
            },
        ],
    }


def _automation_group() -> dict:
    return {
        "id": "automation",
        "title": "自动化运营",
        "description": "自动化转化核心接口：运营概览、成员管理、阶段群发、SOP 模板、Agent 编排、任务流、画像分层及自动接话。",
        "subsections": [
            {
                "id": "automation-overview",
                "title": "概览与设置",
                "endpoints": [
                    {"id": "get-auto-dashboard", "method": "GET", "path": "/api/admin/automation-conversion/dashboard", "summary": "获取运营概览", "description": "返回人群规模、启用任务流数量、池子用户明细及任务流执行摘要。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "dashboard": {"audience_overview": {...}, "active_workflow_count": 3}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/dashboard", "session")},
                    {"id": "get-auto-settings", "method": "GET", "path": "/api/admin/automation-conversion/settings", "summary": "获取运营设置", "description": "返回自动化运营的全局设置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "settings": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/settings", "session")},
                    {"id": "post-auto-settings", "method": "POST", "path": "/api/admin/automation-conversion/settings", "summary": "保存运营设置", "description": "更新自动化运营的全局设置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/settings", "session")},
                    {"id": "get-auto-default-channel", "method": "GET", "path": "/api/admin/automation-conversion/default-channel-settings", "summary": "获取默认渠道设置", "description": "返回默认活码渠道的配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "settings": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/default-channel-settings", "session")},
                    {"id": "put-auto-default-channel", "method": "PUT", "path": "/api/admin/automation-conversion/default-channel-settings", "summary": "保存默认渠道设置", "description": "更新默认活码渠道的配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/default-channel-settings", "session")},
                    {"id": "post-auto-default-channel-qr", "method": "POST", "path": "/api/admin/automation-conversion/default-channel-settings/generate-qr", "summary": "生成默认渠道二维码", "description": "重新生成默认活码渠道的二维码。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "qr_url": "https://..."}', "curl_example": _curl("POST", "/api/admin/automation-conversion/default-channel-settings/generate-qr", "session")},
                    {"id": "get-auto-model-settings", "method": "GET", "path": "/api/admin/automation-conversion/model-settings", "summary": "获取模型设置", "description": "返回 AI 模型相关配置（LLM provider、模型名称等）。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "model_settings": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/model-settings", "session")},
                    {"id": "put-auto-model-settings", "method": "PUT", "path": "/api/admin/automation-conversion/model-settings", "summary": "保存模型设置", "description": "更新 AI 模型配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/model-settings", "session")},
                    {"id": "post-auto-model-test", "method": "POST", "path": "/api/admin/automation-conversion/model-settings/test", "summary": "测试模型连接", "description": "使用当前配置测试 AI 模型连接是否正常。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "test_result": "success"}', "curl_example": _curl("POST", "/api/admin/automation-conversion/model-settings/test", "session")},
                ],
            },
            {
                "id": "automation-member",
                "title": "方案成员操作",
                "endpoints": [
                    {"id": "get-auto-member", "method": "GET", "path": "/api/admin/automation-conversion/member", "summary": "获取成员信息", "description": "查询指定联系人在自动化运营池中的状态。", "auth": "session", "params": [{"name": "external_contact_id", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": "GET /api/admin/automation-conversion/member?external_contact_id=wmXXX", "response_example": '{"ok": true, "member": {"pool_key": "new_user", "focus": false}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/member?external_contact_id=wmXXX", "session")},
                    {"id": "post-auto-put-in-pool", "method": "POST", "path": "/api/admin/automation-conversion/member/put-in-pool", "summary": "加入运营池", "description": "将联系人加入指定运营池。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "pool_key", "type": "string", "required": True, "description": "运营池标识"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/put-in-pool", "session", '{"external_userid":"wmXXX","pool_key":"new_user"}')},
                    {"id": "post-auto-remove-from-pool", "method": "POST", "path": "/api/admin/automation-conversion/member/remove-from-pool", "summary": "移出运营池", "description": "将联系人从指定运营池移除。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "pool_key", "type": "string", "required": True, "description": "运营池标识"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/remove-from-pool", "session", '{"external_userid":"wmXXX","pool_key":"new_user"}')},
                    {"id": "post-auto-set-focus", "method": "POST", "path": "/api/admin/automation-conversion/member/set-focus", "summary": "标记为重点关注", "description": "将联系人标记为重点关注状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/set-focus", "session", '{"external_userid":"wmXXX"}')},
                    {"id": "post-auto-set-normal", "method": "POST", "path": "/api/admin/automation-conversion/member/set-normal", "summary": "取消重点关注", "description": "将联系人从重点关注恢复为普通状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/set-normal", "session", '{"external_userid":"wmXXX"}')},
                    {"id": "post-auto-mark-won", "method": "POST", "path": "/api/admin/automation-conversion/member/mark-won", "summary": "标记已转化", "description": "将联系人标记为已转化（won）。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/mark-won", "session", '{"external_userid":"wmXXX"}')},
                    {"id": "post-auto-unmark-won", "method": "POST", "path": "/api/admin/automation-conversion/member/unmark-won", "summary": "取消已转化标记", "description": "撤销联系人的已转化标记。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/unmark-won", "session", '{"external_userid":"wmXXX"}')},
                    {"id": "post-auto-push-openclaw", "method": "POST", "path": "/api/admin/automation-conversion/member/push-openclaw", "summary": "推送到 OpenClaw", "description": "将联系人信息推送到 OpenClaw 外部系统。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/member/push-openclaw", "session", '{"external_userid":"wmXXX"}')},
                ],
            },
            {
                "id": "automation-stage-send",
                "title": "阶段群发",
                "endpoints": [
                    {"id": "post-auto-stage-send-preview", "method": "POST", "path": "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview", "summary": "阶段群发预览", "description": "预览指定阶段的手动群发内容。", "auth": "session", "params": [{"name": "stage_key", "type": "string (path)", "required": True, "description": "阶段标识"}], "request_example": None, "response_example": '{"ok": true, "preview": {"recipient_count": 10, "content": "..."}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/stage/new-user/manual-send/preview", "session")},
                    {"id": "post-auto-stage-send", "method": "POST", "path": "/api/admin/automation-conversion/stage/<stage_key>/manual-send", "summary": "执行阶段群发", "description": "执行指定阶段的手动群发。", "auth": "session", "params": [{"name": "stage_key", "type": "string (path)", "required": True, "description": "阶段标识"}, {"name": "content", "type": "string", "required": True, "description": "群发内容"}], "request_example": None, "response_example": '{"ok": true, "sent_count": 10}', "curl_example": _curl("POST", "/api/admin/automation-conversion/stage/new-user/manual-send", "session", '{"content":"您好..."}')},
                    {"id": "post-auto-focus-send-batch", "method": "POST", "path": "/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches", "summary": "创建重点关注批量发送", "description": "为重点关注用户创建批量发送任务。", "auth": "session", "params": [{"name": "stage_key", "type": "string (path)", "required": True, "description": "阶段标识"}], "request_example": None, "response_example": '{"ok": true, "batch_id": "batch_123"}', "curl_example": _curl("POST", "/api/admin/automation-conversion/stage/new-user/focus-send-batches", "session")},
                    {"id": "get-auto-focus-send-batch-detail", "method": "GET", "path": "/api/admin/automation-conversion/focus-send-batches/<batch_id>", "summary": "获取批量发送详情", "description": "查询批量发送任务的执行状态和结果。", "auth": "session", "params": [{"name": "batch_id", "type": "string (path)", "required": True, "description": "批次 ID"}], "request_example": None, "response_example": '{"ok": true, "batch": {"status": "completed", "sent_count": 15}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/focus-send-batches/batch_123", "session")},
                    {"id": "post-auto-focus-send-run-due", "method": "POST", "path": "/api/admin/automation-conversion/focus-send-batches/run-due", "summary": "执行到期批量发送", "description": "处理当前到期的批量发送任务。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "result": {"processed": 3}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/focus-send-batches/run-due", "session")},
                ],
            },
            {
                "id": "automation-sop",
                "title": "SOP 配置",
                "endpoints": [
                    {"id": "get-auto-sop-config", "method": "GET", "path": "/api/admin/automation-conversion/sop/config", "summary": "获取 SOP 配置列表", "description": "返回各运营池的 SOP 自动跟进配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "configs": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/sop/config", "session")},
                    {"id": "put-auto-sop-config", "method": "PUT", "path": "/api/admin/automation-conversion/sop/config/<pool_key>", "summary": "更新 SOP 配置", "description": "更新指定运营池的 SOP 配置（启用/停用、模板模式等）。", "auth": "session", "params": [{"name": "pool_key", "type": "string (path)", "required": True, "description": "运营池标识"}, {"name": "enabled", "type": "boolean", "required": False, "description": "是否启用"}, {"name": "template_mode", "type": "string", "required": False, "description": "模板模式"}], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/sop/config/new_user", "session", '{"enabled":true}')},
                    {"id": "get-auto-sop-templates", "method": "GET", "path": "/api/admin/automation-conversion/sop/templates/<pool_key>", "summary": "获取 SOP 模板", "description": "返回指定运营池的 SOP 日程模板列表。", "auth": "session", "params": [{"name": "pool_key", "type": "string (path)", "required": True, "description": "运营池标识"}], "request_example": None, "response_example": '{"ok": true, "templates": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/sop/templates/new_user", "session")},
                    {"id": "put-auto-sop-template", "method": "PUT", "path": "/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", "summary": "更新 SOP 模板", "description": "更新指定日次的 SOP 模板内容。", "auth": "session", "params": [{"name": "pool_key", "type": "string (path)", "required": True, "description": "运营池标识"}, {"name": "day_index", "type": "int (path)", "required": True, "description": "第 N 天（从 0 开始）"}, {"name": "content", "type": "string", "required": False, "description": "模板内容"}], "request_example": None, "response_example": '{"ok": true, "template": {...}}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/sop/templates/new_user/0", "session", '{"content":"第一天跟进话术"}')},
                    {"id": "delete-auto-sop-template", "method": "DELETE", "path": "/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", "summary": "删除 SOP 模板", "description": "删除指定日次的 SOP 模板。", "auth": "session", "params": [{"name": "pool_key", "type": "string (path)", "required": True, "description": "运营池标识"}, {"name": "day_index", "type": "int (path)", "required": True, "description": "日次"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("DELETE", "/api/admin/automation-conversion/sop/templates/new_user/2", "session")},
                    {"id": "post-auto-sop-run-due", "method": "POST", "path": "/api/admin/automation-conversion/sop/run-due", "summary": "执行到期 SOP 任务", "description": "处理当前时刻到期的 SOP 自动跟进任务。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "result": {"processed": 5}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/sop/run-due", "session")},
                ],
            },
            {
                "id": "automation-agent",
                "title": "Agent 编排",
                "endpoints": [
                    {"id": "get-auto-agent-options", "method": "GET", "path": "/api/admin/automation-conversion/agents/options", "summary": "获取 Agent 选项", "description": "返回可用的 Agent 列表及配置选项。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "options": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agents/options", "session")},
                    {"id": "post-auto-agent-create", "method": "POST", "path": "/api/admin/automation-conversion/agents", "summary": "创建 Agent", "description": "创建一个新的自动化 Agent。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "agent": {"agent_code": "intent_v2"}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/agents", "session")},
                    {"id": "get-auto-agent-detail", "method": "GET", "path": "/api/admin/automation-conversion/agents/<agent_code>", "summary": "获取 Agent 详情", "description": "返回指定 Agent 的完整配置和状态。", "auth": "session", "params": [{"name": "agent_code", "type": "string (path)", "required": True, "description": "Agent 代码"}], "request_example": None, "response_example": '{"ok": true, "agent": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agents/intent_v2", "session")},
                    {"id": "delete-auto-agent", "method": "DELETE", "path": "/api/admin/automation-conversion/agents/<agent_code>", "summary": "删除 Agent", "description": "删除指定 Agent。", "auth": "session", "params": [{"name": "agent_code", "type": "string (path)", "required": True, "description": "Agent 代码"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("DELETE", "/api/admin/automation-conversion/agents/intent_v2", "session")},
                    {"id": "post-auto-agent-draft", "method": "POST", "path": "/api/admin/automation-conversion/agents/<agent_code>/draft", "summary": "保存 Agent 草稿", "description": "保存 Agent 的配置草稿（不立即生效）。", "auth": "session", "params": [{"name": "agent_code", "type": "string (path)", "required": True, "description": "Agent 代码"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/agents/intent_v2/draft", "session")},
                    {"id": "post-auto-agent-publish", "method": "POST", "path": "/api/admin/automation-conversion/agents/<agent_code>/publish", "summary": "发布 Agent", "description": "将 Agent 草稿发布为正式版本。", "auth": "session", "params": [{"name": "agent_code", "type": "string (path)", "required": True, "description": "Agent 代码"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/agents/intent_v2/publish", "session")},
                    {"id": "get-auto-agent-outputs", "method": "GET", "path": "/api/admin/automation-conversion/agent-outputs", "summary": "获取 Agent 输出列表", "description": "返回 Agent 生成的话术输出列表，可用于人工评审。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": "GET /api/admin/automation-conversion/agent-outputs?limit=20", "response_example": '{"ok": true, "outputs": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-outputs?limit=20", "session")},
                    {"id": "get-auto-agent-output-detail", "method": "GET", "path": "/api/admin/automation-conversion/agent-outputs/<output_id>", "summary": "获取输出详情", "description": "返回单条 Agent 输出的完整信息。", "auth": "session", "params": [{"name": "output_id", "type": "string (path)", "required": True, "description": "输出 ID"}], "request_example": None, "response_example": '{"ok": true, "output": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-outputs/out_abc", "session")},
                    {"id": "get-auto-agent-run-detail", "method": "GET", "path": "/api/admin/automation-conversion/agent-runs/<run_id>", "summary": "获取 Agent 运行详情", "description": "返回单次 Agent 运行的完整日志和结果。", "auth": "session", "params": [{"name": "run_id", "type": "string (path)", "required": True, "description": "运行 ID"}], "request_example": None, "response_example": '{"ok": true, "run": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-runs/run_abc", "session")},
                    {"id": "post-auto-agent-outputs-export", "method": "POST", "path": "/api/admin/automation-conversion/agent-outputs/export", "summary": "导出 Agent 输出", "description": "创建 Agent 输出的导出任务。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "job_id": "job_abc"}', "curl_example": _curl("POST", "/api/admin/automation-conversion/agent-outputs/export", "session")},
                    {"id": "get-auto-agent-outputs-export-detail", "method": "GET", "path": "/api/admin/automation-conversion/agent-outputs/export/<job_id>", "summary": "获取导出任务状态", "description": "查询 Agent 输出导出任务的进度和下载链接。", "auth": "session", "params": [{"name": "job_id", "type": "string (path)", "required": True, "description": "导出任务 ID"}], "request_example": None, "response_example": '{"ok": true, "status": "completed", "download_url": "..."}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-outputs/export/job_abc", "session")},
                    {"id": "get-auto-agent-replay", "method": "GET", "path": "/api/admin/automation-conversion/agent-replay", "summary": "获取 Agent 重放列表", "description": "返回可重放的 Agent 运行记录。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "replays": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-replay", "session")},
                    {"id": "get-auto-pending-publish", "method": "GET", "path": "/api/admin/automation-conversion/agent-orchestration/pending-publish", "summary": "获取待发布列表", "description": "返回所有有待发布草稿的 Agent 列表。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "pending": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/agent-orchestration/pending-publish", "session")},
                ],
            },
            {
                "id": "automation-review",
                "title": "输出评审与发送",
                "endpoints": [
                    {"id": "get-auto-review-outputs", "method": "GET", "path": "/api/admin/automation-conversion/review-outputs", "summary": "获取待评审输出", "description": "返回待人工评审的 Agent 话术输出列表。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "outputs": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/review-outputs", "session")},
                    {"id": "post-auto-review-output", "method": "POST", "path": "/api/admin/automation-conversion/review-outputs/<output_id>/review", "summary": "评审输出", "description": "对 Agent 输出进行采用/拒绝评审。", "auth": "session", "params": [{"name": "output_id", "type": "string (path)", "required": True, "description": "输出 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/review-outputs/out_abc/review", "session")},
                    {"id": "post-auto-send-via-webhook", "method": "POST", "path": "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook", "summary": "通过 Webhook 发送", "description": "将评审通过的输出通过 Webhook 发送。", "auth": "session", "params": [{"name": "output_id", "type": "string (path)", "required": True, "description": "输出 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/review-outputs/out_abc/send-via-webhook", "session")},
                    {"id": "post-auto-send-via-wecom", "method": "POST", "path": "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom", "summary": "通过企微发送", "description": "将评审通过的输出通过企业微信消息发送给客户。", "auth": "session", "params": [{"name": "output_id", "type": "string (path)", "required": True, "description": "输出 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/review-outputs/out_abc/send-via-wecom", "session")},
                    {"id": "post-auto-send-via-bazhuayu", "method": "POST", "path": "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-bazhuayu", "summary": "通过八爪鱼发送", "description": "将评审通过的输出通过八爪鱼渠道发送。", "auth": "session", "params": [{"name": "output_id", "type": "string (path)", "required": True, "description": "输出 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/review-outputs/out_abc/send-via-bazhuayu", "session")},
                ],
            },
            {
                "id": "automation-workflow",
                "title": "任务流",
                "endpoints": [
                    {"id": "get-auto-workflow-registry", "method": "GET", "path": "/api/admin/automation-conversion/workflows/registry", "summary": "获取任务流节点注册表", "description": "返回任务流中可用的节点类型及其配置模板。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "registry": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/workflows/registry", "session")},
                    {"id": "get-auto-workflows", "method": "GET", "path": "/api/admin/automation-conversion/workflows", "summary": "获取任务流列表", "description": "返回所有任务流及其状态。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数"}, {"name": "offset", "type": "int", "required": False, "description": "偏移量"}], "request_example": None, "response_example": '{"ok": true, "workflows": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/workflows", "session")},
                    {"id": "get-auto-workflow-detail", "method": "GET", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>", "summary": "获取任务流详情", "description": "返回单个任务流的完整定义。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true, "workflow": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/workflows/1", "session")},
                    {"id": "get-auto-workflow-summary", "method": "GET", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>/summary", "summary": "获取任务流摘要", "description": "返回任务流的执行统计摘要。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true, "summary": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/workflows/1/summary", "session")},
                    {"id": "post-auto-workflow-create", "method": "POST", "path": "/api/admin/automation-conversion/workflows", "summary": "创建任务流", "description": "创建一个新的自动化任务流。", "auth": "session", "params": [{"name": "name", "type": "string", "required": True, "description": "任务流名称"}, {"name": "description", "type": "string", "required": False, "description": "描述"}], "request_example": None, "response_example": '{"ok": true, "workflow": {"id": 1}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/workflows", "session", '{"name":"新用户跟进流"}')},
                    {"id": "put-auto-workflow-update", "method": "PUT", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>", "summary": "更新任务流", "description": "更新任务流的名称、描述或状态。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true, "workflow": {...}}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/workflows/1", "session", '{"name":"更新后的名称"}')},
                    {"id": "delete-auto-workflow", "method": "DELETE", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>", "summary": "删除任务流", "description": "删除指定任务流。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("DELETE", "/api/admin/automation-conversion/workflows/1", "session")},
                    {"id": "post-auto-workflow-activate", "method": "POST", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>/activate", "summary": "激活任务流", "description": "激活指定任务流，开始自动执行。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/workflows/1/activate", "session")},
                    {"id": "post-auto-workflow-pause", "method": "POST", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>/pause", "summary": "暂停任务流", "description": "暂停指定任务流。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/workflows/1/pause", "session")},
                    {"id": "get-auto-workflow-nodes", "method": "GET", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", "summary": "获取任务流节点", "description": "返回任务流中的所有节点定义。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}], "request_example": None, "response_example": '{"ok": true, "nodes": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/workflows/1/nodes", "session")},
                    {"id": "post-auto-workflow-node-create", "method": "POST", "path": "/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", "summary": "创建任务流节点", "description": "在任务流中添加一个新节点。", "auth": "session", "params": [{"name": "workflow_id", "type": "int (path)", "required": True, "description": "任务流 ID"}, {"name": "node_type", "type": "string", "required": True, "description": "节点类型"}, {"name": "config", "type": "object", "required": True, "description": "节点配置"}], "request_example": None, "response_example": '{"ok": true, "node": {...}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/workflows/1/nodes", "session", '{"node_type":"send_message","config":{}}')},
                    {"id": "put-auto-workflow-node-update", "method": "PUT", "path": "/api/admin/automation-conversion/workflow-nodes/<int:node_id>", "summary": "更新任务流节点", "description": "更新指定节点的配置。", "auth": "session", "params": [{"name": "node_id", "type": "int (path)", "required": True, "description": "节点 ID"}, {"name": "config", "type": "object", "required": True, "description": "节点配置"}], "request_example": None, "response_example": '{"ok": true, "node": {...}}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/workflow-nodes/1", "session", '{"config":{}}')},
                    {"id": "delete-auto-workflow-node", "method": "DELETE", "path": "/api/admin/automation-conversion/workflow-nodes/<int:node_id>", "summary": "删除任务流节点", "description": "删除指定节点。", "auth": "session", "params": [{"name": "node_id", "type": "int (path)", "required": True, "description": "节点 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("DELETE", "/api/admin/automation-conversion/workflow-nodes/1", "session")},
                ],
            },
            {
                "id": "automation-execution",
                "title": "执行记录",
                "endpoints": [
                    {"id": "get-auto-executions", "method": "GET", "path": "/api/admin/automation-conversion/executions", "summary": "获取执行批次列表", "description": "返回任务流执行批次列表。", "auth": "session", "params": [{"name": "workflow_id", "type": "int", "required": False, "description": "按任务流过滤"}, {"name": "status", "type": "string", "required": False, "description": "按状态过滤"}, {"name": "limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": None, "response_example": '{"ok": true, "executions": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/executions?limit=20", "session")},
                    {"id": "get-auto-execution-detail", "method": "GET", "path": "/api/admin/automation-conversion/executions/<int:execution_id>", "summary": "获取执行批次详情", "description": "返回单个执行批次的详细信息。", "auth": "session", "params": [{"name": "execution_id", "type": "int (path)", "required": True, "description": "执行批次 ID"}], "request_example": None, "response_example": '{"ok": true, "execution": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/executions/1", "session")},
                    {"id": "get-auto-execution-items", "method": "GET", "path": "/api/admin/automation-conversion/executions/<int:execution_id>/items", "summary": "获取执行明细", "description": "返回执行批次中的各条执行明细。", "auth": "session", "params": [{"name": "execution_id", "type": "int (path)", "required": True, "description": "执行批次 ID"}], "request_example": None, "response_example": '{"ok": true, "items": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/executions/1/items", "session")},
                    {"id": "get-auto-execution-item-detail", "method": "GET", "path": "/api/admin/automation-conversion/execution-items/<int:execution_item_id>", "summary": "获取执行明细详情", "description": "返回单条执行明细的完整信息。", "auth": "session", "params": [{"name": "execution_item_id", "type": "int (path)", "required": True, "description": "执行明细 ID"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/execution-items/1", "session")},
                ],
            },
            {
                "id": "automation-profile-segment",
                "title": "画像分层模板",
                "endpoints": [
                    {"id": "get-auto-profile-catalog", "method": "GET", "path": "/api/admin/automation-conversion/profile-segment-templates/catalog", "summary": "获取分层模板目录", "description": "返回可用的画像分层维度目录。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "catalog": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog", "session")},
                    {"id": "get-auto-profile-templates", "method": "GET", "path": "/api/admin/automation-conversion/profile-segment-templates", "summary": "获取分层模板列表", "description": "返回所有已创建的画像分层模板。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "templates": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/profile-segment-templates", "session")},
                    {"id": "get-auto-profile-options", "method": "GET", "path": "/api/admin/automation-conversion/profile-segment-templates/options", "summary": "获取分层模板选项", "description": "返回可用于下拉选择的分层模板列表。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "options": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/profile-segment-templates/options", "session")},
                    {"id": "get-auto-profile-template-detail", "method": "GET", "path": "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", "summary": "获取分层模板详情", "description": "返回单个分层模板的完整配置。", "auth": "session", "params": [{"name": "template_id", "type": "int (path)", "required": True, "description": "模板 ID"}], "request_example": None, "response_example": '{"ok": true, "template": {...}}', "curl_example": _curl("GET", "/api/admin/automation-conversion/profile-segment-templates/1", "session")},
                    {"id": "post-auto-profile-template-create", "method": "POST", "path": "/api/admin/automation-conversion/profile-segment-templates", "summary": "创建分层模板", "description": "创建一个新的画像分层模板。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "template": {"id": 1}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/profile-segment-templates", "session")},
                    {"id": "put-auto-profile-template-update", "method": "PUT", "path": "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", "summary": "更新分层模板", "description": "更新指定分层模板的配置。", "auth": "session", "params": [{"name": "template_id", "type": "int (path)", "required": True, "description": "模板 ID"}], "request_example": None, "response_example": '{"ok": true, "template": {...}}', "curl_example": _curl("PUT", "/api/admin/automation-conversion/profile-segment-templates/1", "session")},
                ],
            },
            {
                "id": "automation-reply-monitor",
                "title": "自动接话",
                "endpoints": [
                    {"id": "post-auto-reply-capture", "method": "POST", "path": "/api/admin/automation-conversion/reply-monitor/capture", "summary": "扫描新消息", "description": "手动触发一次自动接话扫描，将最新未处理消息抓取入队。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "status": "captured", "message": "扫描完成，新增 3 条入队"}', "curl_example": _curl("POST", "/api/admin/automation-conversion/reply-monitor/capture", "session")},
                    {"id": "post-auto-reply-run-due", "method": "POST", "path": "/api/admin/automation-conversion/reply-monitor/run-due", "summary": "放行到期队列", "description": "手动触发放行逻辑，处理当前到期的自动接话队列。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "status": "idle", "message": "本次无到期项"}', "curl_example": _curl("POST", "/api/admin/automation-conversion/reply-monitor/run-due", "session")},
                ],
            },
            {
                "id": "automation-router",
                "title": "路由与回调",
                "endpoints": [
                    {"id": "get-auto-router-pending", "method": "GET", "path": "/api/admin/automation-conversion/router-pending-callbacks", "summary": "获取待处理路由回调", "description": "返回等待处理的路由回调队列。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "callbacks": [...]}', "curl_example": _curl("GET", "/api/admin/automation-conversion/router-pending-callbacks", "session")},
                    {"id": "post-auto-router-replay", "method": "POST", "path": "/api/admin/automation-conversion/router-callback-replay/<run_id>", "summary": "重放路由回调", "description": "重新执行指定的路由回调。", "auth": "session", "params": [{"name": "run_id", "type": "string (path)", "required": True, "description": "运行 ID"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/router-callback-replay/run_abc", "session")},
                    {"id": "post-auto-router-check", "method": "POST", "path": "/api/admin/automation-conversion/router-pending-callback-check", "summary": "检查待处理回调", "description": "检查并处理所有待处理的路由回调。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/router-pending-callback-check", "session")},
                ],
            },
            {
                "id": "automation-jobs",
                "title": "运营任务",
                "endpoints": [
                    {"id": "post-auto-jobs-run-due", "method": "POST", "path": "/api/admin/automation-conversion/jobs/run-due", "summary": "执行到期运营任务", "description": "处理自动化运营中当前到期的所有定时任务。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/admin/automation-conversion/jobs/run-due", "session")},
                    {"id": "post-auto-message-activity-sync", "method": "POST", "path": "/api/admin/automation-conversion/message-activity-sync/run", "summary": "同步消息活跃度", "description": "触发消息活跃度数据的同步更新。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/automation-conversion/message-activity-sync/run", "session")},
                ],
            },
        ],
        "endpoints": [],
    }


def _config_group() -> dict:
    return {
        "id": "config",
        "title": "系统配置",
        "description": "系统设置、路由规则、标签配置及营销自动化配置。所有写操作需要管理员角色。",
        "endpoints": [
            {"id": "get-config-overview", "method": "GET", "path": "/api/admin/config/overview", "summary": "获取配置概览", "description": "返回系统核心配置项的摘要。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "overview": {"webhook_url": "...", "wecom_sso_enabled": true}}', "curl_example": _curl("GET", "/api/admin/config/overview", "session")},
            {"id": "get-config-routing", "method": "GET", "path": "/api/admin/config/routing", "summary": "获取路由规则", "description": "返回客户路由规则和负责人角色映射。", "auth": "session", "params": [{"name": "q", "type": "string", "required": False, "description": "搜索关键词"}, {"name": "active_only", "type": "boolean", "required": False, "description": "仅显示启用的"}], "request_example": None, "response_example": '{"ok": true, "config": {"owner_roles": [...], "rules": [...]}}', "curl_example": _curl("GET", "/api/admin/config/routing", "session")},
            {"id": "post-config-routing-owner-role", "method": "POST", "path": "/api/admin/config/routing/owner-role", "summary": "保存负责人角色", "description": "新增或更新负责人角色配置。", "auth": "session", "params": [{"name": "userid", "type": "string", "required": True, "description": "企微 UserID"}, {"name": "display_name", "type": "string", "required": False, "description": "显示名"}, {"name": "role", "type": "string", "required": False, "description": "角色"}, {"name": "active", "type": "boolean", "required": False, "description": "是否启用"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("POST", "/api/admin/config/routing/owner-role", "session", '{"userid":"zhangsan","role":"sales","active":true}')},
            {"id": "post-config-routing-rule", "method": "POST", "path": "/api/admin/config/routing/rule", "summary": "保存路由规则", "description": "新增或更新客户路由规则。", "auth": "session", "params": [{"name": "rule_key", "type": "string", "required": True, "description": "规则标识"}, {"name": "routing_alias", "type": "string", "required": False, "description": "路由别名"}, {"name": "route_owner_userid", "type": "string", "required": False, "description": "目标负责人"}, {"name": "active", "type": "boolean", "required": False, "description": "是否启用"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("POST", "/api/admin/config/routing/rule", "session", '{"rule_key":"default","route_owner_userid":"zhangsan"}')},
            {"id": "get-config-signup-tags", "method": "GET", "path": "/api/admin/config/signup-tags", "summary": "获取报名标签配置", "description": "返回报名转化标签配置列表。", "auth": "session", "params": [{"name": "q", "type": "string", "required": False, "description": "搜索"}, {"name": "active_only", "type": "boolean", "required": False, "description": "仅启用的"}], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("GET", "/api/admin/config/signup-tags", "session")},
            {"id": "post-config-signup-tags", "method": "POST", "path": "/api/admin/config/signup-tags", "summary": "保存报名标签", "description": "新增或更新报名转化标签配置。", "auth": "session", "params": [{"name": "tag_id", "type": "string", "required": True, "description": "标签 ID"}, {"name": "business_status", "type": "string", "required": True, "description": "业务状态"}, {"name": "active", "type": "boolean", "required": False, "description": "是否启用"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("POST", "/api/admin/config/signup-tags", "session", '{"tag_id":"tag_abc","business_status":"enrolled"}')},
            {"id": "get-config-class-term-tags", "method": "GET", "path": "/api/admin/config/class-term-tags", "summary": "获取班期标签配置", "description": "返回班期标签配置列表。", "auth": "session", "params": [{"name": "q", "type": "string", "required": False, "description": "搜索"}, {"name": "active_only", "type": "boolean", "required": False, "description": "仅启用的"}], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("GET", "/api/admin/config/class-term-tags", "session")},
            {"id": "post-config-class-term-tags", "method": "POST", "path": "/api/admin/config/class-term-tags", "summary": "保存班期标签", "description": "新增或更新班期标签配置。", "auth": "session", "params": [{"name": "tag_group_name", "type": "string", "required": True, "description": "标签组名"}, {"name": "term_no", "type": "int", "required": True, "description": "班期号"}, {"name": "active", "type": "boolean", "required": False, "description": "是否启用"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("POST", "/api/admin/config/class-term-tags", "session", '{"tag_group_name":"班期","term_no":1}')},
            {"id": "get-config-app-settings", "method": "GET", "path": "/api/admin/config/app-settings", "summary": "获取系统设置", "description": "返回所有可配置的系统键值对。", "auth": "session", "params": [{"name": "q", "type": "string", "required": False, "description": "按键名搜索"}, {"name": "scope", "type": "string", "required": False, "description": "配置范围过滤"}], "request_example": None, "response_example": '{"ok": true, "config": {"settings": [...]}}', "curl_example": _curl("GET", "/api/admin/config/app-settings", "session")},
            {"id": "put-config-app-settings", "method": "PUT", "path": "/api/admin/config/app-settings", "summary": "保存系统设置", "description": "批量更新系统配置项。confirm=true 为必填，防止误操作。", "auth": "session", "params": [{"name": "confirm", "type": "boolean", "required": True, "description": "必须为 true"}, {"name": "settings", "type": "object", "required": True, "description": "要更新的键值对"}], "request_example": 'PUT /api/admin/config/app-settings\nContent-Type: application/json\n\n{"confirm": true, "settings": {"OPENCLAW_WEBHOOK_URL": "https://..."}}', "response_example": '{"ok": true, "changed": ["OPENCLAW_WEBHOOK_URL"]}', "curl_example": _curl("PUT", "/api/admin/config/app-settings", "session", '{"confirm":true,"settings":{"KEY":"VALUE"}}')},
            {"id": "get-config-mcp-tools", "method": "GET", "path": "/api/admin/config/mcp-tools", "summary": "获取 MCP 工具配置", "description": "返回 MCP 工具的启用/禁用配置。", "auth": "session", "params": [{"name": "q", "type": "string", "required": False, "description": "搜索"}, {"name": "enabled_only", "type": "boolean", "required": False, "description": "仅启用的"}], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("GET", "/api/admin/config/mcp-tools", "session")},
            {"id": "post-config-mcp-tools", "method": "POST", "path": "/api/admin/config/mcp-tools", "summary": "保存 MCP 工具配置", "description": "启用或禁用指定 MCP 工具。", "auth": "session", "params": [{"name": "tool_key", "type": "string", "required": True, "description": "工具标识"}, {"name": "enabled", "type": "boolean", "required": True, "description": "是否启用"}], "request_example": None, "response_example": '{"ok": true, "item": {...}}', "curl_example": _curl("POST", "/api/admin/config/mcp-tools", "session", '{"tool_key":"crm_search","enabled":true}')},
            {"id": "get-marketing-auto-config", "method": "GET", "path": "/api/admin/marketing-automation/config", "summary": "获取营销自动化配置", "description": "返回营销自动化全局设置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("GET", "/api/admin/marketing-automation/config", "session")},
            {"id": "put-marketing-auto-config", "method": "PUT", "path": "/api/admin/marketing-automation/config", "summary": "保存营销自动化配置", "description": "更新营销自动化全局设置。", "auth": "session", "params": [{"name": "questionnaire_id", "type": "int", "required": False, "description": "关联问卷 ID"}, {"name": "enabled", "type": "boolean", "required": False, "description": "是否启用"}, {"name": "core_threshold", "type": "int", "required": False, "description": "核心阈值"}], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("PUT", "/api/admin/marketing-automation/config", "session", '{"enabled":true}')},
            {"id": "post-marketing-auto-preview", "method": "POST", "path": "/api/admin/marketing-automation/config/preview", "summary": "预览营销自动化效果", "description": "预览指定客户在当前配置下的自动化触达效果。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"}, {"name": "person_id", "type": "int", "required": False, "description": "内部人员 ID"}], "request_example": None, "response_example": '{"ok": true, "preview": {...}}', "curl_example": _curl("POST", "/api/admin/marketing-automation/config/preview", "session", '{"external_userid":"wmXXX"}')},
            {"id": "get-marketing-auto-dispatch", "method": "GET", "path": "/api/admin/marketing-automation/dispatch-history", "summary": "查询分发历史", "description": "查询营销自动化触达与分发记录。", "auth": "session", "params": [{"name": "status", "type": "string", "required": False, "description": "过滤状态"}, {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 20"}], "request_example": None, "response_example": '{"ok": true, "dispatch_history": {"items": [...]}}', "curl_example": _curl("GET", "/api/admin/marketing-automation/dispatch-history?limit=20", "session")},
            {"id": "post-marketing-auto-recompute", "method": "POST", "path": "/api/admin/marketing-automation/recompute", "summary": "重算营销状态", "description": "重新计算指定客户的营销自动化状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": False, "description": "外部联系人 ID"}, {"name": "external_userids", "type": "array", "required": False, "description": "批量联系人 ID"}], "request_example": None, "response_example": '{"ok": true, "recompute": {...}}', "curl_example": _curl("POST", "/api/admin/marketing-automation/recompute", "session", '{"external_userid":"wmXXX"}')},
            {"id": "get-config-signup-conversion", "method": "GET", "path": "/api/admin/config/marketing-automation/signup-conversion", "summary": "获取报名转化配置", "description": "返回报名转化的自动化配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "config": {...}}', "curl_example": _curl("GET", "/api/admin/config/marketing-automation/signup-conversion", "session")},
            {"id": "put-config-signup-conversion", "method": "PUT", "path": "/api/admin/config/marketing-automation/signup-conversion", "summary": "保存报名转化配置", "description": "更新报名转化的自动化配置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("PUT", "/api/admin/config/marketing-automation/signup-conversion", "session")},
            {"id": "get-settings", "method": "GET", "path": "/api/settings", "summary": "获取全局设置", "description": "返回全局应用设置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "settings": {...}}', "curl_example": _curl("GET", "/api/settings", "session")},
            {"id": "put-settings", "method": "PUT", "path": "/api/settings", "summary": "保存全局设置", "description": "更新全局应用设置。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("PUT", "/api/settings", "session")},
        ],
    }


def _user_ops_group() -> dict:
    return {
        "id": "user-ops",
        "title": "用户运营",
        "description": "用户运营管理：批量查询、导入、群发及发送记录。",
        "endpoints": [
            {"id": "get-user-ops-overview", "method": "GET", "path": "/api/admin/user-ops/overview", "summary": "获取用户运营概览", "description": "返回用户运营数据概览，支持多维度筛选。", "auth": "session", "params": [{"name": "keyword", "type": "string", "required": False, "description": "关键词搜索"}, {"name": "mobile", "type": "string", "required": False, "description": "手机号搜索"}, {"name": "owner_userid", "type": "string", "required": False, "description": "负责人过滤"}, {"name": "class_term_no", "type": "string", "required": False, "description": "班期号过滤"}], "request_example": None, "response_example": '{"ok": true, "count": 120, "buckets": {...}}', "curl_example": _curl("GET", "/api/admin/user-ops/overview", "session")},
            {"id": "get-user-ops-list", "method": "GET", "path": "/api/admin/user-ops/list", "summary": "获取用户运营列表", "description": "返回用户运营记录列表（同概览的筛选参数）。", "auth": "session", "params": [{"name": "keyword", "type": "string", "required": False, "description": "关键词搜索"}, {"name": "limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": None, "response_example": '{"ok": true, "records": [...]}', "curl_example": _curl("GET", "/api/admin/user-ops/list?limit=50", "session")},
            {"id": "get-user-ops-history", "method": "GET", "path": "/api/admin/user-ops/history", "summary": "获取操作历史", "description": "返回用户运营操作历史记录。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 100"}], "request_example": None, "response_example": '{"ok": true, "history": [...]}', "curl_example": _curl("GET", "/api/admin/user-ops/history", "session")},
            {"id": "post-user-ops-import-mobile-class-terms", "method": "POST", "path": "/api/admin/user-ops/import-mobile-class-terms", "summary": "导入手机号班期", "description": "通过文件或粘贴文本批量导入手机号与班期的关联。", "auth": "session", "params": [{"name": "file", "type": "file", "required": False, "description": "Excel/CSV 文件"}, {"name": "pasted_text", "type": "string", "required": False, "description": "粘贴的文本数据"}], "request_example": None, "response_example": '{"ok": true, "imported_count": 25, "results": [...]}', "curl_example": _curl("POST", "/api/admin/user-ops/import-mobile-class-terms", "session")},
            {"id": "post-user-ops-import-activation", "method": "POST", "path": "/api/admin/user-ops/import-activation-status", "summary": "导入激活状态", "description": "批量导入用户的激活状态。", "auth": "session", "params": [{"name": "file", "type": "file", "required": False, "description": "Excel/CSV 文件"}, {"name": "pasted_text", "type": "string", "required": False, "description": "粘贴的文本数据"}], "request_example": None, "response_example": '{"ok": true, "imported_count": 10}', "curl_example": _curl("POST", "/api/admin/user-ops/import-activation-status", "session")},
            {"id": "post-user-ops-run-deferred", "method": "POST", "path": "/api/admin/user-ops/run-deferred-jobs", "summary": "执行延迟任务", "description": "执行待处理的用户运营延迟任务。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "批次大小，默认 20"}], "request_example": None, "response_example": '{"ok": true, "processed_count": 5}', "curl_example": _curl("POST", "/api/admin/user-ops/run-deferred-jobs", "session")},
            {"id": "get-user-ops-export", "method": "GET", "path": "/api/admin/user-ops/export", "summary": "导出用户运营数据", "description": "以 Excel 文件格式导出用户运营数据（同概览的筛选参数）。", "auth": "session", "params": [], "request_example": None, "response_example": "Excel 文件下载 (application/vnd.ms-excel)", "curl_example": _curl("GET", "/api/admin/user-ops/export", "session")},
            {"id": "post-user-ops-dnd", "method": "POST", "path": "/api/admin/user-ops/do-not-disturb", "summary": "设置免打扰", "description": "设置或取消用户的免打扰状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "enabled", "type": "boolean", "required": True, "description": "是否开启免打扰"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/admin/user-ops/do-not-disturb", "session", '{"external_userid":"wmXXX","enabled":true}')},
            {"id": "post-user-ops-batch-send-preview", "method": "POST", "path": "/api/admin/user-ops/batch-send/preview", "summary": "批量发送预览", "description": "预览批量发送的受众范围和内容。", "auth": "session", "params": [{"name": "selection_mode", "type": "string", "required": True, "description": "选择模式"}, {"name": "content", "type": "string", "required": True, "description": "发送内容"}], "request_example": None, "response_example": '{"ok": true, "preview": {...}, "count": 50}', "curl_example": _curl("POST", "/api/admin/user-ops/batch-send/preview", "session", '{"selection_mode":"filter","content":"您好"}')},
            {"id": "post-user-ops-batch-send-execute", "method": "POST", "path": "/api/admin/user-ops/batch-send/execute", "summary": "执行批量发送", "description": "执行批量发送任务。", "auth": "session", "params": [{"name": "selection_mode", "type": "string", "required": True, "description": "选择模式"}, {"name": "content", "type": "string", "required": True, "description": "发送内容"}], "request_example": None, "response_example": '{"ok": true, "sent_count": 50, "batch_id": 1}', "curl_example": _curl("POST", "/api/admin/user-ops/batch-send/execute", "session", '{"selection_mode":"filter","content":"您好"}')},
            {"id": "get-user-ops-send-records", "method": "GET", "path": "/api/admin/user-ops/send-records", "summary": "获取发送记录列表", "description": "返回批量发送的历史记录。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数"}, {"name": "offset", "type": "int", "required": False, "description": "偏移量"}], "request_example": None, "response_example": '{"ok": true, "records": [...], "total": 10}', "curl_example": _curl("GET", "/api/admin/user-ops/send-records", "session")},
            {"id": "get-user-ops-send-record-detail", "method": "GET", "path": "/api/admin/user-ops/send-records/<int:record_id>", "summary": "获取发送记录详情", "description": "返回单条发送记录的详细信息。", "auth": "session", "params": [{"name": "record_id", "type": "int (path)", "required": True, "description": "记录 ID"}], "request_example": None, "response_example": '{"ok": true, "record": {...}}', "curl_example": _curl("GET", "/api/admin/user-ops/send-records/1", "session")},
            {"id": "post-user-ops-send-record-refresh", "method": "POST", "path": "/api/admin/user-ops/send-records/<int:record_id>/refresh", "summary": "刷新发送记录状态", "description": "从企业微信更新发送记录的投递状态。", "auth": "session", "params": [{"name": "record_id", "type": "int (path)", "required": True, "description": "记录 ID"}], "request_example": None, "response_example": '{"ok": true, "record": {...}}', "curl_example": _curl("POST", "/api/admin/user-ops/send-records/1/refresh", "session")},
        ],
    }


def _class_user_group() -> dict:
    return {
        "id": "class-user",
        "title": "班级学员管理",
        "description": "班级学员的查询、初始化、迁移和导出。",
        "endpoints": [
            {"id": "get-class-user-list", "method": "GET", "path": "/api/admin/class-user-management", "summary": "获取学员列表", "description": "返回班级学员列表，支持按报名状态过滤。", "auth": "session", "params": [{"name": "signup_status", "type": "string", "required": False, "description": "报名状态过滤"}], "request_example": None, "response_example": '{"ok": true, "records": [...], "tag_initialization": {...}}', "curl_example": _curl("GET", "/api/admin/class-user-management", "session")},
            {"id": "post-class-user-bootstrap", "method": "POST", "path": "/api/admin/class-user-management/bootstrap", "summary": "初始化学员数据", "description": "首次初始化班级学员管理模块的数据。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "initialized": true, "definitions": [...]}', "curl_example": _curl("POST", "/api/admin/class-user-management/bootstrap", "session")},
            {"id": "post-class-user-migrate", "method": "POST", "path": "/api/admin/class-user-management/migrate", "summary": "迁移学员数据", "description": "执行学员数据迁移。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "migrated_count": 50}', "curl_example": _curl("POST", "/api/admin/class-user-management/migrate", "session")},
            {"id": "get-class-user-export", "method": "GET", "path": "/api/admin/class-user-management/export", "summary": "导出学员数据", "description": "以 Excel 文件格式导出学员数据。", "auth": "session", "params": [{"name": "signup_status", "type": "string", "required": False, "description": "报名状态过滤"}], "request_example": None, "response_example": "Excel 文件下载", "curl_example": _curl("GET", "/api/admin/class-user-management/export", "session")},
            {"id": "get-class-user-history", "method": "GET", "path": "/api/admin/class-user-management/history", "summary": "获取操作历史", "description": "返回班级学员管理的操作历史。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 100"}], "request_example": None, "response_example": '{"ok": true, "history": [...]}', "curl_example": _curl("GET", "/api/admin/class-user-management/history", "session")},
        ],
    }


def _sidebar_group() -> dict:
    return {
        "id": "sidebar",
        "title": "侧边栏",
        "description": "企业微信侧边栏应用接口，在客服会话侧边栏中展示客户状态、绑定手机号、管理营销状态。",
        "endpoints": [
            {"id": "get-sidebar-binding", "method": "GET", "path": "/api/sidebar/contact-binding-status", "summary": "查询绑定状态", "description": "返回当前会话联系人的手机号绑定状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "owner_userid", "type": "string", "required": False, "description": "负责人"}], "request_example": "GET /api/sidebar/contact-binding-status?external_userid=wmXXX", "response_example": '{"ok": true, "is_bound": true, "detail_url": "/admin/customers/wmXXX"}', "curl_example": _curl("GET", "/api/sidebar/contact-binding-status?external_userid=wmXXX", "session")},
            {"id": "get-sidebar-jssdk", "method": "GET", "path": "/api/sidebar/jssdk-config", "summary": "获取 JSSDK 签名", "description": "返回企业微信 JSSDK 的签名配置，用于侧边栏页面调用企微 JS API。", "auth": "session", "params": [{"name": "url", "type": "string", "required": True, "description": "当前页面 URL"}], "request_example": "GET /api/sidebar/jssdk-config?url=https://...", "response_example": '{"ok": true, "signature": "...", "noncestr": "...", "timestamp": "..."}', "curl_example": _curl("GET", "/api/sidebar/jssdk-config?url=https://example.com", "session")},
            {"id": "post-sidebar-bind-mobile", "method": "POST", "path": "/api/sidebar/bind-mobile", "summary": "绑定手机号", "description": "将手机号与外部联系人关联。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "mobile", "type": "string", "required": True, "description": "11 位手机号"}, {"name": "bind_by_userid", "type": "string", "required": True, "description": "操作人企微 UserID"}, {"name": "force_rebind", "type": "boolean", "required": False, "description": "是否强制重新绑定"}], "request_example": None, "response_example": '{"ok": true, "binding": {...}, "detail_url": "/admin/customers/wmXXX"}', "curl_example": _curl("POST", "/api/sidebar/bind-mobile", "session", '{"external_userid":"wmXXX","mobile":"13800000000","bind_by_userid":"zhangsan"}')},
            {"id": "get-sidebar-lead-pool", "method": "GET", "path": "/api/sidebar/lead-pool/status", "summary": "查询线索池状态", "description": "返回联系人在线索池中的状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true, "status": {...}}', "curl_example": _curl("GET", "/api/sidebar/lead-pool/status?external_userid=wmXXX", "session")},
            {"id": "post-sidebar-lead-pool-upsert", "method": "POST", "path": "/api/sidebar/lead-pool/upsert-class-term", "summary": "更新线索池班期", "description": "更新联系人在线索池中的班期信息。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "class_term_no", "type": "int", "required": True, "description": "班期号"}], "request_example": None, "response_example": '{"ok": true, "status": {...}, "upsert": {...}}', "curl_example": _curl("POST", "/api/sidebar/lead-pool/upsert-class-term", "session", '{"external_userid":"wmXXX","class_term_no":1}')},
            {"id": "get-sidebar-signup-tags", "method": "GET", "path": "/api/sidebar/signup-tags/status", "summary": "查询报名标签状态", "description": "返回联系人当前的报名转化标签。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true, "current_signup_status": "enrolled", "marketing_profile": {...}}', "curl_example": _curl("GET", "/api/sidebar/signup-tags/status?external_userid=wmXXX", "session")},
            {"id": "post-sidebar-signup-tags-mark", "method": "POST", "path": "/api/sidebar/signup-tags/mark", "summary": "标记报名标签", "description": "为联系人标记报名转化标签。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "signup_status", "type": "string", "required": True, "description": "报名状态"}], "request_example": None, "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/sidebar/signup-tags/mark", "session", '{"external_userid":"wmXXX","signup_status":"enrolled"}')},
            {"id": "get-sidebar-marketing", "method": "GET", "path": "/api/sidebar/marketing-status", "summary": "查询营销状态", "description": "返回联系人的营销自动化状态和跟进阶段。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": "GET /api/sidebar/marketing-status?external_userid=wmXXX", "response_example": '{"ok": true, "marketing_status": {"stage": "operating", "followup_segment": "intent_high"}}', "curl_example": _curl("GET", "/api/sidebar/marketing-status?external_userid=wmXXX", "session")},
            {"id": "post-sidebar-set-followup", "method": "POST", "path": "/api/sidebar/marketing-status/set-followup-segment", "summary": "设置跟进分层", "description": "手动设置联系人的跟进分层标签。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}, {"name": "followup_segment", "type": "string", "required": True, "description": "分层标识"}], "request_example": None, "response_example": '{"ok": true, "marketing_status": {...}, "override": {...}}', "curl_example": _curl("POST", "/api/sidebar/marketing-status/set-followup-segment", "session", '{"external_userid":"wmXXX","followup_segment":"intent_high"}')},
            {"id": "post-sidebar-mark-enrolled", "method": "POST", "path": "/api/sidebar/marketing-status/mark-enrolled", "summary": "标记已报名", "description": "将联系人标记为已报名状态。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true, "marketing_status": {...}, "conversion": {...}}', "curl_example": _curl("POST", "/api/sidebar/marketing-status/mark-enrolled", "session", '{"external_userid":"wmXXX"}')},
            {"id": "post-sidebar-unmark-enrolled", "method": "POST", "path": "/api/sidebar/marketing-status/unmark-enrolled", "summary": "取消已报名", "description": "撤销联系人的已报名标记。", "auth": "session", "params": [{"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"}], "request_example": None, "response_example": '{"ok": true, "marketing_status": {...}, "conversion": {...}}', "curl_example": _curl("POST", "/api/sidebar/marketing-status/unmark-enrolled", "session", '{"external_userid":"wmXXX"}')},
        ],
    }


def _jobs_group() -> dict:
    return {
        "id": "jobs",
        "title": "后台任务",
        "description": "后台任务监控与管理：归档同步、消息批次、延迟任务、Webhook 投递及审计日志。",
        "endpoints": [
            {"id": "get-jobs-summary", "method": "GET", "path": "/api/admin/jobs/summary", "summary": "获取任务摘要", "description": "返回各类后台任务的状态概览。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "summary": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/summary", "session")},
            {"id": "get-jobs-archive-sync", "method": "GET", "path": "/api/admin/jobs/archive-sync", "summary": "获取归档同步状态", "description": "返回消息归档同步的当前状态。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "archive_sync": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/archive-sync", "session")},
            {"id": "post-jobs-archive-sync-run", "method": "POST", "path": "/api/admin/jobs/archive-sync/run", "summary": "触发归档同步", "description": "手动触发一次消息归档同步。", "auth": "session", "params": [{"name": "start_time", "type": "string", "required": True, "description": "起始时间"}, {"name": "end_time", "type": "string", "required": True, "description": "结束时间"}, {"name": "confirm", "type": "boolean", "required": False, "description": "确认执行"}], "request_example": None, "response_example": '{"ok": true, "sync_result": {...}}', "curl_example": _curl("POST", "/api/admin/jobs/archive-sync/run", "session", '{"start_time":"2026-04-01","end_time":"2026-04-30","confirm":true}')},
            {"id": "get-jobs-callbacks", "method": "GET", "path": "/api/admin/jobs/callbacks", "summary": "获取回调任务", "description": "返回回调任务的队列状态。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "callbacks": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/callbacks", "session")},
            {"id": "get-jobs-message-batches", "method": "GET", "path": "/api/admin/jobs/message-batches", "summary": "获取消息批次列表", "description": "返回消息批次任务列表。", "auth": "session", "params": [{"name": "batch_status", "type": "string", "required": False, "description": "按状态过滤"}, {"name": "batch_limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": None, "response_example": '{"ok": true, "message_batches": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/message-batches", "session")},
            {"id": "get-jobs-message-batch-detail", "method": "GET", "path": "/api/admin/jobs/message-batches/<int:batch_id>", "summary": "获取消息批次详情", "description": "返回单个消息批次的详细信息。", "auth": "session", "params": [{"name": "batch_id", "type": "int (path)", "required": True, "description": "批次 ID"}], "request_example": None, "response_example": '{"ok": true, "message_batch": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/message-batches/1", "session")},
            {"id": "post-jobs-message-batch-ack", "method": "POST", "path": "/api/admin/jobs/message-batches/<int:batch_id>/ack", "summary": "确认消息批次", "description": "确认消息批次已处理。", "auth": "session", "params": [{"name": "batch_id", "type": "int (path)", "required": True, "description": "批次 ID"}, {"name": "ack_note", "type": "string", "required": False, "description": "确认备注"}, {"name": "confirm", "type": "boolean", "required": False, "description": "确认操作"}], "request_example": None, "response_example": '{"ok": true, "batch": {...}}', "curl_example": _curl("POST", "/api/admin/jobs/message-batches/1/ack", "session", '{"confirm":true}')},
            {"id": "get-jobs-deferred", "method": "GET", "path": "/api/admin/jobs/deferred-jobs", "summary": "获取延迟任务列表", "description": "返回待执行的延迟任务队列。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "deferred_jobs": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/deferred-jobs", "session")},
            {"id": "post-jobs-deferred-run", "method": "POST", "path": "/api/admin/jobs/deferred-jobs/run", "summary": "执行延迟任务", "description": "手动执行待处理的延迟任务。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "批次大小"}, {"name": "confirm", "type": "boolean", "required": False, "description": "确认执行"}], "request_example": None, "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/admin/jobs/deferred-jobs/run", "session", '{"confirm":true}')},
            {"id": "get-jobs-webhook-deliveries", "method": "GET", "path": "/api/admin/jobs/webhook-deliveries", "summary": "获取 Webhook 投递列表", "description": "返回 Webhook 投递记录。", "auth": "session", "params": [{"name": "webhook_event_type", "type": "string", "required": False, "description": "事件类型过滤"}, {"name": "webhook_status", "type": "string", "required": False, "description": "投递状态过滤"}, {"name": "webhook_limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": None, "response_example": '{"ok": true, "webhook_deliveries": {...}}', "curl_example": _curl("GET", "/api/admin/jobs/webhook-deliveries", "session")},
            {"id": "post-jobs-webhook-run", "method": "POST", "path": "/api/admin/jobs/webhook-deliveries/run", "summary": "执行 Webhook 投递", "description": "手动触发 Webhook 投递任务。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "批次大小"}, {"name": "confirm", "type": "boolean", "required": False, "description": "确认执行"}], "request_example": None, "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/admin/jobs/webhook-deliveries/run", "session", '{"confirm":true}')},
            {"id": "post-jobs-webhook-retry", "method": "POST", "path": "/api/admin/jobs/webhook-deliveries/<int:delivery_id>/retry", "summary": "重试 Webhook 投递", "description": "重试失败的 Webhook 投递。", "auth": "session", "params": [{"name": "delivery_id", "type": "int (path)", "required": True, "description": "投递 ID"}, {"name": "confirm", "type": "boolean", "required": False, "description": "确认操作"}], "request_example": None, "response_example": '{"ok": true, "delivery": {...}}', "curl_example": _curl("POST", "/api/admin/jobs/webhook-deliveries/1/retry", "session", '{"confirm":true}')},
            {"id": "get-audit-logs", "method": "GET", "path": "/api/admin/audit/logs", "summary": "获取审计日志", "description": "返回后台操作审计日志。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "logs": [...]}', "curl_example": _curl("GET", "/api/admin/audit/logs", "session")},
        ],
    }


def _webhooks_group() -> dict:
    return {
        "id": "webhooks",
        "title": "Webhook / 回调",
        "description": "企业微信事件回调及外部系统 Webhook 接口。回调接口由企业微信服务端主动推送，需配置 Token 和 EncodingAESKey。",
        "endpoints": [
            {"id": "wecom-callback", "method": "POST", "path": "/wecom/external-contact/callback", "summary": "企微联系人事件回调", "description": "接收企业微信推送的外部联系人变更事件（新增、删除、修改等）。GET 请求用于回调 URL 验证。", "auth": "public", "params": [{"name": "msg_signature", "type": "string (query)", "required": True, "description": "消息签名"}, {"name": "timestamp", "type": "string (query)", "required": True, "description": "时间戳"}, {"name": "nonce", "type": "string (query)", "required": True, "description": "随机字符串"}], "request_example": "POST /wecom/external-contact/callback?msg_signature=XXX&timestamp=123&nonce=abc\n\n<xml>...</xml>", "response_example": '{"ok": true}', "curl_example": _curl("POST", "/wecom/external-contact/callback?msg_signature=XXX&timestamp=123&nonce=abc", "public")},
            {"id": "wecom-events", "method": "POST", "path": "/api/wecom/events", "summary": "企微通用事件回调", "description": "接收企业微信推送的通用事件（应用事件、审批等）。", "auth": "public", "params": [{"name": "msg_signature", "type": "string (query)", "required": True, "description": "消息签名"}, {"name": "timestamp", "type": "string (query)", "required": True, "description": "时间戳"}, {"name": "nonce", "type": "string (query)", "required": True, "description": "随机字符串"}], "request_example": None, "response_example": '{"ok": true}', "curl_example": _curl("POST", "/api/wecom/events?msg_signature=XXX&timestamp=123&nonce=abc", "public")},
            {"id": "post-activation-webhook", "method": "POST", "path": "/api/customers/automation/activation-webhook", "summary": "激活状态 Webhook", "description": "外部系统通过此接口上报用户激活状态变更。", "auth": "session", "params": [{"name": "mobile", "type": "string", "required": True, "description": "手机号"}, {"name": "activated_at", "type": "string", "required": False, "description": "激活时间"}, {"name": "source", "type": "string", "required": False, "description": "来源标识"}], "request_example": 'POST /api/customers/automation/activation-webhook\n\n{"mobile": "13800000000", "source": "app"}', "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/customers/automation/activation-webhook", "session", '{"mobile":"13800000000","source":"app"}')},
            {"id": "get-automation-webhook-deliveries", "method": "GET", "path": "/api/customers/automation/webhook-deliveries", "summary": "获取自动化 Webhook 投递", "description": "查询自动化触发的 Webhook 投递记录。", "auth": "session", "params": [{"name": "event_type", "type": "string", "required": False, "description": "事件类型过滤"}, {"name": "status", "type": "string", "required": False, "description": "状态过滤"}, {"name": "limit", "type": "int", "required": False, "description": "返回条数"}], "request_example": None, "response_example": '{"ok": true, "deliveries": [...]}', "curl_example": _curl("GET", "/api/customers/automation/webhook-deliveries", "session")},
            {"id": "post-automation-webhook-retry", "method": "POST", "path": "/api/customers/automation/webhook-deliveries/<int:delivery_id>/retry", "summary": "重试自动化 Webhook", "description": "重试失败的自动化 Webhook 投递。", "auth": "session", "params": [{"name": "delivery_id", "type": "int (path)", "required": True, "description": "投递 ID"}], "request_example": None, "response_example": '{"ok": true, "delivery": {...}}', "curl_example": _curl("POST", "/api/customers/automation/webhook-deliveries/1/retry", "session")},
            {"id": "post-automation-webhook-retry-due", "method": "POST", "path": "/api/customers/automation/webhook-deliveries/retry-due", "summary": "批量重试到期 Webhook", "description": "批量重试所有到期的失败 Webhook 投递。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "批次大小"}], "request_example": None, "response_example": '{"ok": true, "result": {...}}', "curl_example": _curl("POST", "/api/customers/automation/webhook-deliveries/retry-due", "session")},
            {"id": "get-signup-conversion-batches", "method": "GET", "path": "/api/customers/automation/signup-conversion/batches", "summary": "获取报名转化批次", "description": "查询报名转化自动化的批次记录。", "auth": "session", "params": [{"name": "limit", "type": "int", "required": False, "description": "返回条数"}, {"name": "cursor", "type": "string", "required": False, "description": "分页游标"}], "request_example": None, "response_example": '{"ok": true, "automation_batches": {...}}', "curl_example": _curl("GET", "/api/customers/automation/signup-conversion/batches", "session")},
            {"id": "get-signup-conversion-batch-detail", "method": "GET", "path": "/api/customers/automation/signup-conversion/batches/<int:batch_id>", "summary": "获取转化批次详情", "description": "返回单个报名转化批次的详细信息。", "auth": "session", "params": [{"name": "batch_id", "type": "int (path)", "required": True, "description": "批次 ID"}], "request_example": None, "response_example": '{"ok": true, "automation_batch": {...}, "candidates": [...]}', "curl_example": _curl("GET", "/api/customers/automation/signup-conversion/batches/1", "session")},
        ],
    }


def _system_group() -> dict:
    return {
        "id": "system",
        "title": "系统",
        "description": "系统健康检查和补偿操作。",
        "endpoints": [
            {"id": "get-system-health", "method": "GET", "path": "/api/system/health", "summary": "系统健康检查", "description": "返回系统各组件的健康状态。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "status": "healthy", "pending_events": 0, "circuit_breaker_state": "closed"}', "curl_example": _curl("GET", "/api/system/health", "session")},
            {"id": "post-system-compensate", "method": "POST", "path": "/api/system/compensate", "summary": "系统补偿", "description": "扫描并修复卡住的事件队列，将超时事件重新入队或转入死信。", "auth": "session", "params": [], "request_example": None, "response_example": '{"ok": true, "scanned": 10, "requeued": 2, "dead_lettered": 0}', "curl_example": _curl("POST", "/api/system/compensate", "session")},
        ],
    }


def _error_codes_group() -> dict:
    return {
        "id": "errors",
        "title": "错误码",
        "description": '所有 API 在出错时返回统一结构：{"ok": false, "error": "<message>"}。HTTP 状态码含义如下。',
        "endpoints": [
            {"id": "error-400", "method": "GET", "path": "HTTP 400", "summary": "参数校验失败", "description": "请求体缺少必填字段、字段格式错误，或高风险操作未带 confirm=true。", "auth": None, "params": [], "request_example": None, "response_example": '{"ok": false, "error": "mobile is required"}', "curl_example": None},
            {"id": "error-401", "method": "GET", "path": "HTTP 401", "summary": "未认证", "description": "后台页面未登录，或 Bearer Token 缺失/错误。", "auth": None, "params": [], "request_example": None, "response_example": '{"ok": false, "error": "authentication required"}', "curl_example": None},
            {"id": "error-403", "method": "GET", "path": "HTTP 403", "summary": "权限不足", "description": "企微成员未授权，或当前角色无权执行写操作。", "auth": None, "params": [], "request_example": None, "response_example": '{"ok": false, "error": "permission denied"}', "curl_example": None},
            {"id": "error-404", "method": "GET", "path": "HTTP 404", "summary": "资源不存在", "description": "请求的问卷、客户或配置项不存在。", "auth": None, "params": [], "request_example": None, "response_example": '{"ok": false, "error": "not found"}', "curl_example": None},
            {"id": "error-503", "method": "GET", "path": "HTTP 503", "summary": "服务未就绪", "description": "内部依赖（数据库、企业微信 API 凭据）未配置完成。", "auth": None, "params": [], "request_example": None, "response_example": '{"ok": false, "error": "service unavailable: wecom credentials not configured"}', "curl_example": None},
        ],
    }


# ---------------------------------------------------------------------------
# Main data function
# ---------------------------------------------------------------------------

def _api_endpoint_groups() -> list[dict]:
    return [
        _auth_group(),
        _dashboard_group(),
        _customers_group(),
        _tags_group(),
        _messages_tasks_group(),
        _questionnaire_group(),
        _automation_group(),
        _config_group(),
        _user_ops_group(),
        _class_user_group(),
        _sidebar_group(),
        _jobs_group(),
        _webhooks_group(),
        _system_group(),
        _error_codes_group(),
    ]


def _flat_endpoints(group: dict) -> list[dict]:
    eps = list(group.get("endpoints") or [])
    for sub in group.get("subsections") or []:
        eps.extend(sub.get("endpoints") or [])
    return eps


def _build_quick_reference(groups: list[dict]) -> list[dict]:
    ref = []
    for g in groups:
        for ep in _flat_endpoints(g):
            if ep.get("auth") is None:
                continue
            ref.append({
                "method": ep["method"],
                "path": ep["path"],
                "summary": ep["summary"],
                "auth": ep["auth"],
                "group_title": g["title"],
                "anchor": ep["id"],
            })
    return ref


# ---------------------------------------------------------------------------
# Markdown export — make every endpoint copy-pasteable for AI consumption
# ---------------------------------------------------------------------------

_AUTH_LABEL_MD = {
    "session": "登录态 (Session Cookie)",
    "bearer": "Bearer Token",
    "public": "公开 (无需认证)",
}


def _params_to_markdown(params: list[dict]) -> str:
    if not params:
        return ""
    lines = ["**请求参数**", "", "| 参数名 | 类型 | 必填 | 说明 |", "|--------|------|------|------|"]
    for p in params:
        req = "是" if p.get("required") else "否"
        desc = (p.get("description") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{p['name']}` | {p.get('type', '')} | {req} | {desc} |")
    return "\n".join(lines)


def _endpoint_to_markdown(ep: dict) -> str:
    auth = ep.get("auth")
    if auth is None:
        # Error code rows — render as a simpler block
        return f"### {ep['path']} — {ep['summary']}\n\n{ep.get('description', '')}\n\n响应示例：`{ep.get('response_example', '')}`"

    auth_label = _AUTH_LABEL_MD.get(auth, "—")
    lines = [
        f"### `{ep['method']} {ep['path']}` — {ep['summary']}",
        "",
    ]
    if ep.get("description"):
        lines.append(ep["description"])
        lines.append("")
    lines.append(f"- **认证**: {auth_label}")
    lines.append("")

    if ep.get("params"):
        lines.append(_params_to_markdown(ep["params"]))
        lines.append("")

    if ep.get("request_example"):
        lines.append("**请求示例**")
        lines.append("")
        lines.append("```")
        lines.append(ep["request_example"])
        lines.append("```")
        lines.append("")

    if ep.get("response_example"):
        lines.append("**响应示例**")
        lines.append("")
        lines.append("```json")
        lines.append(ep["response_example"])
        lines.append("```")
        lines.append("")

    if ep.get("curl_example"):
        lines.append("**curl**")
        lines.append("")
        lines.append("```bash")
        lines.append(ep["curl_example"])
        lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _group_to_markdown(group: dict) -> str:
    parts = [
        f"## {group['title']}",
        "",
    ]
    if group.get("description"):
        parts.append(group["description"])
        parts.append("")

    for ep in group.get("endpoints") or []:
        parts.append(_endpoint_to_markdown(ep))
        parts.append("")

    for sub in group.get("subsections") or []:
        parts.append(f"### 【{sub['title']}】")
        parts.append("")
        for ep in sub.get("endpoints") or []:
            parts.append(_endpoint_to_markdown(ep))
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


_AGENT_GUIDE_MD = """# CRM 系统 API 文档

> 本文档供 AI Agent（如 Claude Code）和开发者集成使用。Agent 可直接阅读本文档并调用所有 API。

## Agent 接入指南

### Base URL

`https://<YOUR_DOMAIN>` — 所有路径均相对于此域名，使用前请替换为实际部署域名。

### 认证方式

- **登录态 (Session Cookie)**: 大部分接口使用。先通过 `GET /login` 或 `POST /login` 获取 session，后续请求携带 Cookie 即可。
- **公开**: 问卷前台提交、企微回调等不需要认证。
- 写操作需在请求参数中传 `admin_action_token`（从 session 获取）或 `confirm=true` 防止误触发。

### 请求约定

- 请求体使用 `Content-Type: application/json`
- 所有响应格式统一：`{"ok": true, ...payload}` 或 `{"ok": false, "error": "..."}`
- 分页使用 `limit` + `cursor` 或 `limit` + `offset`
- 路径参数用尖括号标记，如 `/api/customers/<external_userid>`

### 错误码

- `400` 参数校验失败
- `401` 未认证
- `403` 权限不足
- `404` 资源不存在
- `503` 服务未就绪
"""


def _full_doc_markdown(groups: list[dict]) -> str:
    parts = [_AGENT_GUIDE_MD, ""]
    for g in groups:
        parts.append(_group_to_markdown(g))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _build_markdown_data(groups: list[dict]) -> dict:
    data = {"endpoints": {}, "groups": {}, "full": _full_doc_markdown(groups)}
    for g in groups:
        data["groups"][g["id"]] = _group_to_markdown(g)
        for ep in _flat_endpoints(g):
            data["endpoints"][ep["id"]] = _endpoint_to_markdown(ep)
    return data


def build_api_docs_view_model() -> dict:
    groups = _api_endpoint_groups()
    return {
        "endpoint_groups": groups,
        "quick_reference": _build_quick_reference(groups),
        "markdown_data": _build_markdown_data(groups),
    }


__all__ = [
    "_api_endpoint_groups",
    "build_api_docs_view_model",
]
