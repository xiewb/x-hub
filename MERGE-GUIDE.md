# Fork 合并上游规范（MERGE GUIDE）

> 本文档沉淀 x-hub fork 历次合并上游的固定流程与冲突决策约定。
> 每次合并必须遵循本文档；遇到本文未覆盖的新冲突模式，解决后**回写本文档**。

## 1. 三仓库拓扑

| 位置 | remote 名 | 角色 | 操作权限 |
|---|---|---|---|
| `D:\source\x-hub`（活动工作区） | `origin` → github.com/xiewb/x-hub；`upstream` → `E:/github/dckxx/x-hub` | **开发主线**：所有合并、修订、构建都在这里做 | 读写 |
| `E:\github\dckxx\x-hub` | `origin` → github.com/dckxx/x-hub（真上游） | **上游镜像**：新版本先在这里 `git fetch origin` 可见；其本地 master 需先 ff 同步，`D:\source` 的 `git fetch upstream` 才能取到 | 只读参考（仅允许 `--ff-only` 同步） |
| `E:\github-self\x-hub` | `origin` → github.com/xiewb/x-hub | **发布镜像**：合并推送后到这里 `git pull` 保持一致 | 只读参考（注意其可能有未提交改动，勿动） |

## 2. 合并流程（七步）

```bash
# ① 上游镜像同步 + 取新版本
cd /e/github/dckxx/x-hub && git fetch origin --tags
git merge --ff-only origin/master          # 只允许 ff，禁止在镜像上产生合并提交

# ② 主线拉取并预检
cd /d/source/x-hub
git fetch upstream --tags
git log --oneline HEAD..vX.Y.Z             # 预览新提交
git diff --stat HEAD v0.8.0 | tail -5      # 预览影响面（文件数/行数）
git merge-base HEAD upstream/master        # 确认基点无分叉

# ③ 合并
git merge vX.Y.Z                           # 用 tag 合并，commit message 写 "Merge tag 'vX.Y.Z'：<一句话主题>"

# ④ 冲突解决 —— 按 §3 约定逐块处理，禁止无脑 --ours/--theirs

# ⑤ 验证（全部通过才能提交）
npm run build                              # vue-tsc + vite，前端零 error
cd src-tauri && cargo check                # Rust 编译零 error
cargo test note                            # 速记模块单测全绿（v0.8.0 起 33 条）
npm run tauri:dev                          # 启动应用肉眼回归（重点：双方特性并集区域）

# ⑥ 文档同步 —— CHANGELOG-FORK.md 追加修订记录（见 §4）

# ⑦ 提交推送 + 镜像同步
git add <仅合并相关文件>                    # ⚠️ 禁止 git add -A（会卷入未跟踪的本地脚本/.npmrc 等）
git commit --amend --no-edit               # 如需把 CHANGELOG 并入合并提交；否则单独 docs(fork): 提交
git push origin master                     # 会弹 TortoiseGit 凭据对话框，需人工确认，终端看似卡住属正常
cd /e/github-self/x-hub && git pull origin master
```

## 3. 冲突解决约定（按场景）

### 3.1 总原则

1. **上游为基线，fork 特性做并集/兼容层**——fork 的存在意义是在上游之上增量增强，合并后必须同时保留双方特性，除非一方明确取代另一方。
2. **先判断重叠性质**：同名函数（二选一或语义归一）→ 独立功能（两侧全保留）→ 结构重构（手工套嵌并集）。用 `git show v0.8.0:<file>` 和 `git show HEAD:<file>` 对照原版，不要只看冲突块上下文。
3. **跨文件一致性**：改一处签名，必须同步 Rust 定义 ↔ `lib.rs` 注册 ↔ `src/api/tauri.ts` 封装 ↔ 调用方四处。
4. **验证驱动收尾**：冲突标记清零后立即跑 §2-⑤ 的验证，按报错回改，不要凭感觉判定"应该没问题"。

### 3.2 已固化的决策（v0.8.0 合并确立）

