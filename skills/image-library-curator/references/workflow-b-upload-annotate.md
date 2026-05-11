# 工作流 B — 上传新图时自动打标

适用场景：用户在 Claude Code 里贴图 / 给文件路径 / 给 base64，让 Skill 直接上传到 CRM 素材库并自动打标。

## 步骤

### 1. 把图源转成 base64

输入形态可能是：

- **图片文件路径**（本地）：`/path/to/foo.png`
- **粘贴的图片**（Claude Code 自动转 base64）
- **URL**（外链）

转换：

| 输入 | 处理 |
|---|---|
| 文件路径 | 读字节 → `base64` 编码 → 字符串 |
| 已是 base64 | 检查是否带 `data:image/...;base64,` 头；CRM 会自动剥离 |
| URL | 优先**不**用本工作流，改成调 CRM 的 `from-url` admin endpoint，让 CRM 服务器拉。如果一定要走 MCP，先 `wget`/curl 拉到本地再转 base64 |

### 2. 拉现有词汇池

```
image_library_facets({})
```

记下 `categories` + `tags`，打标时优先复用。

### 3. Vision 分析

把 base64 喂给当前 Claude。按 [system-prompt.md](system-prompt.md) 严格输出 JSON：

```json
{
  "description": "...",
  "tags": [...],
  "category": "...",
  "ai_metadata": {...}
}
```

**特别约束**（上传场景比批量打标更敏感）：

- 如果用户在请求里给了 hint（"这张是好评截图"），ai_metadata 里加一条 `user_hint: "..."` 保留原话
- 如果图里有明显的客户姓名 / 手机号 / 内部信息（OCR 能识别出），在 description 里**不要**复述敏感原文，只用脱敏概括（"客户名为某某 -> 客户表达..."）

### 4. 一站式入库

```
image_library_upload({
  data_base64: "<base64 字节，不含 data: 头也行>",
  file_name: "<原文件名 / 自动生成>.png",
  mime_type: "image/png",  // 或 image/jpeg
  name: "<运营备注，可选；留空用 file_name>",
  description: "<vision 输出>",
  tags: [...],
  category: "...",
  ai_metadata: {...}
})
```

返回 `{"ok": true, "item": {...}}`，里面有新建的 `id`。

### 5. 回报

简短回报给用户：

```
✅ 已上传 #234（5MB ↓ 800KB），分类「好评截图」，标签：好评 / 信任建立 / 宝妈群体。
描述：微信聊天截图，宝妈用户晒孩子使用产品 30 天后的进步...
```

如果造了新词，提示：

```
⚠️ 这张图我加了一个新标签「Q3 活动」，要不要合并到已有「Q3」？
```

## 失败兜底

| 错误 | 处理 |
|---|---|
| `data_base64 is empty` | 检查转换流程，可能文件读取失败 |
| `only image/* allowed` | mime_type 配错；或者用户传了 PDF / Word，提示用户图片才支持 |
| `file too large (max 5MB)` | 让用户重新压缩 / 缩放后再来；或者主动用 sips / pillow 压一压 |
| `data_base64 decode failed` | base64 字符串损坏；如果带了 `data:` 头检查格式 |

## 与工作流 A 的区别

| | 工作流 A | 工作流 B |
|---|---|---|
| 触发 | 库里已有图 | 用户给新图源 |
| 调用 | `update_metadata` | `upload`（一次性带元数据） |
| 批量 | 是（一次最多 20 张） | 单张为主 |
| `overwrite` | false（保护人工） | 不适用（新建） |

## 反模式（避免）

- ❌ **不分析直接用文件名当 description** —— 文件名通常是 `IMG_20240501.jpg` 之类没意义
- ❌ **复述图片里的客户敏感信息** —— OCR 能识别但 description 不该复述手机号 / 姓名 / 订单号
- ❌ **不调 facets** —— 同工作流 A，会造碎片化新词
