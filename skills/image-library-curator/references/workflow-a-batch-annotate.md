# 工作流 A — 批量给未打标的图补元数据

适用场景：素材库里堆了不少历史图、运营来不及一张张写描述。

## 步骤

### 1. 拉现有词汇池

```
image_library_facets({})
```

把返回的 `categories` 和 `tags` 数组**记在心里**。后面打标时优先复用，不造新词。

### 2. 拉一批未打标的图

```
image_library_list({only_unlabeled: true, limit: 20})
```

注意：

- `only_unlabeled=true` 命中 description / tags / category **任一为空**的记录，不要求三个全空
- 返回不含 base64，先看元数据决定要处理的
- 默认 `enabled_only=true`，停用的图不处理

如果返回空数组，告诉用户"没有需要打标的图"，结束。

### 3. 逐张处理

对返回的每张图（用 `for` 串行；并行有重复 facets 写入风险）：

#### 3a. 拿原图

```
image_library_get({image_id, with_data: true})
```

返回里：
- `source = "upload" | "base64"` → 用 `data_base64` 字段
- `source = "url"` → 服务器会拉外链转 base64（同样进 `data_base64`）

#### 3b. Vision 分析

把 base64 喂给当前 Claude（自带 vision 能力），按 [system-prompt.md](system-prompt.md) 严格输出 JSON：

```json
{
  "description": "...",
  "tags": [...],
  "category": "...",
  "ai_metadata": {...}
}
```

**关键约束**（重述自 system-prompt）：
- description 必须同时说"画面是什么"+"适合什么沟通场景"，100-200 字
- tags / category 优先复用 facets 池里的词
- 造新词时记下来，最后汇总给用户确认

#### 3c. 写回

```
image_library_update_metadata({
  image_id: <id>,
  description: "...",
  tags: [...],
  category: "...",
  ai_metadata: {...},
  overwrite: false
})
```

**`overwrite=false` 是默认安全策略**：
- 如果用户之前手动写过 description 或 category，这次 AI 的会被跳过
- 返回的 `applied: [...]` 数组告诉你实际写入了哪几个字段
- 跳过的字段在汇总报告里标注，不要默默忽略

### 4. 汇总报告

最后给用户一个 markdown 表格：

```markdown
| image_id | name | category 写入 | tags 写入 | description 写入 | 跳过 |
|---|---|---|---|---|---|
| 12 | 5月主图.png | ✅ 活动海报 | ✅ +3 | ✅ | - |
| 15 | 截图1.png | ⏭ (已有) | ✅ +2 | ✅ | category（人工已编辑） |
| 18 | xx.jpg | ❌ | ❌ | ❌ | vision 解析失败 |
```

加一段"新词建议"区块（如有）：

```markdown
**本次 AI 想新增的词，请确认是否合并：**
- 新分类「教程截图」可以合并到现有「操作指引」吗？
- 新标签「Q3 活动」可以合并到「Q3」吗？
```

### 5. 循环（可选）

如果第 2 步的 `count == limit`（说明可能还有未处理的），告诉用户"还有更多未打标，要继续吗？"，等指令再下一批。

## 失败兜底

| 错误 | 处理 |
|---|---|
| `image {id} 没有 base64 数据` 且 source=url | 跳过这张，记入失败列表（外链失效） |
| vision 输出无法解析成 JSON | 只 update description（不写 tags/category），失败列表标注"自动打标失败，已写入描述" |
| `image too large` | 跳过；这张图本来就不该 5MB+，让用户重新压缩上传 |
| MCP 401 | 立即停止，告诉用户检查 MCP_BEARER_TOKEN |

## 反模式（避免）

- ❌ **不调 facets 直接打标** —— 会造一堆碎片化新词
- ❌ **overwrite=true** —— 除非用户明确说"重写所有 AI 之前打的标"
- ❌ **batch 超过 20 张** —— token / 失败放大风险，分批
- ❌ **并行处理** —— facets 池实时变化（你刚加的词另一并行任务看不到）
