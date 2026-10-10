# -*- coding: utf-8 -*-
"""标签组成员兜底：Tabbit 把保存的标签组同步进书签树（<父>/标签组/<组名>/url），
按 URL 关联会话标签页"""
import io

path = r"D:\source\x-hub\src-tauri\src\commands.rs"
src = io.open(path, encoding="utf-8").read()

# 1) collect_chromium_tabs 增加 bookmarks_file 参数
old = '''fn collect_chromium_tabs(
    sessions_dir: std::path::PathBuf,
    browser: &str,
    out: &mut Vec<BrowserTab>,
) -> usize {'''
new = '''fn collect_chromium_tabs(
    sessions_dir: std::path::PathBuf,
    bookmarks_file: Option<std::path::PathBuf>,
    browser: &str,
    out: &mut Vec<BrowserTab>,
) -> usize {'''
assert src.count(old) == 1
src = src.replace(old, new)

# 2) 函数末尾归属兜底：URL 在「标签组」书签文件夹中 → 组名
old = '''        if group.is_empty() {
            if let Some((_, rest)) = url.split_once("group-home/") {
                let gs = rest
                    .split(|c: char| !c.is_ascii_hexdigit() && c != '-')
                    .next()
                    .unwrap_or("");
                if let Some(name) = group_name.get(gs) {
                    group = name.clone();
                }
            }
        }
        out.push(BrowserTab {'''
new = '''        if group.is_empty() {
            if let Some((_, rest)) = url.split_once("group-home/") {
                let gs = rest
                    .split(|c: char| !c.is_ascii_hexdigit() && c != '-')
                    .next()
                    .unwrap_or("");
                if let Some(name) = group_name.get(gs) {
                    group = name.clone();
                }
            }
        }
        // 兜底：Tabbit 会把保存的标签组同步进书签树（「标签组」文件夹下按组名分文件夹），
        // 按 URL 反查组名（cmd25 归属记录常在浏览器运行中被锁定的快照里，读不到）
        if group.is_empty() {
            if let Some(name) = tab_group_bookmarks.get(&url) {
                group = name.clone();
            }
        }
        out.push(BrowserTab {'''
assert src.count(old) == 1
src = src.replace(old, new)

# 3) 函数开头加载书签组映射
old = '''    let Ok(dirs) = std::fs::read_dir(&sessions_dir) else {
        return 0;
    };
    let mut files: Vec<std::path::PathBuf> = dirs
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.is_file()
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with("Session_") || n.starts_with("Tabs_"))
                    .unwrap_or(false)
        })
        .collect();
    files.sort_by_key(|p| std::cmp::Reverse(p.metadata().and_then(|m| m.modified()).ok()));
    // 组名与 tab→组归属跨全部可读文件累积'''
new = '''    let Ok(dirs) = std::fs::read_dir(&sessions_dir) else {
        return 0;
    };
    // 书签里的标签组映射（url → 组名），来源见 collect_tab_group_bookmarks
    let tab_group_bookmarks = bookmarks_file
        .and_then(|p| collect_tab_group_bookmarks(&p).ok())
        .unwrap_or_default();
    let mut files: Vec<std::path::PathBuf> = dirs
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.is_file()
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with("Session_") || n.starts_with("Tabs_"))
                    .unwrap_or(false)
        })
        .collect();
    files.sort_by_key(|p| std::cmp::Reverse(p.metadata().and_then(|m| m.modified()).ok()));
    // 组名与 tab→组归属跨全部可读文件累积'''
assert src.count(old) == 1
src = src.replace(old, new)

# 4) 新增书签组解析函数（挂在 guid_to_string 前）
old = '''/// 16 字节二进制 GUID → 标准字符串形式（8-4-4-4-12，前三段小端序还原）'''
new = '''/// 从书签文件提取「标签组」成员映射：遍历书签树，凡名为「标签组」的文件夹，
/// 其下每个子文件夹视为一个保存的标签组，组内全部 URL → 子文件夹名。
/// 返回 Err = 文件不存在或 JSON 解析失败。
fn collect_tab_group_bookmarks(
    path: &std::path::Path,
) -> Result<std::collections::HashMap<String, String>, String> {
    let data = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&data).map_err(|e| e.to_string())?;
    let mut map = std::collections::HashMap::new();
    fn walk(node: &serde_json::Value, in_tab_groups: bool, map: &mut std::collections::HashMap<String, String>) {
        let Some(children) = node.get("children").and_then(|c| c.as_array()) else {
            return;
        };
        let name = node.get("name").and_then(|n| n.as_str()).unwrap_or("");
        for c in children {
            let cname = c.get("name").and_then(|n| n.as_str()).unwrap_or("");
            let is_folder = c.get("type").and_then(|t| t.as_str()) == Some("folder");
            if in_tab_groups && is_folder {
                // 该文件夹即一个标签组：其下所有 URL 归入组名
                fn collect_urls(n: &serde_json::Value, map: &mut std::collections::HashMap<String, String>, group: &str) {
                    if n.get("type").and_then(|t| t.as_str()) == Some("url") {
                        if let Some(u) = n.get("url").and_then(|u| u.as_str()) {
                            map.entry(u.trim().to_string()).or_insert_with(|| group.to_string());
                        }
                        return;
                    }
                    if let Some(cs) = n.get("children").and_then(|c| c.as_array()) {
                        for c in cs {
                            collect_urls(c, map, group);
                        }
                    }
                }
                collect_urls(c, map, cname);
            }
            walk(c, in_tab_groups || (is_folder && name == "标签组"), map);
        }
    }
    if let Some(roots) = v.get("roots").and_then(|r| r.as_object()) {
        for (_k, r) in roots {
            if r.is_object() {
                walk(r, false, &mut map);
            }
        }
    }
    Ok(map)
}

/// 16 字节二进制 GUID → 标准字符串形式（8-4-4-4-12，前三段小端序还原）'''
assert src.count(old) == 1
src = src.replace(old, new)

# 5) 调用点传入 Bookmarks 路径
old = '''            for pd in profile_dirs {
                count += collect_chromium_tabs(pd.join("Sessions"), browser, &mut items);
            }'''
new = '''            for pd in profile_dirs {
                count += collect_chromium_tabs(
                    pd.join("Sessions"),
                    Some(pd.join("Bookmarks")),
                    browser,
                    &mut items,
                );
            }'''
assert src.count(old) == 1
src = src.replace(old, new)

io.open(path, "w", encoding="utf-8", newline="\r\n").write(src)
print("patch2 完成")
