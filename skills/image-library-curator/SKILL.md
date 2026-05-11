---
name: image-library-curator
description: AI-CRM 图片素材库的语义编排器。当用户说「给图片素材库自动打标 / 分析未打标的图 / 给这张图加标签和描述 / 上传图片到素材库（带元数据）/ 根据这段对话推荐合适的图」时使用。本 Skill 通过 CRM 的 MCP 端点（image_library_* 5 个工具）读写素材库，所有 vision 分析在当前 Claude 会话内完成（不调外部 API）。
---

# image-library-curator

让 AI-CRM 的图片素材库具备 AI 化的元数据维护和语义检索能力。CRM 服务**不调任何 LLM**，纯做数据；本 Skill 在 Claude Code 会话里完成图片理解 + 元数据生成 + 推荐决策，通过 MCP 协议读写 CRM。

## 何时触发

用户的请求落在以下任一类时使用本 Skill：

- **批量打标**："给素材库还没打标的图自动分析一下"、"把今天上传的几张新图分类好"
- **单图打标**："给这张图（id=123）加标签和描述"
- **上传 + 打标一体**："把这张图上传到素材库，AI 直接分类"
- **聊天推荐**："我现在和某某客户聊到 X，从素材库找几张合适的图发"、"用户表达对效果质疑时，有什么好评截图能用"
- **元数据修复**："素材库里 tags 用得太乱，帮我整理一下"

## 前置条件

调用任何工具前确认 CRM MCP 已接入。可以通过尝试 `image_library_facets`（无副作用）来验证；如果失败提示 token / endpoint 问题，让用户参考 [README.md](README.md) 配置 `.mcp.json`。

## 可用工具（来自 CRM MCP 服务）

| 工具 | 副作用 | 用途 |
|---|---|---|
| `image_library_list` | read | 按 q / tags / category / only_unlabeled 过滤拉候选 |
| `image_library_get` | read | with_data=true 时返回 base64 给 vision 分析 |
| `image_library_facets` | read | 拉**当前已用**的分类 + 标签池，避免造新词 |
| `image_library_update_metadata` | write | 写元数据；overwrite=false 时只填空字段 |
| `image_library_upload` | write | base64 直传新图 + 一次性带元数据 |

## 三条工作流

### 工作流 A — 批量给未打标的图补元数据

详见 [references/workflow-a-batch-annotate.md](references/workflow-a-batch-annotate.md)。

骨架：
1. 调 `image_library_facets` 拉现有 categories + tags 池（**复用，不造新词**）
2. 调 `image_library_list({only_unlabeled: true, limit: 20})` 拿一批
3. 对每张图：
   a. 调 `image_library_get({image_id, with_data: true})` 拿原图 base64
   b. 把 base64 喂给当前 Claude（vision），按 [system-prompt.md](references/system-prompt.md) 约束输出 JSON
   c. 调 `image_library_update_metadata({image_id, ..., overwrite: false})` 写回（保护人工已编辑的字段）
4. 输出汇总报告：处理了几张、新增了哪些 tags / categories（高亮新词请用户确认是否合并）

### 工作流 B — 上传新图时自动打标

详见 [references/workflow-b-upload-annotate.md](references/workflow-b-upload-annotate.md)。

骨架（用户在 Claude Code 里贴图 / 给文件路径）：
1. 把图转 base64
2. 调 `image_library_facets` 拉现有词汇池
3. vision 分析图片 → 输出元数据（按 system-prompt 约束）
4. 调 `image_library_upload({data_base64, ...metadata})` 一步到位入库
5. 回传新建的 image_id 给用户

### 工作流 C — 聊天上下文推荐

详见 [references/workflow-c-recommend.md](references/workflow-c-recommend.md)。

骨架（用户给一段对话上下文 + 想要的图类型）：
1. 提取对话中的客户痛点 / 情绪 / 决策阶段 → 选 1-3 个 tags + 候选 category
2. 调 `image_library_list({tags, category, limit: 10})` 拿候选**元数据**（不带 base64）
3. 读 description 和 tags，做语义重排选 top 3-5 张
4. （可选）对 top 1-2 调 `image_library_get({with_data: true})` vision 二次确认
5. 输出推荐：每张给出 image_id + 引用理由 + 直接可拷贝的发送指引

## 共同操作原则

- **不造新词**：默认从 `image_library_facets` 拿到的池里选 category + tags。需要新增时**显式告诉用户**「我打算加一个新分类 X / 新标签 Y，是否合并到 Z」。
- **`overwrite=false` 是安全默认**：批量打标时永远用 `overwrite=false`，避免覆盖人工已编辑的内容。只有用户明确说「重写所有 AI 之前打的标」才用 `overwrite=true`。
- **vision 分析的输出必须严格 JSON**：按 [system-prompt.md](references/system-prompt.md) 约束。如果模型输出含说明性文字，先提取 JSON 部分再调 update。
- **失败要透**：MCP 工具返回 `{"ok": false, "error": ...}` 时把 error 原文传给用户，不要重试到用户感知不到。
- **批量分批**：一次最多处理 20 张图（Skill 内部循环），避免 token 超限和单次失败放大。

## 响应风格

- 中文为主（与项目偏好一致）
- 报告进度（"处理 1/20 — id=123 ..."）但不要把每张图的 base64 / 完整 JSON 都贴出来，只给摘要
- 最后给一个 markdown 表格汇总：image_id / 新加的 tags / category / 跳过原因
- 涉及"新词"时高亮提示用户确认

## 出错排查

- `unknown tool: image_library_*` → CRM 那一侧版本太老，没合 PR-C；或 .mcp.json 连错了 endpoint
- `401 missing internal token` / `invalid internal token` → MCP_BEARER_TOKEN 没配或配错
- `image too large (max 5MB)` → 上传前自己压缩
- `image {id} 没有 base64 数据` 且 `source=url` → CRM 服务器拉外链失败，让用户检查图片 URL 可达性

更多细节见 [README.md](README.md)。
