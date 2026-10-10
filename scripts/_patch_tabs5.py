# -*- coding: utf-8 -*-
"""从 Sync Data LevelDB 原始字节提取保存标签组的 组名↔URL 映射"""
import io

path = r"D:\source\x-hub\src-tauri\src\commands.rs"
src = io.open(path, encoding="utf-8").read()

# 1) 新函数：挂在 collect_tab_group_bookmarks 前
anchor = "/// 从书签文件提取「标签组」成员映射"
new_fn = '''/// 从 Sync Data LevelDB 原始字节提取保存标签组映射（url → 组名）。
/// Tabbit 等浏览器的「保存的标签组」成员关系存在同步库（SavedTabGroupSpecifics protobuf），
/// 浏览器运行中该库可能独占锁定：逐文件读取、失败的跳过。不做 LevelDB 语义解析，
/// 直接按二进制特征提取：组记录内 GUID 字符串 + UTF-8 组名（后随 color 字节 0x18,<0-9>）+
/// URL；组名所在记录附近的 URL 归属该组。长前缀优先排序后返回。
fn extract_sync_tab_groups(sync_dir: &std::path::Path) -> Vec<(String, String)> {
    use std::collections::HashMap;
    let Ok(dirs) = std::fs::read_dir(sync_dir) else {
        return Vec::new();
    };
    let uuid_re = |data: &[u8], end: usize, back: usize| -> Option<String> {
        // 在 data[end-back..end] 里找最后一个 uuid 字符串
        let start = end.saturating_sub(back);
        let seg = &data[start..end];
        let mut best = None;
        let mut i = 0;
        while i + 36 <= seg.len() {
            let s = &seg[i..i + 36];
            if s.iter().enumerate().all(|(j, &b)| {
                let c = b as char;
                if [8, 13, 18, 23].contains(&j) {
                    c == '-'
                } else {
                    c.is_ascii_hexdigit()
                }
            }) {
                best = Some(String::from_utf8_lossy(s).to_string());
            }
            i += 1;
        }
        best
    };
    // 组 uuid → 名称（要求：UUID 字符串 + 之后 ≤60 字节处出现 UTF-8 CJK 名称，
    // 名称后紧跟 protobuf color 字节 0x18 + 0..9，避免把页面标题误当组名）
    let mut group_names: HashMap<String, String> = HashMap::new();
    let mut files: Vec<std::path::PathBuf> = dirs.flatten().map(|e| e.path()).collect();
    files.sort();
    for f in &files {
        let Ok(data) = std::fs::read(f) else { continue };
        let mut i = 0;
        while i + 3 < data.len() {
            // UTF-8 CJK 起始（U+4E00–U+9FFF 常用区）
            if data[i] >= 0xE4 && data[i] <= 0xE9 && data[i + 1] & 0xC0 == 0x80 {
                // 尝试读一个 2~24 字的 CJK 串
                let mut end = i;
                let mut chars = 0;
                while end + 2 < data.len() && chars < 24 {
                    let b = data[end];
                    if b >= 0xE4 && b <= 0xE9 && data[end + 1] & 0xC0 == 0x80 && data[end + 2] & 0xC0 == 0x80 {
                        end += 3;
                        chars += 1;
                    } else {
                        break;
                    }
                }
                if chars >= 2
                    && end + 1 < data.len()
                    && data[end] == 0x18
                    && data[end + 1] <= 9
                {
                    if let Some(u) = uuid_re(&data, i, 120) {
                        let name = String::from_utf8_lossy(&data[i..end]).to_string();
                        group_names.entry(u).or_insert(name);
                    }
                    i = end;
                    continue;
                }
            }
            i += 1;
        }
    }
    if group_names.is_empty() {
        return Vec::new();
    }
    // url → 组：URL 前近邻 uuid 是组 uuid → 归属；同 URL 多命中取先（长前缀由调用方排序）
    let mut out: Vec<(String, String)> = Vec::new();
    for f in &files {
        let Ok(data) = std::fs::read(f) else { continue };
        let mut i = 0;
        while i + 8 < data.len() {
            if &data[i..i + 4] == b"http" {
                let mut end = i;
                while end < data.len() && (data[end] > 0x20 && data[end] < 0x7f) && data[end] != b'"' {
                    end += 1;
                }
                let url = String::from_utf8_lossy(&data[i..end]).trim().to_string();
                if let Some(u) = uuid_re(&data, i, 100) {
                    if let Some(name) = group_names.get(&u) {
                        let nu = normalize_url(&url);
                        if !nu.is_empty() && !out.iter().any(|(x, _)| *x == nu) {
                            out.push((nu, name.clone()));
                        }
                    }
                }
                i = end;
                continue;
            }
            i += 1;
        }
    }
    out.sort_by_key(|(u, _)| std::cmp::Reverse(u.len()));
    out
}

/// 从书签文件提取「标签组」成员映射'''
assert src.count(anchor) == 1
src = src.replace(anchor, new_fn)

# 2) collect_chromium_tabs 的书签参数 → 通用外部映射参数
old = '''fn collect_chromium_tabs(
    sessions_dir: std::path::PathBuf,
    bookmarks_file: Option<std::path::PathBuf>,
    browser: &str,
    out: &mut Vec<BrowserTab>,
) -> usize {
    let Ok(dirs) = std::fs::read_dir(&sessions_dir) else {
        return 0;
    };
    // 书签里的标签组映射（url → 组名），来源见 collect_tab_group_bookmarks
    let tab_group_bookmarks: Vec<(String, String)> = bookmarks_file
        .and_then(|p| collect_tab_group_bookmarks(&p).ok())
        .unwrap_or_default();'''
new = '''fn collect_chromium_tabs(
    sessions_dir: std::path::PathBuf,
    bookmarks_file: Option<std::path::PathBuf>,
    sync_dir: Option<std::path::PathBuf>,
    browser: &str,
    out: &mut Vec<BrowserTab>,
) -> usize {
    let Ok(dirs) = std::fs::read_dir(&sessions_dir) else {
        return 0;
    };
    // 标签组成员外部来源（url → 组名）：保存的标签组同步库 + 书签「标签组」文件夹
    let mut tab_group_bookmarks = sync_dir
        .map(|d| extract_sync_tab_groups(&d))
        .unwrap_or_default();
    if let Some(p) = bookmarks_file {
        if let Ok(m) = collect_tab_group_bookmarks(&p) {
            for (u, g) in m {
                if !tab_group_bookmarks.iter().any(|(x, _)| *x == u) {
                    tab_group_bookmarks.push((u, g));
                }
            }
        }
        tab_group_bookmarks.sort_by_key(|(u, _)| std::cmp::Reverse(u.len()));
    }'''
assert src.count(old) == 1
src = src.replace(old, new)

# 3) 调用点传 sync dir
old = '''                count += collect_chromium_tabs(
                    pd.join("Sessions"),
                    Some(pd.join("Bookmarks")),
                    browser,
                    &mut items,
                );'''
new = '''                count += collect_chromium_tabs(
                    pd.join("Sessions"),
                    Some(pd.join("Bookmarks")),
                    Some(pd.join("Sync Data").join("LevelDB")),
                    browser,
                    &mut items,
                );'''
assert src.count(old) == 1
src = src.replace(old, new)

io.open(path, "w", encoding="utf-8", newline="\r\n").write(src)
print("patch5 完成")
