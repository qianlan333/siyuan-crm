# UI Redesign Design System

来源：

- `/Users/qianlan/Downloads/AIcrm _.zip`
- `redesigned/admin_console.css`
- `redesigned/questionnaire_h5_page.html`
- `redesigned/questionnaire_h5_submitted.html`
- `redesigned/open_in_wechat.html`
- `redesigned/sidebar_bind_mobile.html`

目标：

- 统一 admin / h5 / sidebar 三端设计语言。
- 不改变业务逻辑、路由语义、接口语义、数据模型。
- 以 zip 的蓝灰色飞书系视觉为基线，后台密度更高，H5 更轻，sidebar 更聚焦单客户动作。

## 1. 颜色

### Core tokens

| Token | 值 | 用途 |
| --- | --- | --- |
| `--c-t1` | `#1F2329` | 一级正文 / 标题 |
| `--c-t2` | `#4E5969` | 二级正文 / 说明 |
| `--c-t3` | `#8F959E` | 辅助文案 / placeholder |
| `--c-t4` | `#C2C7CC` | 禁用态 / 分隔弱文案 |
| `--c-bg` | `#F2F3F5` | 页面背景 |
| `--c-hover` | `#F5F6F7` | hover 背景 |
| `--c-white` | `#FFFFFF` | 面板底色 |
| `--c-border` | `#DEE0E3` | 统一边框 |
| `--c-div` | `#F0F1F2` | 轻分割线 |
| `--c-blue` | `#3370FF` | 主品牌 / CTA |
| `--c-blue-light` | `#EBF2FF` | 主品牌弱背景 |
| `--c-blue-dark` | `#1456F0` | 主品牌深色 hover / active |
| `--c-green` | `#00B884` | 成功态 |
| `--c-green-bg` | `#E6FAF5` | 成功背景 |
| `--c-orange` | `#FF8800` | 警告态 |
| `--c-orange-bg` | `#FFF3E0` | 警告背景 |
| `--c-red` | `#F54A45` | 错误态 |
| `--c-red-bg` | `#FEF0EF` | 错误背景 |
| `--c-purple` | `#7B61FF` | 次级强调 / AI 特征色 |
| `--c-purple-bg` | `#F0EEFF` | 次级强调背景 |

### 使用原则

- 页面大背景统一用 `#F2F3F5`，不再使用偏黄、偏绿底色。
- 主按钮、活动 tab、当前步骤、选中卡片统一走蓝色系。
- 成功、警告、失败严格用绿 / 橙 / 红，不混用品牌蓝。

## 2. 字体

- 中文：`"PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif`
- 英文数字：沿用系统 UI 字体栈
- 代码 / JSON / 协议块：`ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`

推荐层级：

- `h1`：28-40px，字重 700-800，负字距
- `h2`：22-30px，字重 700
- `h3`：16-20px，字重 700
- 正文：14-15px
- 辅助文案：12-13px

## 3. 圆角

| Token / 级别 | 推荐值 | 用途 |
| --- | --- | --- |
| 基础圆角 | `8px` | zip 原始 token |
| 表单控件 | `12px-14px` | input / select / button |
| 中型面板 | `16px-18px` | 卡片、表格容器、Drawer 内卡片 |
| 大型容器 | `20px-24px` | Hero、主卡片、移动端成功页 |
| 胶囊 | `999px` | tab、badge、tag、筛选 chip |

落地规则：

- admin 面板推荐 `18px-20px`
- h5 / sidebar 顶层容器推荐 `20px-24px`
- 小按钮和输入框不要再用过大的 20px+ 圆角

## 4. 阴影

| Token | 值 | 用途 |
| --- | --- | --- |
| `--shadow-sm` | `0 1px 4px rgba(0,0,0,0.06)` | 表格容器 / 次级卡片 |
| `--shadow-md` | `0 4px 16px rgba(0,0,0,0.10)` | Hero / 浮层 / 主卡片 |
| H5 / sidebar shadow | `0 2px 8px rgba(0,0,0,0.08)` | 移动端轻量悬浮感 |

