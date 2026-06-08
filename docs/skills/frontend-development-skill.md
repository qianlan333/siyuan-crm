# AI-CRM Frontend Development Skill

## 0. 适用范围

This skill applies to all frontend-related tasks in the AI-CRM repository,
including:

- New pages
- Page changes
- New components
- Component changes
- Admin-console features
- Forms
- Lists
- Detail pages
- Edit pages
- Selectors
- Binders
- Upload / preview flows
- API integration
- State management
- UI style adjustments

Before any frontend task starts, read this skill and execute it in order.

## 1. 开发前必须先做“既有模式盘点”

Do not write frontend code until the existing repository patterns have been
searched and compared.

### 1.1 页面模式检查

For the task type, search existing pages of the same kind:

- Management list pages
- New/create pages
- Edit pages
- Detail pages
- Configuration pages
- Preview pages
- Binding pages
- Upload pages
- Tag management pages
- Channel-code management pages
- Product management pages
- Content / material management pages

Prefer mature existing information architecture, route structure, layout,
component composition, and interaction behavior. Do not redesign a page
structure without first checking existing pages.

### 1.2 组件复用检查

Before adding a component, search:

- Components
- Shared/common components
- Hooks
- Services
- API clients
- Types
- Utils
- Existing feature modules

Pay special attention to existing implementations for:

- Tag selectors
- Tag-group selectors
- Member selectors
- Owner selectors
- Customer / group / department selectors
- Product selection / product binding
- Channel-code selection / channel-code binding
- Material selection
- Image upload / preview
- PDF upload / preview
- Mini-program configuration
- Broadcast audience selection
- Form validation
- List pagination
- Search and filters
- Action button groups
- Empty states
- Stats cards
- Detail display
- Permission checks
- Toast / message / modal / drawer behavior

If an implementation exists, reuse it or adapt it into a reusable abstraction. If
it cannot be reused directly, prefer making it generic instead of copying it.

### 1.3 API / 数据接入检查

Before adding an API call, search for:

- Existing services
- Existing API clients
- Existing request wrappers
- Existing type definitions
- Existing hooks
- Existing mock / fallback / error handling behavior
- Existing data structures for the same entity

Do not assemble one-off request logic inside page components. Do not create
multiple incompatible API wrappers for the same business entity.

## 2. 页面标题与说明：禁止重复

### 2.1 强制规则

A page may have only one page-level title and one page-level description.

If a top `PageHeader`, hero, banner, or breadcrumb header already displays the
page title and description, lower content cards must not repeat the same title
and description.

Wrong:

- Top: `内容雷达` plus `创建可追踪的链接、图片、PDF...`
- Lower card: `内容雷达` plus `创建可追踪的链接、图片、PDF...`

Correct:

- Top: `内容雷达` plus `创建可追踪的链接、图片、PDF...`
- Lower content starts directly with stats, list, search, actions, or concrete
  content, without repeating the page title.

Also correct:

- No top `PageHeader`
- The main card contains the only page title and description

Choose one pattern only.

### 2.2 卡片标题规则

Card titles may only describe the card's specific responsibility, for example:

- 数据概览
- 内容列表
- 最近访问
- 新建内容
- 基础信息
- 欢迎语与素材
- 入群标签
- 商品列表
- 渠道码列表

Card titles must not simply repeat the page title.

### 2.3 开发自检

Before submitting any page change, check:

- Are there two identical or near-identical `H1`, `H2`, or `CardTitle` values?
- Are there two identical or near-identical descriptions?
- Do `PageHeader` and `CardHeader` describe the same thing?
- Would a screenshot show "the top says it once, then the card says it again"?

If yes, remove one copy.

## 3. 信息架构：一级页面与二级页面职责分离

### 3.1 一级页面职责

A level-1 page should contain only:

- Page title and description
- Overview stats
- Search
- Filters
- List
- Pagination
- Batch actions
- Main action buttons, such as new, sync, or import
- Entrances to level-2 pages

A level-1 page should not contain full complex forms, complex previews, complex
uploads, complex binding configuration, or multi-step configuration.

### 3.2 二级页面职责

These responsibilities should generally live on level-2 pages:

- New/create
- Edit
- Detail
- Configuration
- Authorization
- Content preview
- Product binding
- Channel-code binding
- Tag binding
- PDF / image / attachment upload
- Multi-step forms
- Complex business-rule configuration
- Complex state transitions

Examples:

- `/admin/channel-codes`: list page
- `/admin/channel-codes/:id`: detail page
- `/admin/channel-codes/:id/edit`: edit page
- `/admin/content-radar`: list page
- `/admin/content-radar/new`: create page
- `/admin/content-radar/:id`: detail / data page
- `/admin/content-radar/:id/edit`: edit page

Concrete route names must follow the repository's existing style.

### 3.3 弹窗 / 抽屉使用边界

Modals and drawers are appropriate for:

- Delete confirmation
- Short rename flows
- Simple selection
- Simple status changes
- Short explanations
- Single-field or few-field edits

