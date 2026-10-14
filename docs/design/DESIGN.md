# 识途 TravelSense · DESIGN.md

> 生成日期：2026-10-12 ｜ 设计师：颜好看
> 范围：计划书按块（event）增删改查 + 景区块展开官方攻略
> 三轴刻度：Variance = 4 / Motion = 3 / Density = 6
> 寄存器：**Product**（设计服务产品，标杆是"赢得熟悉感"，不是独特性）
> 平台轴：web（浅色主题）

---

## 0. 先说三个必须知道的现状事实（设计前实测，非推测）

这三条会直接改变实现方式，请先确认：

| # | 事实 | 证据 | 影响 |
|---|------|------|------|
| 1 | **`frontend/tokens.css` 目前不存在** | `find . -name "tokens.css"` 无结果；`styles/` 只有 `base.css`、`workspace.css`、`product.css` | 本文件是**新建**，不是扩展。它不是"改一点"，是从 4 处冲突里收敛出一份 |
| 2 | **有 4 个互相冲突的 `:root`，且 `product.css` 胜出** | `base.css:1`、`base.css:914`、`workspace.css:2`、`product.css:2`；`index.html` 加载顺序 base→workspace→product | 用户今天看到的强调色是 **蓝 `#3657b5`**，而它存放在名为 `--green` 的变量里。命名与语义相反 |
| 3 | **`tests/test_design_tokens.py` 与 `test_browser_regression.py` 目前不存在** | `ls tests \| grep -iE "token\|browser\|regression"` 无结果 | HANDOVER.md 描述的是**计划中的**守卫，不是已生效的。不要以为改坏会被拦住 |

另外三条实测结论：

- `ASSET_VERSIONS` 不在 `main.py:23`，而在 `app/api/security.py:18`，由 `app/api/page_assets.py` **解析 `index.html` 里所有 `/assets/` 链接并算 sha256[:12]**。所以新增样式表只要在 `index.html` 里声明即可自动纳入版本，**无需手工登记**。
- **CSP 是 `style-src 'self'`**（`security.py:33`）。因此 **Google Fonts / 任何 webfont CDN 在本项目里根本用不了**，字体只能用本地系统栈。这条直接否决了常规字体方案。
- 已有 3 处把符号当功能图标用：`☀`（`views/workspace.js`）、`☰`（`index.html`）、`✓`（`components/workbench.js`）。按 P0-1 需一并替换为 SVG。

---

## 1. Visual Theme & Atmosphere

**关键词**：可核查、克制、连续、手册感

**氛围**：一份"能被用户动手改"的旅行手册。整页保持中性、低饱和，让**时间轴**和**来源可信度**成为唯一被强调的信息；编辑能力只在需要时出现，不喧哗。

**对标品牌**

| 品牌 | 借鉴什么 | 明确不借鉴什么 |
|------|----------|----------------|
| **Linear** | 键盘可达、编辑态极克制、focus ring 清晰、150ms 收敛动效 | 深色主题、极客感 |
| **Notion** | block 模型：每块自带 hover 操作区、inline 编辑、disclosure 展开 | 无限自由的拖拽block（本项目用按钮，更可靠） |
| **Airbnb 行程 / Google Calendar** | 时间轴密度、时长条、可信度标记 | 大图流、营销感 |

**明确的反目标**：不做"AI 生成的漂亮落地页"。这是每天要被逐条核对的工具界面，密度和可信度优先于留白和装饰。

---

## 2. Color Palette & Roles

完整定义见 **`frontend/styles/tokens.css`**（唯一 `:root`）。本节只讲角色与用法。

### A1 · Identity（沿用今日实际生效的皮肤，视觉零跳变）

| Token | 值 | 角色 | 对比度（on `#fff`） |
|-------|----|------|---------------------|
| `--bg` | `#f6f7fa` | 页面底 | — |
| `--surface` / `--paper` | `#ffffff` | 块、卡片 | — |
| `--ink` | `#263249` | 主文本 | **12.85** 应 |
| `--fg-2` | `#3d4a63` | 次级文本 | 应 |
| `--muted` | `#5f6a7d` | 元数据 | **5.46** 应 |
| `--meta` | `#656f80` | 时间戳、占位 | **5.07** 应 |
| `--accent` | `#3657b5` | 强调（蓝） | **6.59** 应 |
| `--accent-on` | `#ffffff` | 强调底上的字 | **6.59** 应 |

### 两处被迫修正（有实测依据，非审美偏好）

| Token | 旧值 | 新值 | 原因 |
|-------|------|------|------|
| `--muted` | `#778195`（**3.92** 禁） | `#5f6a7d`（**5.46** 应） | 旧值不满足正文 4.5:1，块内元数据会大面积用到它 |
| `--line-strong` | 无（新增） | `#80899e`（**3.51** 应） | 现有 `--line` `#e5e8f0` 仅 **1.23**，作为**可交互块**的边界不满足 WCAG 1.4.11 的 3:1 |

