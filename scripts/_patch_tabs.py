# -*- coding: utf-8 -*-
"""重构 collect_chromium_tabs：跨文件聚合组映射 + group-home GUID 兜底"""
import io

path = r"D:\source\x-hub\src-tauri\src\commands.rs"
src = io.open(path, encoding="utf-8").read()  # universal newlines → \n

old_loop = '''    files.sort_by_key(|p| std::cmp::Reverse(p.metadata().and_then(|m| m.modified()).ok()));
    for f in files {
        let Ok(data) = std::fs::read(&f) else {
            continue; // 浏览器运行中被独占锁定的最新快照：跳过，尝试次新文件
        };
        if let Some(tabs) = parse_snss_tabs(&data, browser) {
            if !tabs.is_empty() {
                out.extend(tabs);
                return out.len();
            }
        }
    }
    0
}
'''
new_loop = '''    files.sort_by_key(|p| std::cmp::Reverse(p.metadata().and_then(|m| m.modified()).ok()));
    // 组名与 tab→组归属跨全部可读文件累积（cmd27 组 GUID 与 cmd25 tab_id 全局可对齐），
    // 标签页只取「修改时间最新的含导航记录的可读文件」（会话文件增量追加，跨文件 tab 不可比）
    let mut tab_group: std::collections::HashMap<u32, [u8; 16]> =
        std::collections::HashMap::new();
    // 组名表键为 GUID 标准字符串形式（便于与 Tabbit group-home URL 中的 GUID 对齐）
    let mut group_name: std::collections::HashMap<String, String> =
        std::collections::HashMap::new();
    let mut newest_nav: Option<Vec<(u32, String, String)>> = None;
    for f in files {
        let Ok(data) = std::fs::read(&f) else {
            continue; // 浏览器运行中被独占锁定的最新快照：跳过
        };
        if let Some((nav, tg, gn)) = parse_snss_tabs(&data) {
            for (g, name) in gn {
                group_name.entry(guid_to_string(&g)).or_insert(name);
            }
            for (tid, g) in tg {
                tab_group.entry(tid).or_insert(g);
            }
            if newest_nav.is_none() && !nav.is_empty() {
                newest_nav = Some(nav);
            }
        }
    }
    let Some(nav) = newest_nav else {
        return 0;
    };
    let count = nav.len();
    for (tid, url, title) in nav {
        // 关联优先级：cmd25 归属映射 > Tabbit 组主页 URL 自带 GUID（group-home/<guid>）
        let mut group = tab_group
            .get(&tid)
            .and_then(|g| group_name.get(&guid_to_string(g)).cloned())
            .unwrap_or_default();
        if group.is_empty() {
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
        out.push(BrowserTab {
            name: if title.trim().is_empty() {
                url.clone()
            } else {
                title.trim().to_string()
            },
            target: url,
            group,
            browser: browser.to_string(),
        });
    }
    count
}

/// 16 字节二进制 GUID → 标准字符串形式（8-4-4-4-12，前三段小端序还原）
fn guid_to_string(g: &[u8; 16]) -> String {
    let hex = |b: &[u8]| b.iter().map(|x| format!("{:02x}", x)).collect::<String>();
    format!(
        "{}-{}-{}-{}-{}",
        hex(&g[0..4]),
        hex(&g[4..6]),
        hex(&g[6..8]),
        hex(&g[8..10]),
        hex(&g[10..16])
    )
}
'''
assert src.count(old_loop) == 1, "old_loop 匹配 %d 处" % src.count(old_loop)
src = src.replace(old_loop, new_loop)

old_sig = '''/// 解析单个 SNSS 文件，重建「标签页 + 命名标签组」。
/// 记录帧：u16 size + u8 命令类型 + content（content 前 4 字节为 pickle payload_size）。
/// cmd6 UpdateTabNavigation：tab_id u32、index u32、url str8、title str16（UTF-16LE）；
/// cmd25 SetTabGroup：tab_id u32、占位 u32、组 GUID 16 字节；
/// cmd27 SetTabGroupMetadata2：组 GUID 16 字节、名称字符数 u32、名称 UTF-16LE。
fn parse_snss_tabs(data: &[u8], browser: &str) -> Option<Vec<BrowserTab>> {
'''
new_sig = '''/// 解析单个 SNSS 文件，返回（标签页[(tab_id,url,title)], tab→组GUID, 组GUID→名称）。
/// 记录帧：u16 size + u8 命令类型 + content（content 前 4 字节为 pickle payload_size）。
/// cmd6 UpdateTabNavigation：tab_id u32、index u32、url str8、title str16（UTF-16LE）；
/// cmd25 SetTabGroup：tab_id u32、占位 u32、组 GUID 16 字节；
/// cmd27 SetTabGroupMetadata2：组 GUID 16 字节、名称字符数 u32、名称 UTF-16LE。
fn parse_snss_tabs(
    data: &[u8],
) -> Option<(
    Vec<(u32, String, String)>,
    Vec<(u32, [u8; 16])>,
    Vec<([u8; 16], String)>,
)> {
'''
assert src.count(old_sig) == 1, "old_sig 匹配 %d 处" % src.count(old_sig)
src = src.replace(old_sig, new_sig)

# parse_snss_tabs 函数体：改返回结构
old_ret1 = '''    if nav.is_empty() {
        return None;
    }
    Some(
        nav.into_iter()
            .map(|(tid, (_, url, title))| {
                let group = tab_group
                    .get(&tid)
                    .and_then(|g| group_name.get(g))
                    .cloned()
                    .unwrap_or_default();
                BrowserTab {
                    name: if title.trim().is_empty() {
                        url.clone()
                    } else {
                        title.trim().to_string()
                    },
                    target: url,
                    group,
                    browser: browser.to_string(),
                }
            })
            .collect(),
    )
}
'''
new_ret1 = '''    Some((
        nav.into_iter()
            .map(|(tid, (_, url, title))| (tid, url, title))
            .collect(),
        tab_group.into_iter().collect(),
        group_name.into_iter().collect(),
    ))
}
'''
assert src.count(old_ret1) == 1, "old_ret1 匹配 %d 处" % src.count(old_ret1)
src = src.replace(old_ret1, new_ret1)

io.open(path, "w", encoding="utf-8", newline="\r\n").write(src)
print("替换完成")
