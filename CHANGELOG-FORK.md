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

---

## 三、变更详情

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

## 四、构建环境备注（d:\soure\x-hub 工作副本）

- Node：portable Node v24.17.0（`WPS 灵犀/portable-node/`，Vite 8 要求 node ≥20.19）搭配 `D:\Program Files\nodejs` 的 npm 模块；portable 自带 npm 的网络模块损坏，仅用其 `node.exe`
- 网络：项目根 `.npmrc` 禁用代理（本机 `127.0.0.1:7890` 代理会导致 npm 访问 npmmirror CDN 返回 400），npm 走直连
- 编译命令：`npm run tauri:build`，产物 `src-tauri/target/release/x-hub.exe`（bundle 关闭，仅出裸 exe）