`--line` **保留** `#e5e8f0`，但只允许做纯装饰分隔线，不得作为交互组件边界。

### 色板归属：两案未决，需产品拍板

架构师在 Phase 1 同步的色板取自 `base.css:1`（奶油底 + 绿）。**实测该块是死代码**：`index.html` 加载顺序为 `base.css` → `workspace.css` → `product.css`，四个 `:root` 同特异性，**最后加载者胜**，所以用户今天实际看到的是 `product.css:2` 的**蓝色**：

```
product.css:2  :root { --green:#3657b5; --ink:#263249; --muted:#778195; --line:#e5e8f0; --paper:#fff; --bg:#f6f7fa; }
product.css:11 body  { background:#f6f7fa; color:var(--ink); }
```

两案对比（均为实测值）：

| | **A 案（tokens.css 现采用）** | **B 案（架构师引用）** |
|---|---|---|
| 来源 | `product.css:2`（今日真实生效） | `base.css:1`（被覆盖，当前不生效） |
| 强调色 | 蓝 `#3657b5` | 绿 `#2c6652` |
| 底 / 纸 | `#f6f7fa` / `#fff` | `#f6f4ed` / `#fffdf8` |
| 采用后视觉变化 | **零跳变** | 全站改色（奶油底 + 绿） |
| `--muted` 现状 | `#778195` **3.92 不合格** | `#738078` **4.06 不合格** |
| `--line` 现状 | `#e5e8f0` **1.23 不合格** | `#dce2d7` **1.30 不合格** |

**关键结论：无论选哪案，上面"两处被迫修正"都强制生效** —— 两案的 `--muted` 都不到 4.5:1、两案的 `--line` 都不到 3:1。色板是产品选择，对比度修复是硬要求。

`tokens.css` 当前按 **A 案**发货（零跳变、风险最低）。若产品选 B 案，把 A1 段整体替换为：

```css
  --bg: #f6f4ed;  --surface: #fffdf8;  --paper: #fffdf8;  --surface-2: #f3f1e8;
  --ink: #203d35; --fg-2: #33544a;     --muted: #5f6b63;  --meta: #566259;
  --accent: #2c6652; --accent-on: #ffffff;
  --accent-hover: #245544; --accent-active: #1d4436; --accent-soft: #eaf1ec;
  --line: #dce2d7; --line-strong: #7f887e; --soft: #e8eee4;
```

（B 案修正后：`--muted` 5.48、`--line-strong` 3.61、`--accent` 6.6、白字在 accent 上 6.71 —— 均达标。）

### 兼容策略（关键，决定改造成本）

`--green: var(--accent, #3657b5)` —— 现有 **45 处 `var(--green)`** 一行不动，自动变成蓝色（也就是它们今天已经渲染出的颜色，视觉无变化）。`--green` 标记为 **deprecated**，新代码一律写 `--accent`。

### A2 · Semantic

`--success #1c6b4f` / `--warn #7a5200` / `--danger #b3261e`，各配 `-soft` 底（文字在 soft 底上均 ≥ 5.7 应）。

### C · Extension — 块种类色

spot / transport / meal / free / rest / route 各一对 `(-fg, -soft)`，文字在自己 tint 上最低 **5.76** 应。

> 注意 **种类绝不靠颜色单独传达**（WCAG 1.4.1）。每个块同时带 **16px SVG 图标 + 可见文字标签**。颜色只是辅助扫描。

### C · Extension — 锁定态

`--surface-locked #f1f3f6` · `--border-locked #8a95a8`（**虚线**）· `--fg-locked #5b6678`（在锁定底上 **5.22** 应）

### 每屏强调色规则

`--accent` 在一屏内可见使用 **≤ 2 处**：主 CTA + 当前选中块。块的种类色不占用这个额度。

---

## 3. Typography

**字体（受 CSP 限制，只能系统栈）**

```
--font-display / --font-body:
  "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", system-ui, sans-serif
--font-mono: "Cascadia Mono", "Consolas", "SFMono-Regular", monospace
```

> Google Fonts / Inter / Noto Sans SC **全部不可用**：CSP `style-src 'self'` 会阻断 `@import`。这是硬约束，不是选择。

**字号**（8 级，下限 12px）：`12 / 13 / 14 / 16 / 18 / 20 / 24 / 32`

时间列、时长、金额统一 `font-variant-numeric: tabular-nums`（`base.css` 已在用），保证数字纵向对齐。

**字重**：400 正文 / 500 小标题与按钮 / 600 块标题
**行高**：正文 1.65 · 标题 1.3 ｜ **字距**：正文 0 · 标题 -0.01em

