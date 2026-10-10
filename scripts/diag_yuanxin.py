# -*- coding: utf-8 -*-
"""诊断：垣信NMC 组在哪个环节丢失"""
import os, glob, struct, sys
sys.stdout.reconfigure(encoding='utf-8')

LOCAL = os.path.expandvars(r"%LOCALAPPDATA%\Tabbit Browser\User Data")

# ---------- SNSS 解析（cmd6/cmd25/cmd27） ----------
def read_str8(d, i):
    n = struct.unpack_from("<I", d, i)[0]; i += 4
    s = d[i:i+n].decode("utf-8", "replace"); i += (n + 3) & ~3
    return s, i

def read_str16(d, i):
    n = struct.unpack_from("<I", d, i)[0]; i += 4
    s = d[i:i+2*n].decode("utf-16-le", "replace"); i += (2*n + 3) & ~3
    return s, i

def parse_snss(path):
    try:
        d = open(path, "rb").read()
    except PermissionError:
        return None  # 锁定
    nav, tg, gn = [], {}, {}
    i = 8
    while i + 4 <= len(d):
        (sz,) = struct.unpack_from("<H", d, i)
        cmd = d[i+2]
        body = d[i+3:i+2+sz]
        j = i + 2 + sz
        if cmd == 6 and len(body) > 8:
            ps = struct.unpack_from("<I", body, 0)[0]
            if ps + 4 <= len(body):
                c = body[4:4+ps]
                if len(c) >= 16:
                    tab_id, idx = struct.unpack_from("<II", c, 0)
                    k = 8
                    try:
                        url, k = read_str8(c, k)
                        title, k = read_str16(c, k)
                        nav.append((tab_id, url, title))
                    except Exception:
                        pass
        elif cmd == 25 and len(body) > 8:
            ps = struct.unpack_from("<I", body, 0)[0]
            if ps + 4 <= len(body):
                c = body[4:4+ps]
                if len(c) >= 20:
                    tab_id = struct.unpack_from("<I", c, 0)[0]
                    guid = c[8:24]
                    tg[tab_id] = guid
        elif cmd == 27 and len(body) > 8:
            ps = struct.unpack_from("<I", body, 0)[0]
            if ps + 4 <= len(body):
                c = body[4:4+ps]
                if len(c) >= 16:
                    guid = c[0:16]
                    (nlen,) = struct.unpack_from("<I", c, 16)
                    try:
                        name = c[20:20+2*nlen].decode("utf-16-le", "replace")
                        gn[guid] = name
                    except Exception:
                        pass
        i = j
    return nav, tg, gn

files = []
for prof in os.listdir(LOCAL):
    sd = os.path.join(LOCAL, prof, "Sessions")
    if os.path.isdir(sd):
        for f in glob.glob(os.path.join(sd, "*")):
            files.append((os.path.getmtime(f), f))
files.sort(reverse=True)

all_gn, all_tg = {}, {}
newest_nav = None
for mt, f in files:
    r = parse_snss(f)
    if r is None:
        print(f"[锁定跳过] {os.path.basename(f)}")
        continue
    nav, tg, gn = r
    for g, n in gn.items():
        all_gn.setdefault(g, n)
    for t, g in tg.items():
        all_tg.setdefault(t, g)
    if newest_nav is None and nav:
        newest_nav = nav
    print(f"[读取] {os.path.basename(f)}: nav={len(nav)} tg={len(tg)} gn={len(gn)}")

print("\n== SNSS cmd27 组名 ==")
yuanxin_guids = []
for g, n in all_gn.items():
    mark = "  <<<" if "垣信" in n else ""
    print(f"  {n!r}  guid={g.hex()}{mark}")
    if "垣信" in n:
        yuanxin_guids.append(g)

print("\n== cmd25 tab→组 中垣信NMC 的 tab ==")
tabs_in_group = [t for t, g in all_tg.items() if g in yuanxin_guids]
print(f"  {len(tabs_in_group)} 个 tab: {tabs_in_group}")

if newest_nav:
    print("\n== 最新可读快照导航条数 ==", len(newest_nav))
    hit = [(t, u) for t, u, ti in newest_nav if t in tabs_in_group]
    print("  其中属于垣信NMC 的:", hit)
    # group-home URL
    gh = [u for t, u, ti in newest_nav if "group-home" in u]
    print("  group-home URL:", gh)

# ---------- 同步库原始特征扫描 ----------
print("\n== 同步库 ==")
sd = os.path.join(LOCAL, "Default", "Sync Data", "LevelDB")
names = {}   # uuid str -> name
urls = []    # (uuid, url)
def uuid_at(data, end, back):
    start = max(0, end-back)
    seg = data[start:end]
    best = None
    for i in range(len(seg)-35):
        s = seg[i:i+36]
        ok = all((s[j] == 0x2D if j in (8,13,18,23) else chr(s[j]) in "0123456789abcdefABCDEF") for j in range(36))
        if ok:
            best = s.decode()
    return best

for f in glob.glob(os.path.join(sd, "*")):
    if not os.path.isfile(f):
        continue
    try:
        data = open(f, "rb").read()
    except PermissionError:
        print(f"  [锁定] {os.path.basename(f)}")
        continue
    i = 0
    while i + 3 < len(data):
        b = data[i]
        if 0xE4 <= b <= 0xE9 and i+2 < len(data) and (data[i+1] & 0xC0) == 0x80:
            end, chars, cjk = i, 0, 0
            while end < len(data) and chars < 24:
                bb = data[end]
                if 0xE4 <= bb <= 0xE9 and end+2 < len(data) and (data[end+1] & 0xC0) == 0x80 and (data[end+2] & 0xC0) == 0x80:
                    end += 3; chars += 1; cjk += 1
                elif chr(bb).isascii() and bb != 0 and chr(bb).isalnum():
                    end += 1; chars += 1
                else:
                    break
            if chars >= 2 and cjk >= 1 and end+1 < len(data) and data[end] == 0x18 and data[end+1] <= 9:
                u = uuid_at(data, i, 120)
                if u:
                    nm = data[i:end].decode("utf-8", "replace")
                    names.setdefault(u, nm)
                    if "垣信" in nm:
                        print(f"  [组名命中] {nm!r} uuid={u} file={os.path.basename(f)}")
                i = end
                continue
        i += 1
    # URL 扫描
    i = 0
    while i + 8 < len(data):
        if data[i:i+4] == b"http":
            e = i
            while e < len(data) and 0x20 < data[e] < 0x7f and data[e] != 0x22:
                e += 1
            url = data[i:e].decode("ascii", "replace")
            u = uuid_at(data, i, 100)
            if u and u in names:
                urls.append((u, url))
            i = e
        else:
            i += 1

print("\n== 同步库组名总数 ==", len(names))
yx = [u for u, n in names.items() if "垣信" in n]
print("垣信NMC uuid:", yx, names.get(yx[0]) if yx else None)
if yx:
    yurls = [url for u, url in urls if u == yx[0]]
    print(f"同步库中归属该组的 URL {len(yurls)} 条:")
    for u in yurls:
        print("   ", u)
    # 这些 URL 是否出现在最新可读快照
    if newest_nav:
        urls_set = {u2 for _, u2, _ in newest_nav}
        for u in yurls:
            print(f"  在最新快照? {u[:60]} -> {u in urls_set}")
