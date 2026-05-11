# Vision 分析的输出约定

## 严格 JSON Schema

所有 AI 自动打标场景，vision 分析的输出**必须**是下面这个形态的 JSON 对象（不要带任何说明性文字、markdown 代码块标记或前后缀）：

```json
{
  "description": "一段中文自然语言描述，必须同时回答两件事：(1) 画面上有什么；(2) 这张图适合在什么沟通场景使用。100-200 字。",
  "tags": ["好评截图", "信任建立"],
  "category": "好评截图",
  "ai_metadata": {
    "objects": ["chat_bubble", "phone_screenshot"],
    "ocr_excerpt": "图中能识别的关键文字（截 100 字）",
    "scene_type": "chat_screenshot | product_photo | poster | infographic | other",
    "vision_confidence": 0.85
  }
}
```

字段约束：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `description` | string | 是 | 100-200 中文字符；超过 4000 字符会被 CRM 截断 |
| `tags` | array of string | 是 | 3-8 个；每个最多 64 字符；**优先复用 facets 池里的词** |
| `category` | string | 是 | 单值；最多 80 字符；**优先复用 facets 池里的词** |
| `ai_metadata` | object | 是 | 结构开放；建议至少含 `scene_type` + `vision_confidence` |

## 描述（description）的写法

**好的描述**（同时回答"画面是什么 + 适合什么场景"）：

> "微信聊天截图，宝妈用户晒孩子使用产品 30 天后的进步，配文'真的有效果，比我想象的好太多'。适合在客户表达对效果质疑时回复，强化产品有效性的社会证明。"

**不好的描述**（只描述画面，不说场景）：

> "一张微信聊天截图，里面是一个用户在评价产品。"

**也不好**（场景描述太宽泛）：

> "可以用在很多场景。"

## 标签（tags）的命名规范

### 优先复用现有标签

调 `image_library_facets` 看 `tags` 数组里的词。**只有现有词都不合适时**才造新词，造新词时在最终汇报里高亮提示用户确认是否合并到已有标签。

### 标签维度（建议覆盖 2-4 个维度）

每张图的 tags 最好覆盖以下维度的几个：

- **内容性质**：好评截图 / 产品截图 / 活动海报 / 数据对比图 / 操作指引 / 解决方案 / 教程截图
- **沟通意图**：信任建立 / 价格说服 / 决策辅助 / 风险化解 / 紧迫感塑造 / 案例展示
- **目标群体**：宝妈群体 / 高客单 / 新客户 / 复购客户 / 学生家长
- **业务主题**（按项目实际）：5月活动 / 体验课 / 暑期班

### 反模式（避免）

- ❌ 用「图片」「截图」这种空白标签（描述什么图就有什么图，标签是检索维度）
- ❌ 一张图打 20 个标签（噪音；超过 50 个会被 CRM 截掉）
- ❌ 用相似词重复（「好评」+「正面评价」，留一个就够）

## 分类（category）的选取

`category` 是**单值**，主要给前端筛选侧边栏分组用。粒度比 tags 粗，互斥。常见分类：

- 好评截图
- 产品案例
- 活动海报
- 聊天话术配图
- 解决方案
- 操作指引
- 数据对比

`facets.categories` 里有的优先用；造新分类时显式告知用户。

## ai_metadata 的扩展性

`ai_metadata` 是**逃生舱** —— 任何你想保留但不影响主 schema 的结构化信息都可以塞，未来推荐场景可以读。建议至少有：

```json
{
  "scene_type": "chat_screenshot",       // 场景类型枚举
  "vision_confidence": 0.85,              // 0-1 自评置信度，给后续重排用
  "ocr_excerpt": "...",                   // 关键文字（如有）
  "objects": ["chat_bubble", "ui_card"], // 检测到的元素
  "color_dominant": "blue"                // 可选：主色调
}
```

## 解析失败时的兜底

如果 vision 输出无法解析成上述 JSON：

1. 先尝试自己 fix（去掉 markdown 标记、补全闭合括号）
2. 还不行就**只写 description**，调 `image_library_update_metadata({image_id, description: "..."})` 不动 tags / category
3. 在汇总报告里标注"#123 自动打标失败，已写入描述但 tags/category 留空，请人工补"