---

## 4. Components

### 4.1 块（event block）— 信息架构

一个块 = 一条可独立操作的行程条目。结构固定为**四行**，不因 kind 增删行（保证扫描节奏一致）：

```
┌──────────────────────────────────────────────────┐
│ 09:00   ① [图标] 名称                  ② 时长徽章 │   ← 行1：时间列 + 标题
│ ─────   ③ 可信度徽章  ④ 来源链接                  │   ← 行2：可信度
│         ⑤ 备注 / 只读测算值                       │   ← 行3：详情
│         ⑥ [编辑][删除][↑][↓]  ⌄ 官方攻略          │   ← 行4：操作区
└──────────────────────────────────────────────────┘
```

| # | 元素 | 规则 |
|---|------|------|
| ① | 时间列 | `09:00 — 11:30`，tabular-nums，12px 起，`--meta`。左侧 2px 竖线是**连续时间轴脊**，不是种类色条 |
| ② | 时长徽章 | `90 分钟`。spot 用 duration；route 用 `mode + minutes + distance` |
| ③ | 可信度徽章 | 三态：**已核实**（success）/ **查询参考**（accent）/ **待核实**（warn）。复用现有 `.confidence-badge` |
| ④ | 来源 | 复用现有 `src()` 的 `<details class="source">`，不改 |
| ⑤ | 备注 | 可编辑字段与**只读测算值必须视觉分离**：只读值用 `--muted` + `测算值` 文字标签 + 无输入框 |
| ⑥ | 操作区 | 见 4.2 |

**不同 kind 的差异**（只差异"有什么"，不差异"排版"）

**可操作矩阵**（PRD v3.0 终版）

**移动规则**：只有**可编辑块**（`spot` / `rest` / `free`）可移动；只读块一律不可移动 —— 单一规则，避免"部分能改部分不能改、用户无法预测"的竞品通病。

| kind | 图标 | 编辑 | 删除 | 攻略 | 不可操作时显示的**原因文案** |
|------|------|------|------|------|------------------------------|
| `spot` | map-pin | **duration 可改**（MVP 只改时长；`note` 编辑降级 P2） | **可**（MVP 内唯一可删类型） | **有** | — |
| `rest` | clock | 可 | 不可（MVP） | — | **没有 `candidate_id`，重新生成后无法稳定定位** |
| `free` | plus | 可 | 不可（MVP） | — | 同上（**能加、能改，但不能删** —— 见 §4.8） |
| `meal` | utensils | 只读 | 不可 | — | **餐次由你的餐厅选择与用餐时段推算；如需调整，请改餐次安排** |
| `route` | route | 只读 | 不可 | — | **由前后景点派生的已查询事实（带查询时间），不可改写** |
| `unknown_route` | route | 只读 | 不可 | — | **尚未查到通行数据，确认相邻安排后自动补算** |
| `transport` | route | 只读 | 不可 | — | **固定班次，时间以承运方时刻为准** |
| `arrival` | log-in | 只读 | 不可 | — | **抵达锚点，当天行程由此起算** |
| `transfer_plan` | route | 只读 | 不可 | — | **接驳安排由班次与住宿共同决定** |
| `spot_continue` | map-pin | 只读 | 不可 | 随父块（见 §4.9） | **同一景区的延续时段，随前一段结束** |

> **`meal` 收为只读**（架构裁定）：时刻由 `meal_choices` + 餐次窗口 + 游玩收尾共同决定，是**派生值**；块级改会让 plan 与 `w["meal_choices"]` 失同步。"我不想吃这顿"有正确路径 —— 现有的 `meal_choice{mode:"remove"}`。
>
> **`route` / `unknown_route` 收为只读**：它们是已查询的派生事实（带 `source.queried_at`），允许改写等于允许篡改已核实数据，违反项目"不补造数据"铁律。
>
> **`free` 的"能加、能改、不能删"是有意的不对称**，不是 bug，必须在 UI 上讲清楚（§4.8）。

### 4.2 可编辑 / 不可编辑的视觉区分（**不依赖颜色单独传达**）

四种手段叠加，任一单独失效仍可辨识：

| 手段 | 可编辑块 | 锁定块 |
|------|----------|--------|
| **边框形状** | 实线 1px `--line-strong` | **虚线** 1px `--border-locked` |
| **底色** | `--surface` | `--surface-locked` |
| **图标** | 无锁 | **16px 锁图标** + 指向原因文案的 `aria-describedby` |
| **操作区** | 渲染编辑/删除/移动按钮 | **完全不渲染按钮**，改为一行原因文案 |

> 为什么锁定块不渲染 disabled 按钮：disabled 按钮会让用户以为"以后能点"，产生困惑。直接不渲染 + 给锁图标和**可读的原因文案**，认知负荷更低，也更诚实 —— 这正是 TripIt / Sygic 被吐槽"部分能改部分不能改、用户无法预测"的解药。

