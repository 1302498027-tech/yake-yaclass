# -*- coding: utf-8 -*-
"""
生成云端公开分享版 site/index.html（基于最新 index.html 加工）：
1) file:/// 本地报告链接 → localfile:// 占位（云端无这些文件）
2) 数据源 path / 报告链接中的本机路径脱敏
3) 注入底部快照提示条（含数据生成时间）
用法：python make_site.py（需先运行 build.py）
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE, "index.html"), "r", encoding="utf-8") as f:
    html = f.read()

# 1) 本地文件链接占位
html = html.replace('"file:///', '"localfile://')

# 2a) 数据源目录脱敏（payload JSON 内）
html = re.sub(r'"path": "[^"]*outputs"', '"path": "本地目录（仅作者电脑可见）"', html)

# 2b) 报告链接脱敏（localfile 链接内含本机路径）
html = re.sub(r'"localfile:[^"]*"', '"localfile://已屏蔽"', html)

# 2c) 兜底：扫描任何残余的本机绝对路径
html = re.sub(r"(localfile:[^\"<>]*)(C:[/\\]+Users[^\"<>]*)", r"\1已屏蔽", html)

# 3) 底部快照提示条
m = re.search(r'"generated": "([^"]+)"', html)
gen = m.group(1) if m else ""
banner = ('<div style="position:fixed;bottom:0;left:0;right:0;z-index:80;'
          'background:rgba(47,123,246,.95);color:#fff;font-size:12.5px;text-align:center;'
          'padding:7px 16px">这是 芽课学习台的数据快照（数据生成于 ' + gen +
          '，每天 21:40 自动更新），报告文件仅存于作者本地</div>')
html = html.replace("</body>", banner + "</body>")

site_dir = os.path.join(BASE, "site")
os.makedirs(site_dir, exist_ok=True)
with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

# 4) 科普站并入分享版（site/pm/...，侧边栏链接公开链接里也可直接用）
import shutil
pm_src = os.path.join(BASE, "pm")
pm_dst = os.path.join(site_dir, "pm")
n = 0
if os.path.isdir(pm_src):
    os.makedirs(pm_dst, exist_ok=True)
    for root, dirs, files in os.walk(pm_src):
        rel = os.path.relpath(root, pm_src)
        dst_root = os.path.normpath(os.path.join(pm_dst, rel)) if rel != "." else pm_dst
        os.makedirs(dst_root, exist_ok=True)
        for fn in files:
            if fn.startswith("_"):
                continue
            shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))
            n += 1

leftover = len(re.findall(r"C:[/\\]+Users", html))
print("分享版已生成:", os.path.join(site_dir, "index.html"))
print("科普站已并入: site/pm/ (%d 个文件)" % n)
print("残余本机路径引用:", leftover, "（应为 0）")
