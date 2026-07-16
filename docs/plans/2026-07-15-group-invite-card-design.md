# 群邀请卡片全发送场景设计

## 目标

在 AI-CRM Next 中新增统一的“群邀请卡片”素材。管理员维护一次企微 `https://work.weixin.qq.com/gm/...` 加群链接后，可在企业群发、私信群发、AI 助手固定内容、自动化运营节点和渠道欢迎语中选择同一素材；下发时统一转换为企微 `link` 附件，客户点击卡片进入加群流程，不再接收需要扫描的二维码图片。

## 方案选择

采用独立的 `group_invite_library` 素材类型，而不是在五个业务页面分别保存标题、描述和链接。统一素材可以复用现有 `send_content` 内容包、素材选择器、预览和使用关系查询，也避免五套数据校验与企微 payload 组装。卡片保存 `title`、`description`、`pic_url`、`join_url`，并可保存企微 `config_id`、`state` 和目标群等运维元数据。

本期不自动调用企微 `add_join_way` 创建或更新进群方式。该接口属于新的真实企微配置写操作，不在现有消息外呼批准范围内；管理员先使用企微已生成的 `gm` 链接创建素材。后续如批准 join-way 配置外呼，可在 `integration_gateway` 和 external-effect 审计边界内单独增加同步命令，不改变本期发送内容契约。

## 架构与数据流

- `media_library` 是群邀请素材 CRUD 和管理页 owner，新增 `/admin/group-invite-library` 及 `/api/admin/group-invite-library`。
- `send_content` 在标准内容包中新增 `group_invite_library_ids`，素材选择器、预览、校验和使用关系查询统一认识 `group_invite`。
- `automation_engine.group_ops` 的素材解析器把素材解析为 `{"msgtype":"link","link":...}`；群发、私信群发、AI 助手和自动化运营继续走既有内容包和发送队列。
- `channel_entry` 在渠道配置中新增 `welcome_group_invite_library_ids`，欢迎语外部效果执行前通过同一个素材解析器得到 link 附件。
- `integration_gateway` 仅透传并校验官方 link payload，不新增未批准的真实配置外呼。

## 校验与错误处理

- `join_url` 必须是 HTTPS，域名必须为 `work.weixin.qq.com`，路径必须以 `/gm/` 开头。
- 标题必填，最长 128 字节；描述最长 512 字节；封面 URL 可空，非空时必须是 HTTP(S)。
- 每个内容包最多选择 1 个群邀请卡片；总附件数量仍受企微最多 9 个附件约束。
- 素材不存在、停用或字段不完整时，发送在真实企微调用前失败为 `material_resolve_failed`。
- 历史内容包没有新字段时按空数组读取，保持兼容。

## 前端信息架构

新增独立二级管理页用于群邀请素材的新增、编辑、启停和删除；群发、AI 助手、自动化运营和欢迎语页面继续使用既有发送内容弹层，只增加“+群邀请”入口和卡片预览。页面不新增重复标题，素材选择继续复用 `material_picker.js`，内容编辑继续复用 `send_content_composer.js`。

## 验证与回滚

单元测试覆盖 URL 契约、CRUD、内容包标准化、素材解析、link 消息校验、欢迎语和私信队列；前端契约测试覆盖素材入口与五个场景字段保留；迁移测试覆盖新表和渠道列。回滚时停止选择新素材并回滚应用版本；数据库新增表和 JSONB 列可保留，不影响旧版本读取。若必须数据库回滚，迁移 downgrade 删除新增列与表。