**原因文案的位置与样式**：放在操作区所在的那一行（原地替换按钮组），`--fg-locked` 色、13px，锁图标 16px 前置。它必须**占据原本操作区的位置**，让用户一眼看到"这里本来可以有按钮，但因为这个原因没有"。

### 4.3 三档分离：事实 / 建议 / 未知（项目铁律）

同一个块内部，三类信息必须视觉可分：

| 档 | 内容 | 表现 |
|----|------|------|
| **事实** | POI 名称、位置、evidence 原文与来源 | 只读态，无输入框；来源用 `external-link` 图标 + 可点链接 |
| **建议** | duration / start / end / note | 可编辑；**用户改过之后打"用户已设定"标记** |
| **未知** | evidence 为空、开放时间未核实 | 显式"暂无官方资料，需自行核实"，`--warn-soft` 底 |

**"用户已设定"标记态**（`user-set`）：字段被用户改过之后，值旁挂一个 `shield-check` 16px 徽标 + `title`/`aria-label` "用户已设定，重新生成时会保留"。视觉上**不用强调色**（避免和 CTA 抢），用 `--fg-2` + 细边框徽章。这个标记让用户能预期"下次重新生成时哪些会保留"。

### 4.4 操作区与按钮

- 图标按钮 **44×44px** 触摸区（图标本身 20px），间距 ≥ 8px
- 操作区默认 `opacity: .55`，**`:hover` 与 `:focus-within` 均升到 1** —— 键盘用户必须能看到
- 窄屏（<640px）操作区**常驻可见**（无 hover），见 §8
- 每个按钮必须有 `aria-label`（图标按钮无可见文字）

### 4.5 删除：inline 撤销，**不做二次确认弹窗**

依据 PRD（Linear 的撤销优先 + TripIt"误合并丢失备注"的差评教训）：

1. 点击删除 → **立即移除该节点**（乐观更新，< 100ms 可见）
2. 在**该块原来的位置**插入一条 inline 撤销条：`已删除〈名称〉 · 撤销`（`rotate-ccw` 图标 + `撤销` 文字按钮）
3. 同步请求在后台发出；失败则回滚并给出块内错误
4. 撤销条 **8 秒后自动消失**，或用户执行下一个操作时消失

> 为什么不是顶部 toast：用户点完删除，视线还在刚才那一行，顶部 toast 看不见。撤销入口必须**在原位附近**。
> 为什么不用"确定要删除吗"弹窗：既然有可靠的撤销，弹窗就是纯粹的摩擦。

### 4.6 五态覆盖

| 状态 | 表现 |
|------|------|
| Loading | 保存中的块显示 inline spinner，**块保持原位不重排** |
| Empty | 攻略展开为空 → 见 §5；删除到当天无块 → "这一天还没有安排，添加第一个行程" |
| Error | 保存失败 → 块内 inline 红字 + **重试按钮**，**不回滚用户输入** |
| Populated | 正常 |
| Edge | 超长名称 `text-overflow: ellipsis` 两行截断；`24:00` 跨日边界；单日 20+ 块时操作区仍可达 |

### 4.7 级联变更：告知级与阻断级

时间是链式累加的（`daily_schedule.py:719`），改一个块后面全漂移。产品策略是**级联可见**，分两级，视觉权重必须区分：

| 级别 | 触发条件 | 形态 | 是否阻断 |
|------|----------|------|----------|
| **告知级** | 正常重算 | 被改块下方 inline 细条：`后续 3 项提前 45 分钟，当日 17:40 结束` | 否，不打断 |
| **阻断级** | 超出 day_end / 违反返程接驳 / 与固定班次冲突 | 醒目提醒条 + 两个按钮 | 是，需显式确认才写入 |

**告知级样式**：`--surface-2` 底、13px、`--fg-2` 文字、左侧 2px `--accent` 竖线（是时间轴脊的延续，**不是**装饰性彩色强调条）。出现时 200ms 淡入，不移动下方内容（用 `max-height` 过渡而非插入节点导致的重排 —— 或直接预留空间）。

**阻断级样式**：`--warn-soft` 底 + `alert-triangle` 16px 图标 + `--warn` 文字（对比度 6.25）。两个按钮：
- 「仍然保留这一安排」（主按钮，执行写入）
- 「调整安排」（次按钮，放弃本次修改）

**文案口径沿用系统现有**（`plan_output.py:69-74`）：

> 当日按当前游览建议计算约在 19:20 结束，超过每日结束时间 18:30。可调整安排，也可继续并保留这一提醒；结束时间设置未被自动修改。

> **禁用词**：`操作失败`、`无法保存`、`错误`。这不是错误，是提醒。阻断级要"够醒目但不能像报错" —— 用 warn 语义而非 danger 语义，主按钮是"继续"而不是"重试"。

