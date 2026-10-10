# -*- coding: utf-8 -*-
import io, re

P = r"D:\source\x-hub\src-tauri\src\commands.rs"
with io.open(P, "r", encoding="utf-8", newline="") as f:
    src = f.read()

orig = src

# ---- 补丁1：extract_sync_tab_groups 组名解析支持 CJK+ASCII 混合（如 垣信NMC）----
old_name = """                // 尝试读一个 2~24 字的 CJK 串
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
                {"""
new_name = """                // 尝试读一个 2~24 字的组名：CJK 为主，允许混合 ASCII 字母数字
                //（如「垣信NMC」），此前纯 CJK 检测遇到 ASCII 即停导致整组漏检
                let mut end = i;
                let mut chars = 0;
                let mut cjk = 0;
                while end < data.len() && chars < 24 {
                    let b = data[end];
                    if b >= 0xE4 && b <= 0xE9 && end + 2 < data.len()
                        && data[end + 1] & 0xC0 == 0x80 && data[end + 2] & 0xC0 == 0x80
                    {
                        end += 3;
                        chars += 1;
                        cjk += 1;
                    } else if b.is_ascii_alphanumeric() {
                        end += 1;
                        chars += 1;
                    } else {
                        break;
                    }
                }
                if chars >= 2
                    && cjk >= 1
                    && end + 1 < data.len()
                    && data[end] == 0x18
                    && data[end + 1] <= 9
                {"""
assert old_name in src, "patch1 anchor not found"
src = src.replace(old_name, new_name, 1)

# ---- 补丁2：scan_browser_tabs 去重改为「同浏览器同 URL 保留已归组条目优先」----
old_dedup = """    // 同浏览器同网址去重（同标签在多个快照文件重复出现），跨浏览器保留
    let mut seen: std::collections::HashSet<(String, String)> = std::collections::HashSet::new();
    items.retain(|t| seen.insert((t.browser.clone(), t.target.to_lowercase())));"""
new_dedup = """    // 同浏览器同网址去重（同标签在多个快照文件重复出现），跨浏览器保留；
    // 重复条目中优先保留已归组的（否则先出现的未分组条目会把组内同 URL 标签吞掉）
    let mut best: std::collections::HashMap<(String, String), usize> =
        std::collections::HashMap::new();
    let mut keep = vec![true; items.len()];
    for (idx, t) in items.iter().enumerate() {
        let key = (t.browser.clone(), t.target.to_lowercase());
        match best.get(&key) {
            Some(&prev) => {
                let prev_grouped = !items[prev].group.is_empty();
                let cur_grouped = !t.group.is_empty();
                if cur_grouped && !prev_grouped {
                    keep[prev] = false;
                    best.insert(key, idx);
                } else {
                    keep[idx] = false;
                }
            }
            None => {
                best.insert(key, idx);
            }
        }
    }
    let mut kept_items: Vec<BrowserTab> = Vec::new();
    for (idx, t) in items.drain(..).enumerate() {
        if keep[idx] {
            kept_items.push(t);
        }
    }
    items = kept_items;"""
assert old_dedup in src, "patch2 anchor not found"
src = src.replace(old_dedup, new_dedup, 1)

if src == orig:
    print("no change")
else:
    with io.open(P, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("patched OK")
