# -*- coding: utf-8 -*-
import io
path = r"D:\source\x-hub\src-tauri\src\commands.rs"
src = io.open(path, encoding="utf-8").read()

old = '''    fn walk(node: &serde_json::Value, in_tab_groups: bool, map: &mut Vec<(String, String)>) {
        let Some(children) = node.get("children").and_then(|c| c.as_array()) else {
            return;
        };
        let name = node.get("name").and_then(|n| n.as_str()).unwrap_or("");
        for c in children {
            let cname = c.get("name").and_then(|n| n.as_str()).unwrap_or("");
            let is_folder = c.get("type").and_then(|t| t.as_str()) == Some("folder");
            if in_tab_groups && is_folder {
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
    }'''
new = '''    fn walk(node: &serde_json::Value, map: &mut Vec<(String, String)>) {
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
    }'''
assert src.count(old) == 1, "walk 块匹配 %d" % src.count(old)
src = src.replace(old, new)

old = '''    if let Some(roots) = v.get("roots").and_then(|r| r.as_object()) {
        for (_k, r) in roots {
            if r.is_object() {
                walk(r, false, &mut map);
            }
        }
    }'''
new = '''    if let Some(roots) = v.get("roots").and_then(|r| r.as_object()) {
        for (_k, r) in roots {
            if r.is_object() {
                walk(r, &mut map);
            }
        }
    }'''
assert src.count(old) == 1, "roots 调用匹配 %d" % src.count(old)
src = src.replace(old, new)

io.open(path, "w", encoding="utf-8", newline="\r\n").write(src)
print("patch4 完成")