---

## 5. 攻略展开：形态选型与空态

### 选型：**inline `<details>` 折叠**（否决抽屉 / 弹层 / 侧栏）

| 方案 | 结论 | 理由 |
|------|------|------|
| **inline `<details>`** | **选定** | 与项目现有 `src()`、`book-section`、`dayMapHTML` 的 `<details>` 心智完全一致；原生键盘可达（`summary` 可聚焦，Enter/Space 切换）；无 JS 状态机；零依赖 |
| 抽屉 Drawer | 禁 | 会遮挡左侧时间轴，用户失去"这块在哪一天"的上下文；移动端还要额外遮罩层 |
| 弹层 Modal | 禁 | 打断"逐日连续浏览"的阅读流；需要焦点陷阱与焦点归还，本项目无框架，成本高 |
| 侧栏 Sidebar | 禁 | 计划书已是宽表格布局（1560px），再开侧栏挤压时间轴 |

### 默认折叠（PRD 硬要求）

`evidence` 区**默认折叠**，展开才显示。依据 PRD 引用的 Wanderlog 差评：

> "我不想看位置下面那一堆介绍文案，我只想加进行程说明我已经知道它是什么了。这看起来太乱了。"

两条硬性推论：

- **展开不改变块的起止时刻**，也不改变块的高度占位（展开内容在块内向下延伸，不挤走相邻块的时间轴位置）
- Wanderlog 招人烦是因为它堆的是营销废话；我们的 `evidence` 是**带来源的检索原文**。差别必须体现在视觉上：**来源标识要显式，不与正文混排** —— 每条 evidence 用独立行 + `external-link` 图标 + 来源名 + 采集时间，与正文之间用 1px `--line` 分隔

### 渲染字段（契约 `app/core/contracts.py:174`）

每条 evidence 为 `{ id, city, title, url, text, fetched_at, scope | date_scope }`。渲染时**逐字段降级**，缺失就显示降级文案，**不允许推断或编造**：

```
[external-link] {title}
   {text}
   来源：{scope} · 采集 {fetched_at} · 适用日期需核实
```

| 字段缺失 | 降级文案 |
|----------|----------|
| `title` | `未命名资料` |
| `url` | 不渲染链接，只留文本 |
| `text` | 只显示标题行 |
| `fetched_at` | `采集时间未标注` |
| `scope` / `date_scope` | **来源未标注** |

### 空态（**绝不留白**，且是主路径不是边角）

`evidence` 为空数组时，**必须**渲染：

```
[alert-triangle 图标] 暂无官方资料，需自行核实
  系统没有检索到该景区的官方页面。出发前请自行核实开放时间、门票与预约要求。
```

- 带 `alert-triangle` 图标 + `--warn-soft` 底 + `--warn` 文字（**6.25** 应）
- 措辞落在 **"未检索到"** 而不是 **"没有规定"** —— 前者是系统状态，后者是对事实的断言，会误导
- **绝不允许用任何模型生成内容替代空 evidence**
- 文案要说明"为什么空"和"下一步做什么"，**禁止**出现"暂无数据"这类空洞占位

### 入口出现条件（避免永远空的入口）

`evidence` **只挂在 `kind === "spot"` 的事件上**（`app/planning/daily_schedule.py:716` `add_visit` 写入）。因此：

- 应 仅当 `Array.isArray(event.evidence)` 时才渲染攻略入口
- 禁 不要在 transport / rest / free 块上渲染一个永远为空的入口

（`plan_review.py:31` 只是在发给模型的**审查载荷**里剔除 `evidence` 以省 token，**保存的计划里仍然有**，前端可用。）

### 【关键】导出与打印的陷阱

| 通道 | 现状 | 处理 |
|------|------|------|
| **服务端 Markdown 导出** | `report.py:197-200` 每个 guide 只输出**一行链接** | 应 天然安全，展开与否完全不影响 |
| **浏览器打印 / PDF** | **注意 有 bug 风险**：`views/plan.js:118` 的 `beforeprint` 会强制展开 `.book details:not(.day-map)` | **必须**改成 `:not(.day-map):not(.block-guides)`，并在打印 CSS 加 `@media print { .block-guides { display: none } }` |

不处理的话，用户打印 PDF 时会把整段攻略灌进去 —— 与"展开内容不进导出"的需求直接冲突。

---

## 6. 增删改查交互：无框架下的局部更新方案

### 问题

`views/workspace.js:227`：`$("#content").innerHTML = prerequisitesHTML() + content()`
整块重绘 → 编辑中的输入框会掉焦点、闪烁、丢内容。

### 方案：三层策略

**第 1 层 · 事件委托（项目已有模式，直接沿用）**

