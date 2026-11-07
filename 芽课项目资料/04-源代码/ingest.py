# -*- coding: utf-8 -*-
"""
芽课 · 素材包索引器（P0）
扫描 桌面/素材包 下的 md，生成 payload.json 供工作台渲染。

设计原则：
  1. 只读，绝不写任何 md（PRD §5.1）
  2. 零第三方依赖，标准库即可
  3. 字段契约见 PRD §6.5
  4. 我的复述/反驳/落地三区块存在即计入 evidence，AI 无权改写

用法：python ingest.py [--out 输出路径]
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "素材包")
ROOT = os.environ.get("YAKE_PACK_ROOT", DEFAULT_ROOT)

# 领域配置：文件夹 → 中文领域名 / 排期 / 权重 / 总格数
DOMAINS = [
    ("01_财税", "财税", "MO,TU,WE,TH,FR", "07:30", 0.4, 16),
    ("02_能力与边界", "能力边界", "DAILY", "20:00", 0.8, 16),
    ("03_商业", "商业", "TU,TH,SA", "07:40", 0.4, 16),
    ("04_需求与判断", "需求判断", "DAILY", "20:10", 0.8, 16),
    ("05_AI-Agent", "AI-Agent", "DAILY", "07:00", 1.0, 16),
    ("06_国际", "国际", "WE,SU", "07:50", 0.3, 15),
    ("07_分析与度量", "分析度量", "DAILY", "20:20", 0.7, 16),
    ("08_健康", "健康", "DAILY", "07:20", 0.3, 16),
    ("09_计算机", "计算机", "DAILY", "07:10", 0.9, 18),
    ("10_面试", "面试", "DAILY", "20:30", 0.7, 16),
    ("11_文档与表达", "文档表达", "DAILY", "20:40", 0.6, 16),
    ("12_学习路径", "学习路径", "DAILY", "20:50", 0.5, 16),
]
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]
RRULE_CN = {"MO": "一", "TU": "二", "WE": "三", "TH": "四", "FR": "五", "SA": "六", "SU": "日"}


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_front(text):
    """极简 YAML frontmatter：只取标量与列表，够用即可。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head = text[3:end]
    body = text[end + 4:]
    data, key = {}, None
    for line in head.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") or line.startswith("- "):
            if key:
                v = line.strip()[1:].strip().strip('"').strip("'")
                v = v.replace("[[", "").replace("]]", "")
                data.setdefault(key, [])
                if isinstance(data[key], list):
                    data[key].append(v)
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val == "":
                data[key] = []
            else:
                data[key] = val.strip('"').strip("'")
    return data, body


def section(body, title_kw):
    """取某个二级标题下的内容，直到下一个二级标题。"""
    lines = body.splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            on = title_kw in ln
            continue
        if on:
            out.append(ln)
    return "\n".join(out).strip()


def bullets(text):
    return [re.sub(r"^-\s*\[[ x]\]\s*", "", l).strip()
            for l in text.splitlines() if re.match(r"^\s*-\s*\[[ x]\]", l)]


