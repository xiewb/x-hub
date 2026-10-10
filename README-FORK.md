<div align="center">

# ⚡ x-hub（Fork 版）— 本地个人效率工作台

本仓库为 [dckxx/x-hub](https://github.com/dckxx/x-hub)（上游）的 fork，fork 仓库为 [xiewb/x-hub](https://github.com/xiewb/x-hub)。
在完整保留上游功能的基础上，fork 维护者对**速记模块**等局部做了增强与缺陷修复。

基于 **Tauri 2 + Vue 3 + TypeScript** 的桌面效率工具，Bento 风格界面，所有数据默认本地存储，不上传云端。

![Tauri](https://img.shields.io/badge/Tauri-2.x-24C8DB?logo=tauri&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.x-42b883?logo=vuedotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6.x-3178c6?logo=typescript&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-1.77+-dea584?logo=rust&logoColor=white)
![Upstream](https://img.shields.io/badge/upstream-v0.8.1-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

</div>

## 📌 Fork 说明

- **上游**：[dckxx/x-hub](https://github.com/dckxx/x-hub)，README 功能介绍、截图、交流群等见上游仓库。
- **fork 基点**：上游 v0.6.5（`d957223`，2026-09-23），当前已合并至上游 **v0.8.1**。
- **维护约定**：每次上游合并或发布 fork 修订，必须按 [MERGE-GUIDE.md](MERGE-GUIDE.md) 的七步流程执行，并同步更新 [CHANGELOG-FORK.md](CHANGELOG-FORK.md)（修订记录表 + 变更详情）。

## 🔧 Fork 增强（相对上游的固定差异）

核心改动集中在速记（Notes）模块，涉及 `NoteEditor.vue`、`NoteList.vue`、`forkHighlight.ts` 等文件：

### 速记增强

| 类别 | 内容 |
|------|------|
| 标签管理修复 | 标签支持全局删除（确认弹窗 + 外键级联摘除关联），修复筛选栏显示不完整（自动换行 + 超长截断），编辑器残留同步清理 |
| 搜索与排序 | 列表按标题/内容搜索；按修改时间/创建时间/名称/大小排序，选择持久化 localStorage |
| 垃圾箱 | 软删除（`deleted_at`）+ 恢复 / 彻底删除 / 清空，全链路 ConfirmDialog 防误操作；修复上游 `refreshNotes` 整体替换导致恢复后正文丢失的缺陷（新增 `get_note` 合并式刷新） |
| 格式工具栏 | 三模式通用 14 键工具栏（加粗/斜体/删除线/标题/列表/引用/代码/链接/分割线等），纯文本变换实现；正文字符数统计 |
| 编辑器升级 | 源码模式替换为 **CodeMirror 6**（语法高亮/行号/换行/亮暗主题）；查找替换（Ctrl+F / Ctrl+H，正则/大小写）；撤销重做按钮；大纲导航浮层；`==高亮==` 扩展语法（forkHighlight，round-trip 无损）；排版精修（标题/代码块/表格/引用，暗色适配） |
| 预览一致性 | 分屏预览与实时预览（Crepe）三层修复：`<br />` 转义豁免、`breaks:true` 单换行语义对齐、hardbreak 断行 CSS 移出 Vue scoped data-v 陷阱；列表编号（ol/ul list-style）修复 |
| 单换行修复 | 注入 `remarkLineBreak`，源码↔实时预览 round-trip 无损，不再把单换行放大为空行 |

### 崩溃与环境修复

| 问题 | 修复 |
|------|------|
| 含表格内容导致 Crepe 挂载崩溃 | `forkHighlight.ts` 的 `toMarkdownExtensions` 覆盖语义 bug，改为读取后 `concat`（与 remark-gfm 协议一致） |
| 编辑器主题全失效（无滚动/错乱/不可编辑） | Tauri 运行时 CSP nonce 致 `unsafe-inline` 失效；`tauri.conf.json` 加 `dangerousDisableAssetCspModification: true` 恢复 |

## 🔀 上游合并流程

上游每次代码变更后，按以下流程合并到 fork 分支（`master`）：

1. **获取上游**：在上游克隆（`e:\github\dckxx\x-hub`）执行 `git fetch origin`，确认新提交范围。
2. **合并基线**：在 fork 工作克隆（`e:\github-self\x-hub`）执行 `git fetch origin && git merge <上游commit>`；冲突以 fork 修订与上游语义合并为准，无法自动合并的文件基于上游新版重做 fork 逻辑。
3. **回归验证**：`npm run build`（含 vue-tsc 类型检查）+ `npm run tauri:build` 全量编译通过。
4. **更新 CHANGELOG-FORK.md**：修订记录表追加一行 + 补充变更详情小节。
5. **推送**：`git push origin master`，并同步刷新各工作副本（如 `d:\source\x-hub`）。

合并策略：fork 修订集中在速记等局部文件，优先 `merge` 保留双方历史；上游重写同一文件时基于新版重新实施 fork 逻辑。

## 🛠️ 构建环境备注（工作副本）

- Node：portable Node v24.17.0（`WPS 灵犀/portable-node/`），搭配 `D:\Program Files\nodejs` 的 npm 模块；portable 自带 npm 的网络模块损坏，仅用其 `node.exe`
- 网络：项目根 `.npmrc` 禁用代理（本机 `127.0.0.1:7890` 代理会导致 npm 访问 npmmirror CDN 返回 400），npm 走直连
- 编译命令：`npm run tauri:build`，产物 `src-tauri/target/release/x-hub.exe`（bundle 关闭，仅出裸 exe）

## 🚀 快速开始

```bash
npm install

npm run dev           # Vite 浏览器预览 (http://localhost:1420)
npm run tauri:dev     # Tauri 桌面开发窗口
npm run build         # vue-tsc 类型检查 + vite build
npm run tauri:build   # 构建桌面程序（产物在 src-tauri/target/release/）
```

环境要求：Node.js 18+、Rust 1.77.2+、Windows WebView2（Win10/11 自带）。

## 📄 License

MIT