规则：

- 后台整体用轻阴影 + 清晰边框，不做厚重拟物。
- H5 和 sidebar 阴影更轻，优先靠边框和层级区分。

## 5. 间距体系

建议以 4 的倍数为主：

- `4px`：超小间距
- `8px`：chip / inline action gap
- `12px`：表单块内部间距
- `16px`：卡片内容基础内边距
- `20px`：主卡片和 hero 内边距起点
- `24px`：后台和 H5 顶级容器常规间距
- `32px+`：大段区块之间留白

## 6. 按钮样式

### Primary button

- 背景：`linear-gradient(135deg, #3370FF, #1456F0)`
- 文案：白色
- 圆角：胶囊或 12-14px
- hover / active：加深到 `#1456F0`

### Secondary button

- 背景：白底或 `#EBF2FF`
- 边框：`#DEE0E3` 或蓝色弱边框
- 文案：`#1456F0`

### Ghost button

- 白底
- 轻边框
- 文案用正文色或品牌色

### Danger button

- 红色渐变或纯红底
- 只用于删除、停用、移出池子、撤销关键状态

## 7. 表单样式

- 输入框背景：白底
- 边框：`#DEE0E3`
- focus：`#3370FF`
- placeholder：`#8F959E`
- label：12-13px，字重 600-700
- 表单区块建议配合卡片或分组标题，不直接散落在页面上

后台推荐模式：

- `列表 + 编辑区 / 抽屉`
- 表单分组要明确：“基础信息 / 行为规则 / 绑定关系 / 高级信息”

## 8. 表格样式

- 表头底色：`#F7F9FC`
- 行边框：`#F0F1F2`
- hover 行：蓝色弱背景
- 活动态 / 当前选中态：`#EBF2FF`
- 行内动作右对齐，重要主动作只保留 1 个，其余 secondary / ghost

## 9. 卡片样式

- 白底 + 轻边框 + 轻阴影
- 标题区和内容区明确分层
- summary card 结构推荐：
  - label：12px
  - value：24-28px
  - note：12px 辅助说明

## 10. Badge / Tag / Empty State / Drawer / Modal 样式

### Badge / Tag

- 默认：灰底灰字
- 主强调：蓝底蓝字
- 成功：绿底绿字
- 警告：橙底橙字
- 失败：红底红字

### Empty state

- 使用简短标题 + 说明 + 主 CTA
- 不再使用大面积空白和粗糙占位
- sunset / not found / no data 三类文案语气分开

### Drawer

- 白底，18-20px 圆角
- 标题区固定，操作区 sticky
- 长表单尽量放 Drawer，避免页面跳转

### Modal

- 中心弹层，圆角 18-20px
- 只承载确认、标签选择、短编辑
- 复杂编辑优先 Drawer，不放 Modal

## 11. admin / h5 / sidebar 三端差异

### admin

- 信息密度最高
- 有 sidebar / topbar / breadcrumb / hero / summary cards / table
- 适合工作台、配置中心、内容管理、运行中心

### h5

- 只保留单列结构
- 操作路径非常短：授权 -> 填写 -> 提交完成
- 按钮更大、留白更多、说明更克制
- 不继承后台 shell、后台表格、后台导航

### sidebar

- 面向单客户
- 结构以“识别结果 + 绑定动作 + 自动化动作 + 上下文只读卡片”为主
- 比 H5 稍密，比后台更聚焦
- 不带后台 sidebar / breadcrumb / admin shell

## 组件落地建议

- admin 公共壳层：统一 hero、cards、table、form、drawer、modal
- automation 方案页：统一 program context header + workspace tabs
- config 页：统一 list + editor aside
- 问卷后台：偏内容管理，不直接套 automation 工作台重界面
- 问卷 H5：直接对齐 zip 的三份 HTML 风格
- sidebar：直接对齐 `sidebar_bind_mobile.html` 风格