监听器挂在 `document` 上（`app.js:33`、`plan.js:107` 已经是这个写法），用 `[data-block-action]` + `[data-block-id]` 派发。**节点被 innerHTML 换掉也不会失效**，所以不需要在每次重绘后重新绑定。

**第 2 层 · 编辑期间根本不触发 `render()`（关键）**

| 动作 | 做法 | 是否重绘 |
|------|------|----------|
| 点「编辑」 | 记 `blockEditingId = id`；**只替换这一个节点**：`node.outerHTML = blockEditFormHTML(block)`；随后 `.focus()` | 禁 不调 render |
| 输入中 | 只写模块级 draft（`core/state.js`），**不重绘** | 禁 |
| 保存 | draft → API → 成功后 `render()`（此时焦点已离开输入框） | 应 |
| 取消 | `blockEditingId = null`，重绘该节点回展示态 | 禁 局部 |

> 效果：**打字期间零重绘 → 零掉焦点、零闪烁**。这是本方案的核心，改动量也最小。

**第 3 层 · 服务端变更用定向 DOM 手术，乐观更新**

| 动作 | 做法 |
|------|------|
| 删除 | 先 `node.remove()`（立即可见，无白屏等待）→ 调 API → 失败则 `render()` + 块内错误提示 |
| 上移/下移 | `insertBefore` 交换两个节点 → 调 API → 成功后仅打 `just-updated` 高亮 |
| 新增 | 目标位置 `insertAdjacentHTML` → 调 API → 成功后高亮 |

`just-updated` 已有现成实现（`core/api.js:51`、`components/workbench.js:218` + `base.css:272`），直接复用。

### `render()` 的焦点与展开态保全（必须做）

任何 `action()` 都会整页重绘，而项目里已有两个同类先例可沿用：
- `switchTab(next, focusId)` 已做滚动位置恢复（`core/api.js:29`）
- `beforeprint/afterprint` 已做 `details` 开合快照（`views/plan.js:115-125`）

照此在 `renderWorkspace()` 加三步：

1. **快照**：`#content` 的 `scrollTop`、所有 `details` 的 `open` 状态、`document.activeElement` 的 `data-focus-key`
2. **重绘**
3. **恢复**：滚回原位、还原 `open`、把焦点还给同一 `data-focus-key` 的元素

### 明确不做

**HTML5 拖拽排序**：在 innerHTML 整块重绘下，拖动中的节点随时会被销毁，且移动端与键盘都不可靠。改为 **↑/↓ 按钮 + 键盘 `Alt+↑/↓`**，端到端更稳。需求优先级是"真实可用"，可靠性 > 炫技。

---

## 7. 图标系统

### 选型：**Lucide**（ISC 许可，24×24 网格，stroke 2，round cap/join，统一描边）

与架构师锁定的选型**一致**。与项目现存的 `timeline.js:161`、`candidates.js:13` 手写 inline SVG 同为 stroke 描边风格，无需视觉迁移。

### 无构建引入方式：**`frontend/core/icons.js` 内联 path 常量表**

架构师已锁定交付形态，我采纳（比我原先提的 index.html sprite 更适合本项目 —— views 本来就返回 HTML 字符串，`icon()` 返回字符串可直接拼进 `innerHTML`，且可单测）：

```js
// frontend/core/icons.js —— 唯一出口
icon(name, { size = 20, className = "", label = "" })
// label 为空 → aria-hidden="true" + focusable="false"
// label 非空 → role="img" + <title>{label}</title>
```

**给 `icon()` 的视觉规格（请照此实现，否则描边风格会散）**

| 属性 | 值 |
|------|----|
| `viewBox` | `0 0 24 24` |
| `fill` | `none` |
| `stroke` | `currentColor`（**禁止写死颜色**） |
| `stroke-width` | `2` |
| `stroke-linecap` / `linejoin` | `round` |
| `width`/`height` | 由 `size` 传入，16 / 20 / 24 |
| `focusable` | `false` |

尺寸用法：**16px** 行内与徽标 / **20px** 按钮内 / **24px** 独立图标按钮。全项目统一，不混。

禁止任何其他文件硬写 `<svg>` 或 emoji。

### 图标清单（20 个，正好压在架构师给的上限内）

**块编辑主用（14，来自架构师清单）**

| 图标 | 用途 |
|------|------|
| `square-pen` | 编辑块 |
| `grip-vertical` | 拖动手柄（六点，progressive disclosure） |
| `arrow-up` / `arrow-down` | 上移 / 下移 |
| `trash-2` | 删除 |
| `plus` | 新增块 |
| `book-open` | 展开官方攻略 |
| `chevron-down` / `chevron-up` | 折叠 / 收起 |
| `clock` | 时长 |
| `x` | 关闭 |
| `rotate-ccw` | 撤销（inline 撤销条） |
| `alert-triangle` | 阻断级提醒 / 空态 |
| `external-link` | 来源链接 |

