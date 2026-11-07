# -*- coding: utf-8 -*-
"""
芽课 · 数据源同步（从线上站点拉回全部历史日报）

背景
  早期 build.py 依赖 WorkBuddy 的 automation-*/outputs 目录，
  但那些任务在 2026-09-19 之后已停止产出。
  真正在跑的管线是 CloudBase 云函数 yake-daily：每天 21:00
  用 GLM 生成三份日报 → 构建 → 上传静态托管，并把全部历史
  写进站点上的 data/manifest.json。

  本脚本做云函数做的事：从站点把 reports/**/*.md 全部拉回本地
  outputs/<key>/ 目录，让 build.py 能照常解析构建。

用法
  python sync_sources.py           # 增量同步（已有文件跳过）
  python sync_sources.py --force   # 强制重下

同步后再跑 build.py，即可得到含全部历史的工作台。
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://yake-pm-learn-d8gj30hst985e4f14-1491333553.tcloudbaseapp.com"
OUT_ROOT = os.path.join(BASE, "outputs")

# 站点目录 → 本地目录（与 build.py 的 SOURCES key 对应）
KEY_MAP = {"deep": "deep", "learn": "learn", "journal": "journal"}


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "yake-sync/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_manifest():
    url = SITE + "/data/manifest.json"
    try:
        raw = http_get(url, timeout=30)
    except Exception as e:
        raise SystemExit("清单读取失败：%s\n（确认网络可访问 %s）" % (e, SITE))
    data = json.loads(raw.decode("utf-8"))
    files = data.get("files") or []
    out = []
    for item in files:
        if isinstance(item, dict):
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            mt = item.get("mtime")
        else:
            rel, mt = str(item).replace("\\", "/").lstrip("/"), None
        if rel.endswith(".md") and ".." not in rel:
            out.append((rel, mt))
    return out


def fetch_one(args):
    rel, mtime, force = args
    key = rel.split("/")[0]
    local_key = KEY_MAP.get(key)
    if not local_key:
        return ("skip", rel)
    dest = os.path.join(OUT_ROOT, local_key, os.path.basename(rel))
    if os.path.exists(dest) and not force:
        return ("have", rel)
    url = SITE + "/reports/" + urllib.parse.quote(rel, safe="/")
    for attempt in range(3):
        try:
            body = http_get(url, timeout=60)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(body)
            if mtime:
                try:
                    os.utime(dest, (int(mtime), int(mtime)))
                except Exception:
                    pass
            return ("got", rel)
        except Exception:
            time.sleep(1 + attempt)
    return ("fail", rel)


def main():
    force = "--force" in sys.argv
    items = load_manifest()
    print("清单中 .md 文件：%d 个" % len(items))
    if not items:
        raise SystemExit("清单里没有 .md 文件，请检查站点 manifest。")

    jobs = [(rel, mt, force) for rel, mt in items]
    stat = {"got": 0, "have": 0, "fail": 0, "skip": 0}
    failed = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r, rel in ex.map(fetch_one, jobs):
            stat[r] += 1
            if r == "fail":
                failed.append(rel)

    print("下载 %(got)d｜已存在 %(have)d｜跳过 %(skip)d｜失败 %(fail)d" % stat)
    if failed:
        print("\n失败的 %d 个（可重跑本脚本重试）：" % len(failed))
        for f in failed[:10]:
            print("  ", f)

    # 汇总各目录
    print("\n本地 outputs/ 现状：")
    for key in sorted(KEY_MAP.values()):
        d = os.path.join(OUT_ROOT, key)
        n = len([f for f in os.listdir(d) if f.endswith(".md")]) if os.path.isdir(d) else 0
        print("  %-8s %d 份" % (key, n))

    print("\n下一步：python build.py")


if __name__ == "__main__":
    main()
