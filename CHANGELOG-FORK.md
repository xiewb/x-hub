# CHANGELOG-FORK — fork 版本修订与变更记录

本仓库为 [dckxx/x-hub](https://github.com/dckxx/x-hub)（上游）的 fork，fork 仓库为 [xiewb/x-hub](https://github.com/xiewb/x-hub)。

本文件记录：

- 每次 fork / 合并上游时的时间和版本基点；
- 每次 fork 版本新增和修改的需求、设计与实现内容；
- 上游合并的维护约定。

> 本文件由 fork 维护者维护，每次合并上游或发布 fork 修订时**必须同步更新**。

---

## 一、维护约定：上游合并流程

上游 [dckxx/x-hub](https://github.com/dckxx/x-hub) 每次代码变更后，都按以下流程合并到 fork 分支（`master`）：

1. **获取上游**：在上游克隆（`e:\github\dckxx\x-hub`）执行 `git fetch origin`，确认上游新提交范围与内容。
2. **合并基线**：在 fork 工作克隆（`e:\github-self\x-hub`）执行 `git fetch origin && git merge <上游commit>`（或对 fork 未推送的本地提交做 `rebase`）；冲突以 fork 修订与上游语义合并为准，无法自动合并的文件基于上游新版重做 fork 逻辑。
3. **回归验证**：前端 `npm run build`（含 vue-tsc 类型检查）+ `npm run tauri:build` 全量编译通过。
4. **更新本文件**：在「修订记录」表追加一行，并补充「变更详情」小节（时间、上游版本、fork 提交、需求与设计实现）。
5. **推送**：`git push origin master` 推送到 fork 仓库，并同步刷新各工作副本（如 `d:\soure\x-hub`）。

合并策略说明：fork 修订数量少、集中在速记标签等局部文件，优先采用 `merge` 保留双方历史；若上游重写同一文件（如 `NoteEditor.vue` 重构），基于上游新版重新实施 fork 逻辑，并在变更详情中注明。

---

## 二、修订记录

| # | 日期 | 上游基点 | 上游版本 | fork 提交 | 摘要 |
|---|------|----------|----------|-----------|------|
| 1 | 2026-09-23 | `d957223` | v0.6.5 | —（本地开发） | 建立副本，开发速记标签修复 |
| 2 | 2026-09-24 | `8e195b9` | v0.6.6 | `c3b970f` | 上游合并 16 提交；标签修复在新基线重做并推送 fork |
| 3 | 2026-09-24 | `8e195b9` | v0.6.6 | 待提交 | 速记四大增强：搜索/排序/垃圾箱/格式工具栏（开发副本 d:\source\x-hub） |
| 4 | 2026-09-26 | `8e195b9` | v0.6.6 | 待提交 | 编辑器全面升级：源码 CodeMirror 6、查找替换、撤销重做、大纲导航、==高亮== 扩展、排版精修；含垃圾箱恢复与换行修复 |
| 5 | 2026-09-26 | `8e195b9`→`6167b8f` | v0.7.0 | 待提交 | 上游合并 9 提交（v0.6.7+v0.7.0），零冲突自动合并；93 文件 +5242/-732 |

---

## 三、变更详情

### #5（2026-09-26）合并上游 v0.7.0

- **上游基点**：`8e195b9` → `6167b8f`（9 个提交，含 `bb56431` v0.6.7 与 `f1e749d` v0.7.0）
- **上游主要变更**：速达子分类/自定义卡片/内置浏览器面板（`SudaCustom*`/`SudaWebPanel`/`suda_browser.rs` +796）；托盘/后台应用窗口调度前台；通知驻留时长可配；AI 供应商空模型拦截保存；扩展外链权限 `system`→`open-url`；`NoteEditor.vue` 仅修 `detachImageListeners` 声明位置（TDZ），与 fork 逻辑无冲突
- **合并结果**：零冲突自动合并（93 文件交集 10 个，双方改动区域不重叠）；`vue-tsc` + `cargo check` 双侧验证通过
- **备注**：合并期间 push 通道（GitHub POST）网络受阻，合并先在本地 `d:\\source\\x-hub` 完成，网络恢复后推送

### #4（2026-09-26）速记编辑器全面升级（含两个缺陷修复）

**缺陷修复**（随本轮一并交付）：

| 问题 | 根因与修复 |
|------|-----------|
| 垃圾箱恢复后笔记内容丢失 | 上游 `refreshNotes` 用 `list_meta`（空 content）整体替换内存列表；新增 `get_note` 命令 + 合并式刷新（已有笔记保留正文，新 id 补拉） |
| 源码↔实时预览单换行被放大为空行且不可逆 | milkdown 默认无 `remarkLineBreak`，单换行被拆为独立段落且序列化产生多余空行；注入官方插件（parse 拆 inline hardbreak、serialize 输出干净单换行，round-trip 无损），并在 `restoreCrepeMarkdown` 清理行尾硬换行痕迹（单个 `\\` / 双空格） |

**编辑器全面升级**（用户决策：全面升级档位 + 跟随应用风格精修）：

| 功能 | 设计与实现 |
|------|-----------|
| 源码模式 CodeMirror 6 | 新增 `CodeMirrorSource.vue` 替换 source/split 左栏两处 textarea：markdown 语法高亮（嵌套代码块经 language-data 按需加载）、行号、自动换行、亮/暗主题全走应用 CSS 令牌（darkTheme 布尔经 MutationObserver + Compartment 重配）；Enter 结构补全钩子保留（`transformOnEnter` prop），分屏滚动同步改观 `scrollDOM` |
| 查找替换 | 新增 `FindReplaceBar.vue`（匹配计数/上下条/替换/全部/大小写/正则开关）+ `utils/proseFind.ts`（ProseMirror 文本扫描与事务，全部替换从尾向头单事务防位置偏移）；wysiwyg 走 PM 事务、源码/分屏走 CM search API，Ctrl+F / Ctrl+H 面板级捕获统一入口 |
| 撤销/重做按钮 | 工具栏追加两键：wysiwyg 经 `callCommand(undoCommand.key/redoCommand.key)`（Crepe 内置 history），源码/分屏走 CM `undo/redo`；不走文本变换通道 |
| 大纲导航 | 工具栏大纲按钮弹出浮层面板：wysiwyg 从 doc 扫 heading（600ms 节流轮询对比重建），source/split 正则解析行首 `#`（跳过围栏）；点击滚动定位（PM setTextSelection+scrollIntoView / CM scrollToLine） |
| ==高亮== 扩展语法 | `utils/forkHighlight.ts`：`$mark` schema（`<mark>` DOM）+ remark 双向 transformer（parse 拆 text 内 `==x==`，serialize 经 unified `toMarkdownExtensions` 协议注入 handler 输出 `==…==`），round-trip 无损（scripts/test-highlight-roundtrip.mjs 冒烟验证）；工具栏高亮键走三模式文本变换通道 |
| 排版精修 | 标题 h1-h6 层级/行距/段距、代码块圆角边框、表格表头底色与边框、引用左边条+浅底（暗色适配）、hr 细化；查找条/大纲面板毛玻璃统一风格；全部分异名流应用设计令牌，暗色随 `[data-theme='dark']` 自动生效 |

**新增依赖**：`@codemirror/state/view/language`、`@codemirror/lang-markdown`、`@codemirror/search`、`@codemirror/language-data`（源码模式升级）。

**已知限制**：手写源码中 `==高亮==` 内嵌行内结构（如 `==a *b* c==`）时，跨节点匹配不支持，re-parse 后退化为字面文本（编辑器内 toggleMark 创建的高亮不受影响）。

### #2（2026-09-24）合并上游 v0.6.6 + 标签修复并推送 fork

- **上游基点**：`d957223` → `8e195b9`（16 个提交，含 `74aadb1` chore(release): v0.6.6）
- **上游主要变更**：速记三模式（预览/分屏/源码）与输入修复（`NoteEditor.vue` 重写 +674 行）；速达卡片长按拖拽排序；倒计时列表撑满与已结束条目原位灰态；扩展隔离、服务鉴权与数据外发安全加固；`openExternal` 权限收紧；敏感名单放宽；MIT LICENSE 与贡献指南补全
- **fork 提交**：`c3b970f` fix(notes): 速记标签支持全局删除并修复筛选栏显示不完整
- **合并处理**：上游重写了 `NoteEditor.vue`，fork 的标签同步 watch 基于新版重新实施（插入点 `removeTag` 函数后）；`NoteList.vue` 上游未改动，修复直接沿用

### #1（2026-09-23）建立 fork 副本 + 速记标签修复（需求与设计实现）

**需求背景**：上游 v0.6.5（`d957223`）的速记模块存在两个缺陷：

1. 标签无法删除——编辑器底栏 ✕ 只把标签从当前笔记摘除，标签实体永远留在筛选栏（API 层 `deleteTag`、store action、Rust 命令均已存在但 UI 从未接线）；筛选栏横向滚动条被 `display: none` 隐藏，标签多时超出部分不可见。

**设计与实现**：

| 改动点 | 设计 |
|--------|------|
| 筛选栏删除入口（`NoteList.vue`） | 标签 chip 内嵌 `×` 按钮（悬停显示，交互仿待办模块 `TodoView` 惯例），点击写入 `removingTag` 状态 |
| 删除确认（`NoteList.vue`） | 复用 `ConfirmDialog`（tone=danger），确认后调 `store.deleteTag(id)` → Rust `delete_tag` → `note_tags` 外键 `ON DELETE CASCADE` 级联摘除所有笔记关联；删除后重置筛选状态并刷新 `tagMap` |
| 显示不完整修复（`NoteList.vue`） | 筛选栏 `flex-wrap: wrap` 自动换行替代隐藏的横向滚动；标签名超长省略号截断（`max-width: 12em`）；新增 `tag-x` 悬停显隐样式 |
| 编辑器残留同步（`NoteEditor.vue`） | watch `store.state.tags` 的 id 集合，标签被全局删除后同步过滤 `noteTags`，底栏不再残留已删标签 |

**验证**：vue-tsc 类型检查 + vite 构建通过；tauri 全量编译通过并产出验证用 exe。

---

### #3（2026-09-24）速记四大增强：搜索 / 排序 / 垃圾箱 / 格式工具栏

**需求**：① 文档列表支持按修改时间/名称/大小排序；② 提供更完善的 markdown 编辑体验；③ 删除进垃圾箱可恢复；④ 按标题或内容搜索笔记。

**设计与实现**：

| 功能 | 设计 |
|------|------|
| 搜索（`NoteList.vue`） | 列表头部搜索框，标题/内容双字段本地过滤（store 全量持有 content），空结果区分「无笔记/无匹配」 |
| 排序（`NoteList.vue`） | 头部下拉：修改时间（默认）/创建时间/名称（zh-CN localeCompare）/大小（content 长度），选择持久化 localStorage（`note_sort_key`） |
| 垃圾箱（全栈） | `notes` 表加 `deleted_at` 列（PRAGMA table_info 幂等迁移）；`delete_note` 改软删除，新增 `restore_note/purge_note/list_trash/empty_trash` 命令并注册；所有活跃查询排除已删条目，`update/search` 同步收紧；note_tags 由外键 CASCADE 清理。前端：列表头部垃圾箱入口 → 垃圾箱视图（恢复/彻底删除/清空，全部 ConfirmDialog 防误操作）；原「重建式撤销」toast 移除 |
| 格式工具栏（`NoteEditor.vue`） | 三模式通用 14 键工具栏（加粗/斜体/删除线/H1-H3/无序/有序/任务列表/引用/行内代码/代码块/链接/分割线）。实现为纯文本变换 `transformMarkdown`：源码/分屏模式基于 textarea 选区精确操作（包裹类 toggle、行前缀 toggle、有序列表自动编号）；wysiwyg 模式 capture→变换→重挂（Crepe 无法取源码光标的务实退化）。另加正文字符数统计 |

**兼容性**：`delete_note` IPC 命令名与参数未变（语义升级为软删除），扩展桥等既有调用方无需改动；恢复的笔记保持原 id/标签/时间戳。

**追加修复（同日）**：垃圾箱恢复后笔记内容丢失。根因是上游 `refreshNotes()` 的既有缺陷：它用 `list_notes`（仅元信息，content 为空串）整体替换 `state.notes`，把列表里所有笔记的正文清掉，此后任何一次编辑都会把空正文写回数据库（剪贴板浮层保存后刷新同样会触发）。修复：新增 `get_note(id)` 命令按 id 补拉单条全文；`refreshNotes` 改为合并式——已有笔记保留本地正文，新出现的 id 单独补拉全文。

## 四、构建环境备注（d:\soure\x-hub、d:\source\x-hub 工作副本）

- Node：portable Node v24.17.0（`WPS 灵犀/portable-node/`，Vite 8 要求 node ≥20.19）搭配 `D:\Program Files\nodejs` 的 npm 模块；portable 自带 npm 的网络模块损坏，仅用其 `node.exe`
- 网络：项目根 `.npmrc` 禁用代理（本机 `127.0.0.1:7890` 代理会导致 npm 访问 npmmirror CDN 返回 400），npm 走直连
- 编译命令：`npm run tauri:build`，产物 `src-tauri/target/release/x-hub.exe`（bundle 关闭，仅出裸 exe）
