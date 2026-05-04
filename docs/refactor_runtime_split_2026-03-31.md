# 2026-03-31 运行治理拆分记录

本次调整目标不是加新功能，而是把已经影响维护和运行的超大文件拆开，同时保持现有接口与测试行为不变。

## 本次完成

### 1. `routes.py` 去内联页面
原始 `wecom_ability_service/routes.py` 为 **6210 行**，其中包含多段超长 `render_template_string(...)` 内联 HTML/JS。

已完成：
- 页面模板迁移到 `wecom_ability_service/templates/`
- 路由改为 `render_template(...)`
- 清理 `render_template_string` 依赖
- 同时修正 OAuth 时间戳中的 `datetime.utcnow()` 弃用用法

拆分后：
- `wecom_ability_service/routes.py` → **2602 行**
- 新增模板：
  - `templates/sidebar_bind_mobile.html`
  - `templates/admin_class_user_management.html`
  - `templates/admin_class_user_backoffice.html`
  - `templates/admin_questionnaires.html`
  - `templates/questionnaire_h5_page.html`
  - `templates/questionnaire_h5_submitted.html`

### 2. `services.py` 按领域拆分
原始 `wecom_ability_service/services.py` 为 **6530 行**。

已按领域拆到以下模块，并保留 `wecom_ability_service.services` 的原始导出面，避免现有调用方大面积改 import：

- `class_user_service.py`
- `user_ops_service.py`
- `identity_binding_service.py`
- `archive_message_service.py`
- `questionnaire_service.py`

拆分后：
- `wecom_ability_service/services.py` → **848 行**

### 3. 兼容性处理
由于测试和现有调用会直接 patch `wecom_ability_service.services` 下的一些私有 helper，本次保留了兼容层：
- `_user_ops_contact_client`
- `_resolve_third_party_user_id_by_mobile`
- `_extract_third_party_user_id`

这样拆分后，旧测试和旧调用方式仍然有效。

### 4. 弃用告警修正
已替换：
- `datetime.utcnow()` → `datetime.now(timezone.utc)`

## 验证结果

执行：

```bash
PYTHONPATH=. pytest -q
```

结果：

```text
213 passed
```

## 本次拆分后的主要边界

### 路由层
- `routes.py` 保留路由注册与少量 orchestration
- 大体积 UI 模板移入 `templates/`

### 服务层
- `services.py` 变为兼容 facade
- 班期/用户运营逻辑：`user_ops_service.py`
- 身份绑定/第三方用户同步：`identity_binding_service.py`
- 群聊/消息/批次/标签快照：`archive_message_service.py`
- 问卷后台 + 提交链路：`questionnaire_service.py`
- class user 状态读写：`class_user_service.py`

## 仍可继续做的下一步

这轮已经把最影响维护和运行的“大块字符串 + 超大服务文件”拆掉了。后续如果继续治理，建议下一批是：

1. 再把 `user_ops_service.py` 继续拆成：池构建、班期回填、导入解析三块
2. 再把 `questionnaire_service.py` 拆成：后台配置、公开读取、提交落库三块
3. 视情况把 `routes.py` 再按领域拆成多个 blueprint 模块