Modals and drawers are not appropriate for:

- Full create flows
- Complex edit flows
- Large forms
- Upload + preview + authorization + binding combined flows
- Features that require users to stay for repeated or long-running work

### 3.4 不允许“一页塞满所有功能”

Reconsider the information architecture when one page contains several of these
areas at once:

- Stats cards
- Create form
- Upload area
- Preview area
- Authorization settings
- Visit records
- Tag binding
- Product binding
- Channel-code binding
- List
- Detail

If a level-1 page has too many responsibilities, split it into list + level-2
detail/create/edit pages.

## 4. 复刻既有模块，而不是重新设计

Before building a new feature, find at least one existing repository module of
the same kind as a reference.

Reference priority:

1. Existing page in the same business domain
2. Existing admin page of the same type
3. Existing page with the same interaction pattern
4. Shared component or common pattern

Examples:

- For channel-code work, inspect the channel-code center first.
- For content-radar work, inspect channel-code center, product management, and
  material management patterns.
- For tag work, inspect enterprise tag management first.
- For product binding, inspect product management and existing product
  selection/share/binding logic.
- For member selection, inspect owner, employee, and WeCom member selector
  patterns.
- For broadcasts, inspect existing broadcast, audience, and customer-filtering
  logic.

Codex must state in its plan, implementation summary, or final response:

- Which existing files / pages / components were referenced
- Why those patterns were reused
- Whether any component was added
- If a component was added, why existing components were insufficient
- Whether there are follow-up abstraction opportunities

## 5. 组件复用与沉淀规则

### 5.1 禁止重复造轮子

If two features have the same or highly similar UI, interaction, or data
integration, extract or reuse a common component.

Do not:

- Build one tag selector for page A and another for page B
- Build one member selector for page A and another for page B
- Build one product binder for page A and another for page B
- Build one channel-code binder for page A and another for page B
- Build one upload preview for page A and another for page B
- Put large one-off business UI directly inside a page when it should be reused

### 5.2 新增组件判断标准

Add a component only when one of these is true:

- No similar component exists in the repository
- The existing component is tightly bound to one business flow and cannot be
  reasonably reused
- The new need has a clearly different data model or interaction model
- Refactoring the existing component is too risky for the current task scope

New components must:

- Live in the location expected by repository conventions
- Use clear generic names
- Avoid hard-coded single-page copy
- Avoid coupling pure UI components directly to business APIs
- Define props, loading, empty, error, disabled, and state behavior clearly
- Match the existing project UI style

### 5.3 推荐沉淀的标准组件类型

The repository should gradually converge on standard components such as:

- `PageHeader`
- `ManagementListPage`
- `ListToolbar`
- `SearchInput`
- `FilterBar`
- `StatsCards`
- `DataTable`
- `ActionButtonGroup`
- `EmptyState`
- `DetailSection`
- `FormSection`
- `EntitySelector`
- `TagSelector`
- `MemberSelector`
- `ProductSelector`
- `ChannelCodeSelector`
- `MaterialSelector`
- `UploadPreview`
- `PdfPreview`
- `ImagePreview`
- `BindingPanel`

If these already exist, record and reuse them. This skill does not require this
task to implement all of them, but future frontend work should move in this
direction.

## 6. 页面开发固定流程

Every frontend task must follow this order:

1. Read this skill.
2. Understand the business goal.
3. Classify the page type: list / create / edit / detail / config / preview /
   binding.
4. Search existing pages of the same kind.
5. Search reusable components.
6. Search existing API / hooks / services / types.
7. Design information architecture: what belongs on level-1 pages and what
   belongs on level-2 pages.
8. Check for duplicate titles and descriptions.
9. Prefer existing components and patterns.
10. Add a new generic component only after reusable implementations are ruled
    out.
11. Implement.
12. Self-check:
    - Duplicate title?
    - Overloaded level-1 page?
    - Existing pattern reused?
    - Duplicate wheel?
    - Duplicate API integration?
    - Route and page hierarchy consistent?
13. In the final response, state:
    - Referenced existing implementations
    - Reused components / hooks / services
    - Added components and why
    - Information architecture choice
    - Whether duplicate title/description issues were handled

## 7. Codex 输出要求

For every future frontend task, the final response must include this
`Frontend Skill Checklist`:

- 已读取 `frontend-development-skill.md`: 是 / 否
- 参考的已有页面:
- 参考的已有组件:
- 复用的 hooks / services / types:
- 是否新增组件:
- 新增组件原因:
- 一级 / 二级页面职责划分:
- 是否存在重复标题和说明:
- 是否存在重复造轮子风险:
- 自检结论:

If the task is not frontend-related, state: `Frontend Skill Checklist: 不适用`.

## 8. 本 Skill 的优先级

This skill is the first-priority frontend development standard for the AI-CRM
repository.

If user requests, old code habits, or temporary implementation habits conflict
with this skill, follow this skill. If a deviation is genuinely required, Codex
must state the reason and risk explicitly in its response.