**我补充申请（6，都是可编辑性表达与标记态的必需品）**

| 图标 | 用途 | 为什么必须有 |
|------|------|--------------|
| `lock` | 锁定块标识 | 可编辑/不可编辑区分的**三手段之一**，没有它只剩边框和文案 |
| `map-pin` | spot 块种类图标 | 块种类不能靠颜色单独传达（WCAG 1.4.1） |
| `utensils` | meal 块种类图标 | 同上 |
| `route` | route / transport 块种类图标 | 同上 |
| `shield-check` | 「用户已设定」标记 | PRD 铁律：区分系统建议与用户设定 |
| `check` | 保存成功反馈 | 轻量确认态 |

**存量符号替换（3，独立工作流，不计入上面 20）**

`sun`（替换 `☀`，`views/workspace.js`）、`menu`（替换 `☰`，`index.html`）、`check`（替换 `✓`，`components/workbench.js`）。

> 注：`check` 同时出现在补充清单与存量替换里，只需 vendor 一份。

**为什么 path 常量表是无构建下的可行解**

| 方案 | 结论 |
|------|------|
| npm 包（lucide / feather） | 禁 无构建步骤无法 tree-shake；CSP `script-src 'self'` 也阻断 CDN |
| 外部 `.svg` + `<img src>` | 禁 无法继承 `currentColor`，且每个图标一个请求 |
| **`<symbol>` sprite 内联进 index.html** | 可用，但需维护一份与 JS 分离的 DOM 依赖 |
| **`icons.js` 内联 path 常量表** | **选定** 零构建、零网络、返回 HTML 字符串可直接拼进 `innerHTML`、可单测、单一出口 |

**尺寸**：16px 行内 / 20px 按钮内 / 24px 独立。**全项目统一 `stroke-width="2"`、`fill="none"`。**

**绝对禁令**：任何 emoji 不得作为功能图标（正则 `[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]` 扫描须为零）。

---

## 8. Layout & Spacing

- **间距**：4px 网格，`--space-1..12`（4/8/12/16/20/24/32/40/48）。块内 padding `--space-4`(16px)，块间距 `--space-2`(8px)（行程密度 6，不能太松）
- **圆角**：块 `--radius-md`(8px)；徽章 `--radius-sm`(4px)。**上限 12px，禁止 ≥24px**
- **时间列**：固定 `78px`（沿用 `base.css:1352`），`tabular-nums`
- **容器**：`--container-max: 1560px`
- **断点**：`<640` 单列（时间列改为行内前置）／`640–1024` ／`>1024` 完整

### 窄屏（< 640px）— 编辑入口不得被遮挡

执行期的用户是**在手机上看日程的**，这是主用场景不是降级场景。

| 项 | 桌面 | 窄屏 |
|----|------|------|
| 操作区 | `opacity:.55`，`:hover`/`:focus-within` 升到 1 | **常驻可见**（无 hover 可用），不再做透明度变化 |
| 手柄 `grip-vertical` | hover 才出现 | 常驻，位于块左侧时间轴脊旁 |
| 布局 | 时间列 78px + 内容 | **单列**：时间移到块标题行内前置（`09:00 — 11:30`），释放横向空间 |
| 触摸目标 | 可 32px（有 hover 辅助） | **强制 44×44px**，间距 ≥ 8px |
| 编辑表单 | inline 展开 | inline 展开，**输入框 `font-size ≥ 16px`**（< 16px 会触发 iOS 自动缩放） |
| 撤销条 | 原位 | 原位，且**不得被底部固定元素遮挡** |

**不得**：把操作区收进"⋯"溢出菜单再靠 hover 触发 —— 触屏没有 hover，等于功能不可达。窄屏宁可常驻占位，也不要藏。

---

## 9. Depth & Elevation

- 块**默认无阴影**，靠 1px 边框区分（`--elev-ring`）
- 仅**编辑中**的块升到 `--elev-raised` + `--accent` 边框，表示"浮起"
- 弹层 `--elev-overlay`；`z-index`：dropdown 1000 / sticky 1100 / modal 1200 / toast 1300
- **禁止**装饰性毛玻璃；**禁止**幽灵卡片（`1px 边框 + blur ≥16px 阴影` 同时出现）

---

## 10. 动效

| 场景 | 时长 | 缓动 |
|------|------|------|
| 按钮按下 | 80ms | `--ease-standard` |
| hover / 展开 | 150ms | `--ease-standard` |
| 块展开、toast | 200–300ms | `--ease-standard` |

