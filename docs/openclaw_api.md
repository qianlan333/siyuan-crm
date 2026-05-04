# OpenClaw Minimal API

当前已真实跑通、适合 OpenClaw 直接调用的最小接口清单。

## A. 消息

### `GET /api/messages/<external_userid>`

读取某个客户全部历史消息。

可选参数：

- `chat_type=private`
- `chat_type=group`

### `GET /api/messages/<external_userid>/recent`

读取某个客户最近 N 条消息。

可选参数：

- `limit=20`
- `chat_type=private`
- `chat_type=group`

### `GET /api/messages/search`

按关键词搜索某个客户消息。

参数：

- `external_userid`
- `keyword`

## B. Contacts

### `GET /api/contacts`

获取本地客户映射列表。

可选参数：

- `owner_userid`
- `sync=0|1`

### `GET /api/contacts/<external_userid>`

获取单个客户详情。

可选参数：

- `sync=0|1`

### `POST /api/contacts/full-sync`

全量同步客户，并按规则补齐 `description`。

### `POST /api/contacts/sync-new`

仅同步本地缺失客户，并按规则补齐 `description`。

### `POST /api/contacts/normalize-description`

历史 `description` 规则纠正：

- 空值 -> 写纯 `external_userid`
- 旧格式 `external_userid: <id>` -> 改成纯 `<id>`
- 人工内容默认不覆盖

## C. 标签

### `GET /api/tags`

读取企业标签库。

### `POST /api/tags`

创建企业标签。

### `POST /api/tags/mark`

给单个客户打标签。

### `POST /api/tags/unmark`

给单个客户删标签。

## D. 官方任务

### `POST /api/tasks/private-message`

创建客户私信群发任务。

### `POST /api/tasks/moment`

创建客户朋友圈任务。

### `POST /api/tasks/group-message`

创建客户群群发任务。

## E. 群目录

### `POST /api/group-chats/full-sync`

全量同步客户群目录。

### `POST /api/group-chats/sync-new`

只同步本地不存在的客户群目录。

## F. 运维

### `GET /api/archive/health`

查看会话存档 SDK 和私钥路径状态。

### `GET /api/ops/status`

查看当前服务运维状态摘要：

- `service_ok`
- `archived_messages_count`
- `contacts_count`
- `group_chats_count`
- `database_backend`
- `last_seq`
- `last_archive_sync_status`
- `last_archive_sync_time`
- `last_contacts_sync_time`
- `callback_enabled`
- `cron_script_path`
- `env_file_path`
- PostgreSQL 模式：`database_url_configured`
- SQLite 模式：`sqlite_path`