def one_liner(body):
    m = re.search(r"\*\*解决什么问题\*\*[：:]\s*(.+)", body)
    if m:
        return m.group(1).strip()
    for ln in body.splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", ">", "-", "|", "!", "```", "**")):
            return s[:120]
    return ""


def plan_desc(rrule, hhmm):
    if rrule == "DAILY":
        return "每天 " + hhmm
    days = "、".join("周" + RRULE_CN.get(x, x) for x in rrule.split(","))
    return days + " " + hhmm


def due_dates_back(rrule, hhmm, today, lookback=14):
    """返回最近 lookback 天内所有排期日期（倒序）。"""
    hour, minute = (int(x) for x in hhmm.split(":"))
    allow = None if rrule == "DAILY" else set(rrule.split(","))
    res = []
    for i in range(lookback + 1):
        d = today - timedelta(days=i)
        if allow and ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][d.weekday()] not in allow:
            continue
        res.append(d)
    return res, hour, minute


def parse_progress(path):
    """从 00_学习进度.md 读每个领域的进度与关卡名。"""
    info = {}
    if not os.path.exists(path):
        return info
    text = read(path)
    for m in re.finditer(r"^### (\S+)\s*\n\n- 下一个格子：\*\*(\d+)\*\*\s*\n- 总格数：(\d+)\s*\n- 已讲：(\d+)\s*\n- 最后更新：([^\n]+)", text, re.M):
        dom, nxt, total, done, upd = m.groups()
        info[dom] = {"next": int(nxt), "total": int(total), "done": int(done), "last": upd.strip()}
    # 每格标题：- [x] 3. 结构化输出…  ✅ 2026-11-03
    grids = {}
    cur = None
    for ln in text.splitlines():
        m = re.match(r"^### (\S+)\s*$", ln)
        if m:
            cur = m.group(1)
            grids[cur] = []
            continue
        m = re.match(r"^- \[([ x])\] (\d+)\. (.+?)(?:\s+✅\s+(\d{4}-\d{2}-\d{2}))?$", ln)
        if m and cur:
            grids[cur].append({"grid": int(m.group(2)), "name": m.group(3).strip(),
                               "done": m.group(1) == "x", "date": m.group(4) or ""})
    for d, g in grids.items():
        if d in info:
            info[d]["grids"] = g
    return info


def main():
    out_path = os.path.join(BASE, "..", "05-工作台成品", "payload.json")
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
    now = datetime.now()
    today = now.date()

    entries, concepts, progress, tasks = [], [], [], []
    total_chars, total_pdf = 0, 0
    prog = parse_progress(os.path.join(ROOT, "00_学习进度.md"))

    for folder, domain, rrule, hhmm, weight, grid_total in DOMAINS:
        dpath = os.path.join(ROOT, folder)
        dom_entries, dom_concepts = [], []
        if os.path.isdir(dpath):
            for dirpath, _, files in os.walk(dpath):
                for fn in files:
                    if not fn.endswith(".md"):
                        continue
                    p = os.path.join(dirpath, fn)
                    text = read(p)
                    fm, body = parse_front(text)
                    typ = str(fm.get("type", ""))
                    if typ == "日记":
                        gnum = 0
                        try:
                            gnum = int(str(fm.get("grid", 0)))
                        except ValueError:
                            gnum = 0
                        doing = bullets(section(body, "今日动手") or section(body, "今日动作"))
                        done_n = body.count("- [x]")
                        chars = len(body)
                        total_chars += chars
                        dom_entries.append({
                            "date": str(fm.get("date", "")),
                            "domain": domain,
                            "chapter": str(fm.get("chapter", "")),
                            "grid": gnum,
                            "gridTotal": grid_total,
                            "gridName": str(fm.get("grid_name", "")),
                            "file": fn,
                            "path": p.replace("\\", "/"),
                            "chars": chars,
                            "sources": int(str(fm.get("sources", 0)) or 0),
                            "checksTotal": len(doing),
                            "checksDone": done_n,
                            "doing": doing,
                            "brief": one_liner(body),
                            "read": str(fm.get("read", "")),
                            "digest": str(fm.get("digest", "")),
                            "applied": int(str(fm.get("applied", 0)) or 0),
                            "verdict": str(fm.get("verdict", "")),
                            "hasReflect": "## 我的复述" in body,
                            "weight": weight,
                        })
                    elif typ == "concept":
                        ups = 1
                        try:
                            ups = int(str(fm.get("updates", 1)))
                        except ValueError:
                            ups = 1
                        dom_concepts.append({
                            "name": fn[:-3],
                            "domain": domain,
                            "chapter": str(fm.get("chapter", "")),
                            "firstSeen": str(fm.get("first_seen", "")),
                            "updates": ups,
                            "path": p.replace("\\", "/"),
                        })
                # PDF 数
                if dirpath.endswith("PDF"):
                    total_pdf += len([f for f in files if f.lower().endswith(".pdf")])

        dom_entries.sort(key=lambda x: x["date"])
        entries.extend(dom_entries)
        concepts.extend(dom_concepts)

        # 进度
        pinfo = prog.get(domain, {})
        done = pinfo.get("done", len([e for e in dom_entries if e["digest"]]))
        passed = [g for g in pinfo.get("grids", []) if g["done"]]
        # 健康度：最近一个应产出日 vs 最新产出日
        due, hour, minute = due_dates_back(rrule, hhmm, today)
        last_ok = dom_entries[-1]["date"] if dom_entries else ""
        overdue_days, status = 0, "ok"
        for d in due:
            slot = datetime(d.year, d.month, d.day, hour, minute)
            if slot > now:
                continue  # 今天还没到点，不算应产出
            if not last_ok or last_ok < d.isoformat():
                overdue_days = (today - d).days
                status = "fail" if overdue_days else "due"
                break
        tasks.append({
            "domain": domain,
            "folder": folder,
            "plan": plan_desc(rrule, hhmm),
            "lastOk": last_ok,
            "grids": f'{done}/{grid_total}',
            "done": done,
            "total": grid_total,
            "overdueDays": overdue_days,
            "gapDays": ((today - datetime.strptime(last_ok, "%Y-%m-%d").date()).days if last_ok else 0),
            "status": status,
            "entries": len(dom_entries),
            "concepts": len(dom_concepts),
            "weight": weight,
        })

        progress.append({
            "domain": domain, "folder": folder, "done": done, "total": grid_total,
            "next": pinfo.get("next", done + 1),
            "last": pinfo.get("last", "—"),
            "weight": weight,
            "passsed": passed,
        })

    # 证据分层
    l1 = [e for e in entries if e["digest"]]
    l2 = [e for e in entries if e["applied"] > 0 or e["checksDone"] > 0]
    l3 = [e for e in entries if e["applied"] >= 3]
    moc = 0
    for folder, _d, _r, _h, _w, _g in DOMAINS:
        moc += len([f for f in os.listdir(os.path.join(ROOT, folder))
                    if f.startswith("MOC-")]) if os.path.isdir(os.path.join(ROOT, folder)) else 0
    stats = {"l0": len(entries), "l1": len(l1), "l2": len(l2), "l3": len(l3),
             "notes": len(entries) + len(concepts) + moc, "entries": len(entries),
             "concepts": len(concepts), "moc": moc,
             "chars": total_chars, "pdf": total_pdf,
             "checksTotal": sum(e["checksTotal"] for e in entries),
             "checksDone": sum(e["checksDone"] for e in entries)}

    # 今日 3 件事
    recent_cut = (today - timedelta(days=3)).isoformat()
    cand = [e for e in entries if e["date"] >= recent_cut and not e["digest"]]
    cand.sort(key=lambda e: (e["weight"], e["date"]), reverse=True)
    pick_read = cand[0] if cand else (entries[-1] if entries else None)

    doing = None
    if pick_read and pick_read["doing"]:
        doing = {"domain": pick_read["domain"], "date": pick_read["date"],
                 "items": pick_read["doing"][:3], "file": pick_read["file"]}

    # 复习：概念按 1/3/7/21 间隔到期
    review = None
    for c in sorted(concepts, key=lambda x: x["firstSeen"]):
        if not c["firstSeen"]:
            continue
        try:
            d0 = datetime.strptime(c["firstSeen"], "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (today - d0).days
        if age in (1, 3, 7, 21) or (age > 21 and age % 21 == 0):
            review = {"name": c["name"], "domain": c["domain"], "age": age}
            break
    if not review and concepts:
        c = max(concepts, key=lambda x: x["updates"])
        review = {"name": c["name"], "domain": c["domain"], "age": 0}

    overdue = [t for t in tasks if t["overdueDays"] > 0 or t["status"] == "due"]
    payload = {
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "pack": {"notes": stats["notes"], "entries": stats["entries"], "concepts": stats["concepts"],
                 "moc": stats["moc"], "chars": stats["chars"], "pdf": stats["pdf"]},
        "stats": stats,
        "progress": progress,
        "entries": entries,
        "concepts": concepts,
        "tasks": sorted(tasks, key=lambda t: -t["overdueDays"]),
        "today3": {
            "read": pick_read,
            "doing": doing,
            "review": review,
        },
        "overdue": [{"domain": t["domain"], "days": t["overdueDays"], "gapDays": t["gapDays"], "lastOk": t["lastOk"], "plan": t["plan"]} for t in overdue],
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"素材包          {ROOT}")
    print(f"日记 {len(entries)} 篇 / 概念 {len(concepts)} 个 / PDF {total_pdf} 份 / {total_chars} 字符")
    print(f"证据            L0={stats['l0']} L1={stats['l1']} L2={stats['l2']} L3={stats['l3']}")
    print(f"动手项          勾了 {stats['checksDone']} / 共 {stats['checksTotal']}")
    print(f"今日必读        {pick_read['domain'] if pick_read else '—'} · 第 {pick_read['grid'] if pick_read else '-'} 格 · {pick_read['gridName'][:30] if pick_read else ''}")
    print(f"今日动手        {doing['items'][0][:40] if doing and doing['items'] else '—'}")
    print(f"今日复习        {review['name'] if review else '—'}")
    tail = ("：" + "、".join("%s(%d天)" % (x["domain"], x["overdueDays"]) for x in overdue)) if overdue else ""
    print(f"断供            {len(overdue)} 个{tail}")
    print(f"输出            {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