- `--ease-standard: cubic-bezier(0.2, 0, 0, 1)`，**禁止弹跳缓动** `cubic-bezier(0.68,-0.55,0.265,1.55)`
- 必带 `prefers-reduced-motion` 降级（已写进 `tokens.css`）
- 动效必须传达含义（展开/保存成功），**禁止**每个 section 都来一遍相同的淡入

---

## 11. Do's & Don'ts

**应 应该**

1. 所有颜色走 `var()`，且带兜底 `var(--x, #fallback)`
2. 每个图标按钮有 `aria-label`，操作区 `focus-within` 可见
3. 攻略空态必须给出"为什么空 + 下一步"
4. 编辑期间不触发全量 `render()`
5. 删除走 **inline 撤销**（原位、8 秒），**不用二次确认弹窗**
6. 数字用 `tabular-nums`

**禁 不应该**

1. 禁 emoji 或 `☀ ☰ ✓` 当功能图标
2. 禁 紫色→粉色渐变 / Indigo→Pink 组合
3. 禁 硬编码颜色（组件 CSS 里出现裸 hex）
4. 禁 卡片 `border-left: 3px solid` 彩色强调条
5. 禁 圆角 ≥ 24px
6. 禁 弹跳缓动
7. 禁 靠颜色单独传达"可编辑/锁定"或"块种类"
8. 禁 空态留白或写"暂无数据"
9. 禁 每屏超过 2 处强调色
10. 禁 引入需要打包的方案（React/Vue/CSS-in-JS/Google Fonts）

---

## 12. Responsive & Accessibility

- **触摸目标** ≥ 44×44px，间距 ≥ 8px（WCAG 2.5.5）
- **对比度**：正文 ≥ 4.5:1 · 交互边界 ≥ 3:1（`--line-strong` 已达标）
- **键盘**：`Tab` 遍历块与操作；`Alt+↑/↓` 移动块；`Esc` 退出编辑；所有交互有 `:focus-visible` 环
- **屏幕阅读器**：块列表用 `<ol>` + `<li>`；锁定块 `aria-describedby`；攻略展开用 `<details>/<summary>`（原生语义，无需 ARIA 补）
- **5 态**：Loading / Empty / Error / Populated / Edge 全覆盖（见 §4.6）

---

## 13. Agent Implementation Guide

### 落地步骤（按依赖顺序）

0. **先拍板色板 A / B**（§2）。`tokens.css` 现按 A 案发货（零跳变）；选 B 案则替换 A1 段（已给可直接粘贴的代码块）
1. **新建** `frontend/styles/tokens.css`（**已完成**，本仓库内）
2. **在 `index.html` 首个 `<link>` 之前插入**
   `<link rel="stylesheet" href="/assets/styles/tokens.css" />`
   > 注意 必须先有文件再加 link：`page_assets.py` 会对每个声明的资源 `read_bytes()`，文件缺失会导致启动崩溃
3. **删除** `base.css:1`、`base.css:914`、`workspace.css:2`、`product.css:2` 四个 `:root` 块（只删 `:root{}` 本身，其内部注释可移到文件头）
   > 这是让 `test_design_tokens.py` 的"唯一 `:root`"守卫通过的**必要**步骤
4. 新增块视图函数 `views/plan.js` + 块样式（可放 `product.css`）
5. 事件委托 + 编辑态局部更新（§6）
6. 攻略 `<details>` + 空态（§5）
7. **`frontend/core/icons.js`** 单一出口 `icon(name,{size,className,label})`，vendor 20 个 Lucide path（§7）；视觉属性按 §7 表格写死在出口里，调用方不许覆盖
8. 存量符号 `☀ ☰ ✓` 替换为 `sun`/`menu`/`check`（独立工作流，不阻塞块编辑）

### 已知坑

| 坑 | 说明 |
|----|------|
| **改完前端必须重启服务** | `ASSET_VERSIONS` 是**启动时**算的 sha256，不重启浏览器拿旧缓存 |
| **打印会漏出攻略** | `plan.js:118` 的 `beforeprint` 强制展开所有 `details`，必须排除 `.block-guides`（§5） |
| **`--green` 其实是蓝色** | 迁移期别被名字骗了，新代码用 `--accent` |
| **`--surface-2` 从未定义** | `workspace.css:2034` 用了 `var(--surface-2, #f7f8fa)`；兜底救了它，现已在 tokens 内正式定义 |
| **Google Fonts 不可用** | CSP `style-src 'self'` |
| **`--muted` 变深了** | 从 `#778195` → `#5f6a7d`，是修 WCAG 失败，70 处引用会略微调深 |

### 验收自检

```bash
# 唯一 :root；变量全部有定义；裸 var() 有兜底
pytest tests/test_design_tokens.py      # 需先按步骤3清理
pytest tests/test_browser_regression.py # 需先建立（当前不存在）
# P0 扫描（须为零）
grep -oP "[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]" frontend/**/*.js frontend/index.html
```