| 场景 | 约定 |
|---|---|
| 回收站双实现 | 上游 `trash/restore/delete/purge_expired/list_trashed` 为主；fork 旧 API（`soft_delete`/`purge`/`list_trash`/`empty_trash`）在 `repo/note.rs` 尾部保留为薄兼容层，扩展桥（`xhub_api.rs`）继续走 fork 口径，新 SpeednoteView 走上游口径 |
| NoteEditor.vue | fork（格式工具栏/查找替换/大纲/==高亮==/CodeMirror 源码模式）与上游（AI 美化/双链面板/wiki 补全/emoji 图标）**两侧全保留**；模板外壳用上游 `ed-main`+双链面板结构，内部嵌 fork 三模式（CodeMirrorSource）；上游按 textarea API 写的光标代码一律适配为 CM 实例 API（`getSelection().from` / `view.dispatch({selection})` / `focusEditor()`）；`.ed-body` CSS 保持 row 向 + `position:relative`（查找替换浮条依赖） |
| NoteList.vue 类孤儿文件 | 上游重构后删除、fork 曾深度修改的文件：接受删除（新组件已取代），fork 版本可 `git show <合并前commit>:<path>` 取回；其中仍有效的 fork 功能确认上游新 UI 是否已有对应物，没有的记入 CHANGELOG 待移植清单 |
| 命令重复注册 | `lib.rs` generate_handler 中同名命令只留一份；优先保留与 `commands.rs` 存活定义匹配的那份 |
| Rust 测试 | 两侧测试函数名不同则都保留；fork 测试断言与上游新语义冲突时（如 v0.8.0 起 `update` 不再限制软删笔记），按上游语义改断言并注释原因 |
| `git add` 范围 | 只 add 合并涉及的路径；未跟踪的本地脚本（`scripts/test-*.mjs`、`*.py`、`__pycache__`、`.npmrc`、`README-FORK.md` 等）不入库 |

### 3.3 常见坑（历次踩过）

- **CRLF 陷阱**：仓库文件为 LF；冲突标记行精确匹配 `^=======$`，不要用含 `\r` 假设的正则。Python 脚本按行处理时先确认无 `\r`。
- **git 对齐误导**：冲突块两侧的"公共上下文"可能被 git 错误对齐（两个相似函数体被拼成一个），必要时对照 `git show v0.8.0:<file>` 原版手工重排。
- **`&&` 链中断**：链条中前一条失败（如脚本 ValueError）会导致后面的 sed/命令**静默不执行**，事后必须用独立命令核验每步实际生效。
- **凭据弹窗**：`git push` 会触发 TortoiseGit 凭据选择器（`git-credential-helper-sel` 进程），终端长时间无输出≠卡死；屏幕确认弹窗后即恢复。
- **dev 常驻进程**：`npm run tauri:dev` 不会自行退出，管道 `| tail` 会缓冲全部输出；判断启动成功应查 `app.exe`（`src-tauri/target/debug/app.exe`）进程与 1420 端口，而非等命令结束。

## 4. 文档同步要求

每次合并完成后，`CHANGELOG-FORK.md` 必须追加：

1. **修订总表一行**：`| #N | 日期 | 基点commit→目标commit | 上游版本 | 状态 | 一句话摘要 |`（fork 修订号从 #14 起已与上游合并绑定）。
2. **详情小节**：`### #N（日期）标题`，含上游内容清单、冲突解决策略、验证结果。
3. `README-FORK.md` 的 Upstream badge 同步为新版本号。

## 5. 历次合并决策索引

| 版本 | 修订号 | 核心决策 | 详见 |
|---|---|---|---|
| v0.7.0–v0.7.6 | — | 常规 ff 合并，无重大冲突 | CHANGELOG-FORK.md |
| v0.8.0 | #14 | 回收站归一（上游为主+fork 兼容层）；NoteEditor 双特性并集；NoteList.vue 删除；get_note 取上游 Option 语义 | CHANGELOG-FORK.md #14 |
