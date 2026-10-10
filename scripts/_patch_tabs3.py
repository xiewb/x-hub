# -*- coding: utf-8 -*-
"""组成员匹配放宽：精确 URL → 规范化最长前缀匹配"""
import io, re

path = r"D:\source\x-hub\src-tauri\src\commands.rs"
src = io.open(path, encoding="utf-8").read()

# 1) 书签组映射改为 Vec<(规范化URL, 组名)>，支持前缀匹配
old = '''/// 从书签文件提取「标签组」成员映射：遍历书签树，凡名为「标签组」的文件夹，
/// 其下每个子文件夹视为一个保存的标签组，组内全部 URL → 子文件夹名。
/// 返回 Err = 文件不存在或 JSON 解析失败。
fn collect_tab_group_bookmarks(
    path: &std::path::Path,
) -> Result<std::collections::HashMap<String, String>, String> {
    let data = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&data).map_err(|e| e.to_string())?;
    let mut map = std::collections::HashMap::new();
    fn walk(node: &serde_json::Value, in_tab_groups: bool, map: &mut std::collections::HashMap<String, String>) {'''
new = '''/// URL 规范化：去 scheme、去锚点（#…）、去尾斜杠，供前缀匹配
fn normalize_url(u: &str) -> String {
    let u = u.split("#").next().unwrap_or(u);
    let u = u.split("://").nth(1).unwrap_or(u);
    let u = u.trim_end_matches('/');
    u.to_string()
}

/// 从书签文件提取「标签组」成员映射：遍历书签树，凡名为「标签组」的文件夹，
/// 其下每个子文件夹视为一个保存的标签组，组内全部 URL → 子文件夹名。
/// 返回 Err = 文件不存在或 JSON 解析失败。
fn collect_tab_group_bookmarks(
    path: &std::path::Path,
) -> Result<Vec<(String, String)>, String> {
    let data = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&data).map_err(|e| e.to_string())?;
    let mut map: Vec<(String, String)> = Vec::new();
    fn walk(node: &serde_json::Value, in_tab_groups: bool, map: &mut Vec<(String, String)>) {'''
assert src.count(old) == 1, "old1 %d" % src.count(old)
src = src.replace(old, new)

old = '''            if in_tab_groups && is_folder {
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
}'''
new = '''            if in_tab_groups && is_folder {
                // 该文件夹即一个标签组：其下所有 URL 归入组名
                fn collect_urls(n: &serde_json::Value, map: &mut Vec<(String, String)>, group: &str) {
                    if n.get("type").and_then(|t| t.as_str()) == Some("url") {
                        if let Some(u) = n.get("url").and_then(|u| u.as_str()) {
                            let nu = normalize_url(u.trim());
                            if !nu.is_empty() && !map.iter().any(|(x, _)| *x == nu) {
                                map.push((nu, group.to_string()));
                            }
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
    // 长前缀优先：更具体的书签路径先命中
    map.sort_by_key(|(u, _)| std::cmp::Reverse(u.len()));
    Ok(map)
}'''
assert src.count(old) == 1, "old2 %d" % src.count(old)
src = src.replace(old, new)

# 2) 兜底匹配改为规范化前缀（书签URL与标签页URL任一为前缀，边界在 / ? 或串尾）
old = '''        // 兜底：Tabbit 会把保存的标签组同步进书签树（「标签组」文件夹下按组名分文件夹），
        // 按 URL 反查组名（cmd25 归属记录常在浏览器运行中被锁定的快照里，读不到）
        if group.is_empty() {
            if let Some(name) = tab_group_bookmarks.get(&url) {
                group = name.clone();
            }
        }'''
new = '''        // 兜底：Tabbit 会把保存的标签组同步进书签树（「标签组」文件夹下按组名分文件夹），
        // 按规范化 URL 最长前缀反查组名（cmd25 归属记录常在锁定快照里读不到，且当前页
        // 与保存时 URL 常有路径/锚点差异，精确匹配命中率过低）
        if group.is_empty() {
            let nu = normalize_url(&url);
            if let Some((_, name)) = tab_group_bookmarks
                .iter()
                .find(|(bu, _)| {
                    let (a, b) = if bu.len() <= nu.len() { (bu.as_str(), nu.as_str()) } else { (nu.as_str(), bu.as_str()) };
                    b.starts_with(a)
                        && (a.len() == b.len()
                            || b.as_bytes()[a.len()] == b'/'
                            || b.as_bytes()[a.len()] == b'?')
                })
            {
                group = name.clone();
            }
        }'''
assert src.count(old) == 1, "old3 %d" % src.count(old)
src = src.replace(old, new)

# 3) 变量类型调整
old = '''    let tab_group_bookmarks = bookmarks_file
        .and_then(|p| collect_tab_group_bookmarks(&p).ok())
        .unwrap_or_default();'''
new = '''    let tab_group_bookmarks: Vec<(String, String)> = bookmarks_file
        .and_then(|p| collect_tab_group_bookmarks(&p).ok())
        .unwrap_or_default();'''
assert src.count(old) == 1, "old4 %d" % src.count(old)
src = src.replace(old, new)

io.open(path, "w", encoding="utf-8", newline="\r\n").write(src)
print("patch3 完成")
