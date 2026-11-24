# Cloud9 x JetBrains: Sky's The Limit Hackathon 2026 — 官方规则与技术简报

> **采集核实时间**：2026-11-23 23:28 (UTC+8)  
> **赛事主页**：https://cloud9.devpost.com/  
> **规则/细节来源**：`submission-specifics`、`resources`、`details/dates`、`rules` 与官方 GRID Starter 仓库 [`cloud9esports/stl-hackathon-2026-grid-starter`](https://github.com/cloud9esports/stl-hackathon-2026-grid-starter)

---

## 一、赛事总览、奖金池与关键时间节点

- **总奖金池**：**$25,000 USD 现金** + 3 套 GDC 2027 门票与差旅（每赛道第 1 名各 1 人）+ $100 Cloud9 Store 礼品卡 + JetBrains All Products Pack（1 年个人订阅）
- **赛道奖项分配**（同一项目最多获 **1 个主赛道奖 + 1 个 Bonus 奖**）：
  - **Category 1 (VAL/GC)**：Best **$6,000**（含 GDC 2027 门票+机酒） / Runner-up **$2,000**
  - **Category 2 (LoL)**：Best **$6,000**（含 GDC 2027 门票+机酒） / Runner-up **$2,000**
  - **Category 3 (Event Mini Game)**：Best **$6,000**（含 GDC 2027 门票+机酒） / Runner-up **$2,000**
  - **Bonus Prize (Best AI-Powered Workflow Story)**：**$1,000**（1 名）
- **参赛者福利**：每位注册参赛者可领 1 个 All Products Pack 激活码和 1 个 AI Ultimate（2 个月）激活码（需配合 JetBrains IDE / All Products Pack / 试用版 / EAP 激活，学生版无效，发完即止）。
- **关键赛程**（注意：Devpost `details/dates` 与 `rules` 的 PT/GMT+8 显示存在 1 小时/夏令时边界差异，提交务必按早者倒计时）：
  - **提交窗口**：`2026-11-17 11:00 PT`（Devpost 日程页显示 `2026-11-18 03:00 GMT+8`）– **`2027-01-12 11:00 PT`**（Devpost 日程页显示 **`2027-01-13 03:00 GMT+8`**）
  - **评审周期**：`2027-01-27 15:00 PT` – `2027-02-03 15:00 PT`（`2027-01-28 07:00 GMT+8` – `2027-02-04 07:00 GMT+8`）
  - **结果公布**：`2027-02-08 12:00 PT`（`2027-02-09 04:00 GMT+8`）附近

---

## 二、三大赛道官方蓝图与必备功能清单

### 1. Category 2 (LoL): Macro Scouting & Draft Management System（重点）
- **官方定位**：为 Cloud9 LoL 教练组打造的竞技级平台，消除电子表格混乱（eliminate spreadsheet chaos）、加速赛前准备并提升 BP（Draft）与宏观战术准备效率。
- **两大官方推荐蓝图**（二选一或融合，亦可自研教练分析方案）：
  1. **Automated Macro Scouting Tool（自动化宏观侦察工具）**
  2. **Modular Draft Organizer（模块化 BP 管理器，支持 Fearless Draft 无畏征召规则）**
- **核心能力清单**：
  - **Draft Tendency Analysis & Recommendations**：分析历史数据（英雄池、版本 Patch、近期比赛记录），识别对手 Pick/Ban 倾向并推荐针对性的 C9 最优 BP 策略。
  - **Modular Draft Organizer (Fearless Draft Ready)**：模拟并追踪 Pick/Ban 阶段，完整支持当前 **Fearless Draft（全局 BP / 无畏征召）** 规则，在 Bo5 的 Game 3 / Game 4 / Game 5 自动扣减已选用英雄并追踪缩水后的英雄池。
  - **Supporting Macro Context**：分析对手近期比赛的宏观模式（如打野路线倾向 `jungle pathing`、前期资源/巢虫/小龙/先锋布局 `early-game objective setups`），为 BP 洞察提供上下文支撑。
- **加分进阶方向（"Next Level"）**：
  - **数据驱动的 "How to Win" 对策**：不止罗列统计，而是生成可执行的反制建议（例如：*"对手 X 在 Game 1 有 70% 概率选猪妹；若我们 Ban 掉猪妹，他们在 Fearless Draft Game 2 的胜率下降 15%，建议前期 Ban 猪妹"*）。
  - **Live Draft Winrate Impact（实时 BP 胜率影响）**：随当前 BP 状态推进，实时展示预测胜率变化，直观体现不同候选 Pick/Ban 对胜率的边际影响。
- **评委核心检验问题**：
  - *"该对手最常重复出现的 Pick/Ban 倾向是什么？"*
  - *"在 Fearless Draft 的 Game 3、4 或 5 场景中，对手的 BP 策略如何变化？"*

### 2. Category 1 (VAL/GC): VALORANT Tactical Scouting, Utility Placement, & Operator Profiler（重点）
- **官方定位**：为 Cloud9 VALORANT 与 Game Changers（GC）教练组及选手打造的可视化战术侦察工具，减少人工拉片（VOD review），无需技术背景即可读懂。
- **两大官方推荐蓝图**（二选一或融合）：
  1. **Utility Placement & Ability Analysis Engine（技能与道具落点分析引擎）**
  2. **Operator Tendency & Sniper Profiler（冥驹/狙击手倾向画像引擎）**
- **核心能力清单**：
  - **Utility Placement & Ability Analysis**：可视化对手技能释放位置，优先级：**可放置道具（Placeable）**（Cypher 绊线、Killjoy 警戒机器人、Vyse 墙、Chamber 绊雷）> 侦察（Recon）> 烟（Smokes）> 拖延/反制（Reactive stall）> 闪（Flashes）。
  - **Operator Tendency & Sniper Profiler**：追踪 Operator（及 Odin 等高价值武器）的经济购买率与持有者，映射防守端站位（前压激进架点 vs 被动架过点像素位），以及狙击手持有权在队员/特工间的转移。
  - **Dynamic Filtering**：支持按对手战队、地图、选手、特工、阵容组合（Composition）、版本（Patch）、攻防边（Side）、武器、具体技能进行多维筛选。
  - **Coach-Friendly Visualizations & Evidence**：提供密度渐变热力图与硬数字（如 `"75/100 rounds"`），必须展示样本量、分析回合数/场次数等证据链，**禁止仅做纯聊天机器人问答框**。
- **数据特注**：GRID 主事件流提供施放技能时的玩家位置与时间，**`val-ability-supplements/` 补充了精确的 3D 施放位置、视角朝向（view）与速度**，但仍**不直接包含道具最终落点（landing location）**；参赛者可做落点推断/物理估算，但不强制要求完美重建。
- **加分进阶方向**：Anti-Strat 反制建议（如推荐特定阵容/道具清点方案）+ Self-Scouting（对 Cloud9 / Cloud9 GC 自身历史比赛做自查）。
- **评委核心检验标准**：至少展示一条有样本量支撑的可视化战术结论，如：*"对手 A 在地图 B 的 (X, Y) 点位 60% 概率放置哨卫道具"* 或 *"队伍 C 主狙击手在回合 0-20s 有 80% 概率架 D 点激进位，20-40s 降至 10%"*。

### 3. Category 3: Event Mini Game
- **官方定位**：Cloud9 线下展台 / 活动现场供粉丝排队的快节奏趣味小游戏（推荐 **Rider** + Unity / Unreal / Godot，或 WebStorm + Phaser / PixiJS）。
- **核心要求**：单局 `< 3 分钟`、高重玩性、零教程即上手（纯鼠标点击/方向键/单键）、**Booth-Ready**（局间干净重置、离线/无 Wi-Fi 可运行本地高分榜）。
- **合规红线**：若受 Riot 游戏启发，**必须使用原创名称、美术、音效与资产**，严禁直接复用 Riot 内容，须遵守 [Riot Games Developer Policies](https://developer.riotgames.com/policies/general)。

---

## 三、评审维度、权重与 Bonus Prize 要求

### 1. 两阶段评审机制
- **Stage One（Pass/Fail 初筛）**：是否切合赛道主题，以及是否合理使用了至少一种必选 JetBrains 工具。
- **Stage Two（5 项等权重评分，各占 20%）**：
  1. **Technological Implementation**：使用 JetBrains 工具的深度与熟练度，以及工程实现的真实工作量与非平凡程度（non-trivial）。
  2. **Design**：是否交付完整、连贯的产品体验，而非粗糙的 PoC。
  3. **Potential Impact**：是否针对真实受众（Cloud9 教练组/选手/展台粉丝）的真实痛点提出可信、具体的解决方案并在 Demo 中验证。
  4. **Quality of the Idea**：创意新颖度与差异化。
  5. **Presentation**：3 分钟内演示端到端运行效果，清晰传达痛点、受众与价值。
- **同分决胜（Tie Breaking）**：按上述 1 → 5 顺序逐项比较单项最高分。

### 2. JetBrains 强制门槛与 Bonus Prize ($1,000)
- **强制门槛（Eligibility）**：项目必须使用至少一种 JetBrains 工具构建或重大更新：
  - **JetBrains IDEs**（PyCharm、WebStorm、IntelliJ IDEA、Rider、DataGrip 等）
  - **JetBrains Air**（今年主推的 Agentic 开发环境，含独立应用 / IDE 插件 / Web / CLI）
  - **AI Coding Agent Junie**
  - *官方强烈建议*：将 `.idea/`、`.junie/` 或 `.air/` 目录提交到公开仓库作为使用证据（注意剔除敏感信息）。
- **Bonus Prize（Best AI-Powered Workflow Story, $1,000）**：
  - 需在提交表单中提供**直链 URL**（独立文档、Dev.to/Medium 博客、LinkedIn/X 帖子、短视频，或仓库内专门文件如 `AI_SHOWCASE.md`），完整展示团队如何用 **JetBrains IDEs / Junie / JetBrains Air** 加速开发并解决关键工程难题。

---

## 四、GRID 官方电竞数据获取路径与格式（公开免费直下）

> **重要结论**：**无需等待 API Key 审批**。主办方已将官方赛事数据打包为公开 GitHub 仓库，可直接 `git clone` 免费获取（但严格受版权与反再分发约束）。

- **官方数据仓库**：`https://github.com/cloud9esports/stl-hackathon-2026-grid-starter`（总大小约 **1.4 GB**，单文件不超过 3 MB；另附 GRID API 文档 `https://docs.grid.gg/public/documentation`）。
- **拉取命令**（支持按赛道 Sparse Checkout）：
  ```bash
  # 克隆到项目目录之外（严禁放进自己的项目 git 仓库！）
  git clone --filter=blob:none --sparse https://github.com/cloud9esports/stl-hackathon-2026-grid-starter.git
  cd stl-hackathon-2026-grid-starter
  git sparse-checkout set lol meta                  # LoL 赛道
  # 或：git sparse-checkout set val val-ability-supplements meta  # VAL 赛道
  ```
- **数据规模与覆盖范围（2025–2026 赛季）**：
  - **LoL (`lol/`)**：**745 个 Series（1,741 局比赛）**，覆盖 LCK、LEC、LTA North/South、LCS（含 **Cloud9 Kia**）。
  - **VAL (`val/` + `val-ability-supplements/`)**：**857 个 Series（2,081 局地图，856 个技能位置/朝向补充包）**，覆盖 VCT Americas、Masters Toronto 与全赛区 Game Changers（含 **Cloud9** 与 **Cloud9 GC**）。
  - **元数据索引 (`meta/`)**：6 张轻量 CSV（`tournaments.csv`、`teams.csv`、`players.csv`、`characters.csv`、`games.csv`、`rosters.csv`），可直接做快速索引与胜负/阵容统计，无需解压 `.zst`。
- **数据格式与解析规范**：
  - 格式为 Zstandard 压缩的 UTF-8 JSON Lines（`events_{seriesId}_grid.jsonl.zst`），解压膨胀比 **50–150×**（VAL 全量解压约 160 GB），**必须流式读取**（Python 3.14+ 用 `compression.zstd.open`，Python <=3.13 用 `zstandard.open`）。
  - 每行是一个 JSON Envelope（含 `occurredAt`、`sequenceNumber`、`events[]`）；`events[].type` 遵循 `{actor}-{action}-{target}`（`!` 前缀表示回滚撤回，如 `player-!purchased-item`）。
  - `includesFullState: true` 为完整状态快照，`false` 为增量局部状态；58 个 series 以 `valid: false` 结束，统计前须检查 `meta/games.csv` 的 `session_valid` 标志。
  - LoL BP 事件：`team-picked-character`、`team-banned-character` 与 `draftActions`。
- **绝对禁令（LICENSE.md）**：**严禁**将 `.zst`、解压后的 `.jsonl`、提取的 `.parquet/.sqlite/.duckdb` 或 `meta/*.csv` 提交到任何自己的 Git 仓库（包括私有库），否则构成违规再分发并导致取消资格。项目代码应通过环境变量 `STL_DATA_DIR`（默认 `../stl-hackathon-2026-grid-starter`）引用本地数据；仅允许在代码中保留极小脱敏聚合结果/截图。

---

## 五、交付物硬性清单（Submission Checklist）

1. **公开开源代码仓库**：GitHub / GitLab / Bitbucket 公开 URL，根目录必须包含可识别的**开源协议文件**（`LICENSE` / `LICENSE.md` / `LICENSE.txt`），含完整运行说明（建议附 `.idea/` / `.junie/` / `.air/`）。
2. **可访问的 Working Project**：在线 Web Demo URL（若需登录须在测试说明中提供免费测试账号），或评委可直接安装运行的构建包/步骤（评审期结束 `2027-02-03` 前保持免费可用）。
3. **Demo 视频**：**<= 3 分钟**（评委不看超时部分），**公开发布在 YouTube**，展示真实端到端运行画面，不得包含无授权第三方商标/版权音乐，英文讲解或英文字幕。
4. **文本说明（全英文）**：
   - 功能特性说明 + **JetBrains 工具使用说明**（用了哪些工具、各自承担什么角色）
   - **Methodology Write-up**：技术路线与解决赛道痛点的方法论
5. **（可选）Bonus Prize 链接**：指向 `AI_SHOWCASE.md` 或博客/视频的直链。
6. **语言要求**：所有提交材料、视频与说明须为**英文**（或提供完整英文翻译）。

---

## 六、推荐立项赛道与 MVP 切入点

- **推荐主攻赛道**：**Category 2 (LoL): Macro Scouting & Draft Management System**（次选 Category 1 VAL，可按自身前端可视化 vs 策略建模优势最终拍板）。
  - **推荐理由**：
    1. **数据轻且结构高度确定**：LoL 745 个 series 的 `team-picked-character` / `team-banned-character` / `draftActions` + 前期野区/资源事件（龙、先锋、虚空巢虫）可直接从流式扫描中提取成极紧凑的聚合特征表，无需处理 VAL 复杂的 2D/3D 地图坐标配准与技能落点物理推断；
    2. **痛点明确、差异化空间大**：2025–2026 职业赛全面推行 **Fearless Draft（全局 BP）**，传统静态胜率表完全失效；能把 **Bo3/Bo5 跨局英雄池衰减 + 实时 Draft Winrate Impact + 对手前 15 分钟宏观资源倾向** 结合成一个教练可直接点击使用的交互式 Web 工作台，极易在 `Design` 和 `Potential Impact` 拿高分。
- **推荐 MVP 架构（Category 2 LoL）**：
  1. **离线 ETL 管线（PyCharm / Python）**：流式扫描 `stl-hackathon-2026-grid-starter/lol/` + `meta/`，提取仅含聚合统计的轻量 JSON（绝不提交原始赛事流），涵盖：战队/选手 Hero Pool、一二轮 Pick/Ban 率、**Fearless Draft Game 1→5 状态转移与胜率衰减**、打野前 10 分钟刷野路线/首条资源控制率。
  2. **实时 Draft 决策引擎（FastAPI / TypeScript）**：模拟标准 BP 与 Fearless Bo5 状态机，基于当前已锁/已 Ban 阵容实时计算 **Winrate Delta** 与 **"How to Win" 反制建议**（含样本量证据链，如 `"n=18 games on Patch 15.x"`）。
  3. **教练端交互前端（WebStorm / React / Next.js + Vercel 在线部署）**：左侧对手 Macro Scouting 卡片，中间 Fearless Bo5 交互式 BP 模拟器（自动灰显前几局已用英雄），右侧实时胜率仪表盘与 Ban/Pick 推荐理由。
  4. **JetBrains 证据链与 Bonus 冲刺**：全程用 **PyCharm + WebStorm + Junie / JetBrains Air** 开发，保留 `.idea/` 与 `.junie/`，并在仓库根目录撰写 `AI_SHOWCASE.md` 同步角逐 **$1,000 Bonus Prize**。
