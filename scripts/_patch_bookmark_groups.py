# -*- coding: utf-8 -*-
import io

P = r"D:\source\x-hub\src-tauri\src\commands.rs"
with io.open(P, "r", encoding="utf-8", newline="") as f:
    src = f.read()

old = """    let mut map: Vec<(String, String)> = Vec::new();
    fn walk(node: &serde_json::Value, map: &mut Vec<(String, String)>) {
        let Some(children) = node.get("children").and_then(|c| c.as_array()) else {
            return;
        };
        let name = node.get("name").and_then(|n| n.as_str()).unwrap_or("");
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
        for c in children {
            let cname = c.get("name").and_then(|n| n.as_str()).unwrap_or("");
            let is_folder = c.get("type").and_then(|t| t.as_str()) == Some("folder");
            if name == "标签组" && is_folder {
                // 该文件夹即一个保存的标签组：其下所有 URL 归入组名
                collect_urls(c, map, cname);
            } else {
                walk(c, map);
            }
        }
    }
    if let Some(roots) = v.get("roots").and_then(|r| r.as_object()) {
        for (_k, r) in roots {
            if r.is_object() {
                walk(r, &mut map);
            }
        }
    }"""

new = """    let mut map: Vec<(String, String)> = Vec::new();
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
    fn walk(node: &serde_json::Value, map: &mut Vec<(String, String)>) {
        let Some(children) = node.get("children").and_then(|c| c.as_array()) else {
            return;
        };
        let name = node.get("name").and_then(|n| n.as_str()).unwrap_or("");
        for c in children {
            let cname = c.get("name").and_then(|n| n.as_str()).unwrap_or("");
            let is_folder = c.get("type").and_then(|t| t.as_str()) == Some("folder");
            if name == "标签组" && is_folder {
                // 该文件夹即一个保存的标签组：其下所有 URL 归入组名
                collect_urls(c, map, cname);
            } else {
                walk(c, map);
            }
        }
    }
    // 第二遍：垣信NMC 等组的书签文件夹不一定同步在「标签组」目录下
    //（实测还出现在 bookmark_bar/常用标签页/ 与 other/ 下），
    // 任何含直接 URL 子项的文件夹都按其文件夹名作为组名兜底（不覆盖第一遍已归属的 URL），
    // 子树中遇到「标签组」则跳过（已在第一遍按保存组精确处理）
    fn walk_other(node: &serde_json::Value, map: &mut Vec<(String, String)>) {
        let name = node.get("name").and_then(|n| n.as_str()).unwrap_or("");
        if name == "标签组" {
            return;
        }
        if let Some(children) = node.get("children").and_then(|c| c.as_array()) {
            for c in children {
                let is_url = c.get("type").and_then(|t| t.as_str()) == Some("url");
                let is_folder = c.get("type").and_then(|t| t.as_str()) == Some("folder");
                if is_folder {
                    walk_other(c, map);
                } else if is_url {
                    collect_urls(c, map, name);
                }
            }
        }
    }
    if let Some(roots) = v.get("roots").and_then(|r| r.as_object()) {
        for (_k, r) in roots {
            if r.is_object() {
                walk(r, &mut map);
            }
        }
        for (_k, r) in roots {
            if r.is_object() {
                walk_other(r, &mut map);
            }
        }
    }"""

assert old in src, "anchor not found"
src = src.replace(old, new, 1)

with io.open(P, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("patched OK")
