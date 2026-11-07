# -*- coding: utf-8 -*-
"""
M1 站点骨架生成器：把每日简报数据构建成「PM 入门科普站」
输出（pm-site/）：
  index.html          首页（今日速览 + 最新期数 + 分类入口）
  map.html            知识地图（分类筛选 + 关键词搜索）
  quiz.html           今日自测（主动回忆式，M2 换 AI 选择题）
  k/<id>.html         知识点详情页（每知识点一页，SEO 友好）
  assets/site.css     设计系统（亮色为主 + 冰蓝强调，与工作台同源）
  assets/site.js      前端交互（筛选/搜索/已读与自测进度 localStorage）
  data.json           站点数据（含能力边界）
用法：python build_site.py
"""
import io
import json
import os
import re
import shutil
import sys


BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import build  # noqa: E402

OUT = os.path.join(BASE, "pm-site")
ASSETS = os.path.join(OUT, "assets")
KDIR = os.path.join(OUT, "k")

CATS = ["AI前沿", "AI资讯", "行业资讯", "政策法规", "财税政策", "财税知识", "数据统计", "数据库", "SQL", "Python", "PM思考"]
CAT_META = {
    "AI前沿": ("#2f7bf6", "大模型能力边界、Agent、RAG 等前沿认知"),
    "AI资讯": ("#7c3aed", "AI 行业动态与产品发布"),
    "行业资讯": ("#d4537e", "内容、文化、消费行业的真实案例"),
    "政策法规": ("#0f766e", "法律法规、监管规定、司法规则的产品侧影响"),
    "财税政策": ("#f59e0b", "影响 B 端业务与商业化的政策变化"),
    "财税知识": ("#e11d48", "发票、税种、成本结构等必修常识"),
    "数据统计": ("#0ea5a4", "指标口径、留存、AB 实验与数据陷阱"),
    "数据库": ("#64748b", "表/字段/主键等数据存储认知"),
    "SQL": ("#0284c7", "看得懂取数逻辑与简单查询"),
    "Python": ("#f97316", "知道能解决什么问题，不要求写项目"),
    "PM思考": ("#9333ea", "把当天所学落到实习动作上"),
}
TYPE_TAG = {"deep": ("深度版", "#1d5fd0"), "learn": ("轻量版", "#38bdf8"), "journal": ("技术版", "#8b5cf6")}

# 知识型板块：能力边界（✅必须掌握 / ❌不必深入）只落到这些板块的知识点上；
# 资讯类（AI资讯/行业资讯/财税政策）与 PM思考 属"容器/资讯"，不计入覆盖率分母。
KNOWLEDGE_BUCKETS = ("AI前沿", "财税知识", "数据统计", "数据库", "SQL", "Python")


def slug(s, n=40):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s).strip("-")
    return s[:n].lower()


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def norm_key(s):
    """归一化标题，用于把「今日知识点」块与条目文本配对（容忍标点/空白差异）"""
    return re.sub(r"[\s，。：:；;、（）()\-—_·｜|【】\[\]「」\"'`]+", "", s or "")


def boundary_stats(entries):
    """能力边界覆盖率（GAP-01 质量门）。

    口径（2026-09-11 用户确认）：分母只算**知识型板块**的知识点
    （AI前沿 / 财税知识 / 数据统计 / 数据库 / SQL / Python）；
    资讯类（AI资讯/行业资讯/财税政策）与 PM思考 是资讯/容器条目，不计入分母。
    """
    kps = [e for e in entries if e.get("bucket") in KNOWLEDGE_BUCKETS]
    bounded = [e for e in kps if e.get("must") and e.get("skip")]
    missing = [e for e in kps if not (e.get("must") and e.get("skip"))]
    total = len(kps)
    by_source = {}
    for e in missing:
        by_source[e["typeName"]] = by_source.get(e["typeName"], 0) + 1
    return {"total": total, "bounded": len(bounded),
            "coverage": round(len(bounded) / total * 100) if total else 0,
            "missing": len(missing), "bySource": by_source,
            "missingItems": ["%s ｜ %s" % (e["date"], e["text"]) for e in missing]}


def source_stats(entries):
    """原文来源 URL 覆盖率（GAP-02 质量门）。

    口径：分母 = 全部知识点/条目；分子 = 解析出原文链接（http/https）的条目。
    资讯条目（kind=news）单列一个覆盖率，因为它们的可追溯性要求最高。
    """
    total = len(entries)
    with_url = [e for e in entries if e.get("source_url")]
    news = [e for e in entries if e.get("kind") == "news"]
    news_with = [e for e in news if e.get("source_url")]
    seen, urls = set(), []
    for e in with_url:
        u = e["source_url"]
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return {
        "total": total,
        "withUrl": len(with_url),
        "coverage": round(len(with_url) / total * 100) if total else 0,
        "newsTotal": len(news),
        "newsWithUrl": len(news_with),
        "newsCoverage": round(len(news_with) / len(news) * 100) if news else 0,
        "urls": urls,
        "missingItems": ["%s ｜ %s" % (e["date"], e["text"]) for e in entries if not e.get("source_url")],
    }


def parse_boundaries(report):
    """从学报类报告的 md 里解析 ✅PM必须掌握 / ❌PM不需要深入 列表"""
    md = report.get("links", {}).get("md", "")
    path = None
    for src in build.SOURCES:
        cand = os.path.join(src["path"], "%s_%s.md" % (src["prefix"], report["date"]))
        if os.path.exists(cand) and src["key"] == report["type"]:
            path = cand
    if not path:
        return {}
    text = build.clean_md_meta(open(path, encoding="utf-8").read())
    out, cur = {}, None
    for line in text.splitlines():
        # 任何标题都会结束当前知识点的采集（避免把后续小节内容混入清单）
        if re.match(r"^#{2,4}\s", line):
            h3 = re.match(r"^###\s*今日知识点\s*[：:]\s*(.+)$", line)
            if h3:
                cur = h3.group(1).strip()
                out[cur] = {"must": [], "skip": []}
            else:
                cur = None
            continue
        if not cur:
            continue
        # 先识别能力边界标记行（它们本身带编号，如 "3. ✅ PM必须掌握："）
        if "PM必须掌握" in line or "PM 必须掌握" in line:
            out[cur]["_mode"] = "must"
            continue
        if "PM不需要深入" in line or "PM 不需要深入" in line:
            out[cur]["_mode"] = "skip"
            continue
        # 其它编号小节标题（如 "5. 业务风险&产品设计注意点："）结束采集
        if re.match(r"^\s*\d+\.\s", line):
            out[cur].pop("_mode", None)
            continue
        m = re.match(r"^\s*[-*]\s+(.{4,120})$", line)
        if m and out[cur].get("_mode"):
            item = re.sub(r"[*`]", "", m.group(1)).strip()
            if item and item != "-":
                out[cur][out[cur]["_mode"]].append(item[:110])
    for v in out.values():
        v.pop("_mode", None)
    return out


# ---------------- 数据组装 ----------------
def build_data():
    data = build.collect()
    reports = data["reports"]
    boundaries = {}
    for r in reports:
        for k, v in parse_boundaries(r).items():
            boundaries[(r["date"], k)] = v

    entries = []
    for r in reports:
        tm = TYPE_TAG.get(r["type"], ("", "#64748b"))
        for i, e in enumerate(r.get("entries", [])):
            if e.get("bucket") == "其他":
                continue
            eid = slug("%s-%s-%s" % (r["date"], r["type"], e["text"]), 60)
            b = boundaries.get((r["date"], e["text"].strip()), None)
            if b is None:
                # 兜底：按归一化标题配对（容忍标点/空白/轻微措辞差异）
                nt = norm_key(e["text"])
                for (d, k), v in boundaries.items():
                    if d != r["date"]:
                        continue
                    nk = norm_key(k)
                    if nk and nt and (nk == nt or (len(nt) > 8 and nt in nk) or (len(nk) > 8 and nk in nt)):
                        b = v
                        break
            entries.append({
                "id": eid,
                "date": r["date"],
                "type": r["type"],
                "typeName": tm[0],
                "bucket": e["bucket"],
                "text": e["text"],
                "snippet": e.get("snippet", ""),
                "kind": e.get("kind", ""),
                "source": e.get("source_name") or (r.get("title") or "").split("｜")[0],
                "source_name": e.get("source_name", ""),
                "source_url": e.get("source_url", ""),
                "must": (b or {}).get("must", []),
                "skip": (b or {}).get("skip", []),
            })
    entries.sort(key=lambda x: (x["date"], x["bucket"]), reverse=True)

    # 今日（最新日期）自测题：优先知识型分类
    latest = data["dates"][0] if data["dates"] else ""
    pref = ("AI前沿", "财税知识", "数据统计", "数据库", "SQL", "Python")
    quiz_pool = [e for e in entries if e["date"] == latest and e["bucket"] in pref]
    if len(quiz_pool) < 3:
        quiz_pool += [e for e in entries if e["bucket"] in pref and e not in quiz_pool]
    return data, entries, quiz_pool[:3]


def related_of(entry, entries, n=4):
    return [e for e in entries if e["bucket"] == entry["bucket"] and e["id"] != entry["id"]][:n]


def build_quiz(entries, dates):
    """从真实内容生成三档难度的选择题（零编造）：
    L1 入门 · 认识题：这条内容出现在哪个板块（识别归档）
    L2 进阶 · 边界题：哪一项属于 PM 必须掌握（正取 must，干扰取 skip）
    L3 挑战 · 反向题：哪一项【不必深入/不属于 PM 职责】（正取 skip，干扰取 must）
    """
    import random
    qs = []
    bounded = [e for e in entries if e["must"] and e["skip"]]
    all_skip = [x for e in entries for x in e["skip"]]
    all_must = [x for e in entries for x in e["must"]]

    def place(opts, rnd, target):
        """打乱选项并把正确答案旋转到 target 位置，避免答案位置偏 A"""
        rnd.shuffle(opts)
        n = len(opts)
        ci = [i for i, o in enumerate(opts) if o[1]][0]
        rot = (target - ci) % n
        return opts[-rot:] + opts[:-rot] if rot else opts

    qseq = [0]

    def next_target(n):
        qseq[0] += 1
        return qseq[0] % n

    def pick(primary, secondary, exclude, n, rnd):
        """优先从同主题条目里取干扰项，不足再用其他主题补齐"""
        out = [x for x in primary if x not in exclude]
        rnd.shuffle(out)
        out = out[:n]
        if len(out) < n:
            extra = [x for x in secondary if x not in exclude and x not in out]
            rnd.shuffle(extra)
            out += extra[:n - len(out)]
        return out[:n]

    for e in bounded:
        rnd = random.Random("b" + e["id"])
        # L2 边界题
        correct = rnd.choice(e["must"])
        distract = pick(e["skip"], all_skip, [correct], 3, rnd)
        if len(distract) == 3:
            opts = place([(correct, True)] + [(d, False) for d in distract], rnd, next_target(4))
            qs.append({
                "id": "b-" + e["id"], "date": e["date"], "eid": e["id"],
                "kind": "boundary", "level": 2,
                "q": "关于「%s」，以下哪一项属于 PM 必须掌握的能力？" % e["text"],
                "options": [o[0] for o in opts],
                "answer": [i for i, o in enumerate(opts) if o[1]][0],
                "why": "「必须掌握」是你需要能听懂、能在评审会上提要求的部分；「不必深入」属于研发或专业岗位的工作，PM 知道边界即可。",
            })
        # L3 反向题（考"知道什么不该做"）
        rnd3 = random.Random("c" + e["id"])
        wrong_side = rnd3.choice(e["skip"])
        distract3 = pick(e["must"], all_must, [wrong_side], 3, rnd3)
        if len(distract3) == 3:
            opts3 = place([(wrong_side, True)] + [(d, False) for d in distract3], rnd3, next_target(4))
            qs.append({
                "id": "c-" + e["id"], "date": e["date"], "eid": e["id"],
                "kind": "inverse", "level": 3,
                "q": "关于「%s」，以下哪一项是 PM 【不必深入】的（属于研发或专业岗位的工作）？" % e["text"],
                "options": [o[0] for o in opts3],
                "answer": [i for i, o in enumerate(opts3) if o[1]][0],
                "why": "反向题最容易出错：能分清「哪些不属于 PM 的活」，你才真的掌握了能力边界。",
            })

    recent = [e for e in entries if e["date"] in dates[:2] and e["bucket"] in ("AI资讯", "行业资讯", "财税政策")]
    buckets = ["AI资讯", "行业资讯", "财税政策"]
    for e in recent[:4]:
        rnd = random.Random("n" + e["id"])
        raw = [(e["bucket"], True)] + [(b, False) for b in buckets if b != e["bucket"]]
        opts = place(raw, rnd, next_target(3))
        qs.append({
            "id": "n-" + e["id"], "date": e["date"], "eid": e["id"],
            "kind": "bucket", "level": 1,
            "q": "这条资讯出现在当天简报的哪个板块？「%s」" % e["text"],
            "options": [o[0] for o in opts],
            "answer": [i for i, o in enumerate(opts) if o[1]][0],
            "why": "它归档在当日「%s」板块——注意：这是归档事实，若你觉得归类不合理，说明该期简报的分类需要复核。" % e["bucket"],
        })
    qs.sort(key=lambda x: (x["date"], x["level"], x["id"]), reverse=True)
    return qs


def pick_daily(quiz, latest, n=3):
    """每日组卷：确定性抽 n 题，优先「1 入门 + 1 进阶 + 1 挑战」，同一天固定不变。

    给每道题打 daily 标记：True = 今日组卷（计入完成度）；False = 补充练习（不计入）。
    兑现 PRD「每天 3 题、15 分钟」的轻量承诺。
    """
    import random
    pool = [q for q in quiz if q["date"] == latest]
    for q in quiz:
        q["daily"] = False
    if not pool:
        return []
    if len(pool) <= n:
        for q in pool:
            q["daily"] = True
        return pool
    rnd = random.Random("daily" + latest)
    by = {1: [], 2: [], 3: []}
    for q in pool:
        by.setdefault(q["level"], []).append(q)
    for lv in by:
        rnd.shuffle(by[lv])
    picks = []
    for lv in (1, 2, 3):          # 先每档各取 1 题
        if by.get(lv):
            picks.append(by[lv].pop())
    rest = [q for lv in sorted(by) for q in by[lv]]
    rnd.shuffle(rest)
    while len(picks) < n and rest:  # 某档不足时用其余题补齐
        picks.append(rest.pop())
    picks = picks[:n]
    for q in picks:
        q["daily"] = True
    return picks


# ---------------- 模板 ----------------
CSS = """
/* 字体自托管：woff2 与 site.css 同源（assets/fonts/），零外部请求、离线可用 */
@font-face{font-family:"Orbitron";font-style:normal;font-weight:700;font-display:swap;src:url("fonts/orbitron-latin-700-normal.woff2") format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:400;font-display:swap;src:url("fonts/ibm-plex-sans-latin-400-normal.woff2") format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:500;font-display:swap;src:url("fonts/ibm-plex-sans-latin-500-normal.woff2") format("woff2")}
@font-face{font-family:"IBM Plex Mono";font-style:normal;font-weight:400;font-display:swap;src:url("fonts/ibm-plex-mono-latin-400-normal.woff2") format("woff2")}
:root{
  --bg:#f7f8fa;--surface:#fff;--soft:#eef1f6;--text:#111827;--muted:#5b6472;--faint:#8a94a6;
  --accent:#2f7bf6;--accent-d:#1d5fd0;--line:rgba(17,24,39,.1);--tint:rgba(17,24,39,.05);
  --radius:16px;--display:"Orbitron","PingFang SC","Microsoft YaHei",sans-serif;
  --body:"IBM Plex Sans","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased}
a{color:var(--accent-d);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:940px;margin:0 auto;padding:0 20px}
header.nav{position:sticky;top:0;z-index:20;background:rgba(247,248,250,.88);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
header.nav .wrap{display:flex;align-items:center;gap:18px;height:58px}
.brand{font-family:var(--display);font-size:15px;font-weight:700;letter-spacing:.14em}
.brand small{display:block;font-family:var(--body);font-size:11px;color:var(--faint);letter-spacing:0;font-weight:400}
nav a{margin-right:16px;font-size:14px;color:var(--muted)}
nav a.on{color:var(--text);font-weight:500}
.spacer{flex:1}
.kbd{font-family:var(--mono);font-size:11px;color:var(--faint);border:1px solid var(--line);border-radius:5px;padding:1px 6px}
.hero{padding:64px 0 28px}
.hero .eyebrow{font-size:13px;color:var(--accent);font-weight:500;letter-spacing:.12em;text-transform:uppercase}
.hero h1{font-size:42px;line-height:1.15;letter-spacing:-.02em;margin-top:12px;font-weight:700}
.hero p{font-size:18px;color:var(--muted);margin-top:14px;max-width:640px}
.hero .meta{font-family:var(--mono);font-size:12px;color:var(--faint);margin-top:16px}
.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
.card{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:22px}
.card .cat{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.card h3{font-size:18px;line-height:1.45;margin:10px 0 8px;letter-spacing:-.01em}
.card p{font-size:14.5px;color:var(--muted)}
.card .foot{display:flex;align-items:center;gap:10px;margin-top:14px;font-size:12px;color:var(--faint);font-family:var(--mono)}
.sect{margin:44px 0 14px;display:flex;align-items:baseline;gap:12px}
.sect h2{font-size:24px;letter-spacing:-.01em}
.sect span{font-size:13px;color:var(--faint)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.chip{border:1px solid var(--line);background:var(--surface);border-radius:980px;padding:7px 15px;font-size:13.5px;color:var(--text);cursor:pointer;font-family:inherit}
.chip.on{background:var(--text);color:#fff;border-color:var(--text)}
input.search{width:100%;height:44px;border:1px solid var(--line);border-radius:12px;padding:0 16px;font-size:15px;font-family:inherit;background:var(--surface);outline:none}
input.search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(47,123,246,.15)}
.row{display:flex;gap:14px;align-items:flex-start;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:10px}
.row .main{flex:1;min-width:0}
.row .t{font-size:16px;font-weight:500}
.row .s{font-size:13.5px;color:var(--muted);margin-top:4px}
.row .m{font-family:var(--mono);font-size:11.5px;color:var(--faint);white-space:nowrap}
.prose{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:30px 32px}
.prose h1{font-size:30px;line-height:1.3;letter-spacing:-.02em;margin-bottom:10px}
.prose .kicker{font-family:var(--mono);font-size:12px;color:var(--faint);margin-bottom:18px}
.prose h2{font-size:20px;margin:26px 0 10px}
.prose p{color:#1f2937}
.bound{display:grid;gap:14px;margin-top:8px}
.bound .b{border-radius:12px;padding:14px 16px;font-size:14.5px}
.bound .must{background:rgba(47,123,246,.07);border:1px solid rgba(47,123,246,.22)}
.bound .skip{background:var(--soft);border:1px solid var(--line)}
.bound .b b{display:block;font-size:13px;margin-bottom:6px}
.bound ul{margin-left:18px}
.bound li{margin:4px 0}
.note{margin-top:20px;font-size:13px;color:var(--muted);background:var(--soft);border-radius:12px;padding:14px 16px}
.btn{display:inline-flex;align-items:center;gap:8px;border:none;border-radius:980px;padding:11px 20px;font-size:14.5px;font-family:inherit;cursor:pointer;background:var(--accent);color:#fff}
.btn.ghost{background:var(--tint);color:var(--text)}
.btn.ok{background:#16a34a}
.quiz .q{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:12px}
.quiz .q .h{font-size:13px;color:var(--faint);font-family:var(--mono);margin-bottom:8px}
.quiz .q .t{font-size:17px;font-weight:500;line-height:1.6}
.quiz .opts{display:grid;gap:8px;margin-top:14px}
.opt{text-align:left;border:1px solid var(--line);background:var(--surface);border-radius:12px;padding:12px 15px;font-size:15px;font-family:inherit;color:var(--text);cursor:pointer;line-height:1.55}
.opt:hover{border-color:var(--accent);background:rgba(47,123,246,.04)}
.opt.right{border-color:#16a34a;background:rgba(22,163,74,.08);font-weight:500}
.opt.pick-wrong{border-color:#e11d48;background:rgba(225,29,72,.07)}
.opt:disabled{cursor:default}
.quiz .why{margin-top:12px;font-size:13.5px;color:var(--muted);line-height:1.7}
.quiz .acts{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.empty{color:var(--faint);font-size:14px;padding:24px;text-align:center;border:1px dashed var(--line);border-radius:14px}
footer{margin:56px 0 40px;padding-top:20px;border-top:1px solid var(--line);font-size:12.5px;color:var(--faint);font-family:var(--mono)}
@media(max-width:860px){
  .hero h1{font-size:30px}.hero{padding:40px 0 20px}
  .g3,.g4,.g2{grid-template-columns:1fr}
  .prose{padding:22px 20px}
  nav{display:none}
  .row .m{display:none}
}
"""

JS = """
(function(){
function ls(k,d){try{var v=localStorage.getItem(k);return v?JSON.parse(v):d;}catch(e){return d;}}
function save(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
var read=ls("pm_read",{}),quiz=ls("pm_quiz",{});
document.querySelectorAll("[data-read]").forEach(function(b){
  var id=b.getAttribute("data-read");
  if(read[id])b.classList.add("ok"),b.textContent="已学会";
  b.addEventListener("click",function(){
    read[id]=!read[id];save("pm_read",read);
    b.classList.toggle("ok",!!read[id]);
    b.textContent=read[id]?"已学会":"标记已学会";
    paint();
  });
});
function paint(){
  var n=Object.keys(read).filter(function(k){return read[k];}).length;
  document.querySelectorAll("[data-progress]").forEach(function(el){el.textContent=n;});
}
paint();
/* ---- 选择题：选项判定 + 错题本（localStorage）----
   注意：题库由页面内联脚本注入，这里延迟到 load 之后执行，避免脚本顺序问题 */
function initQuiz(){
var ans=ls("pm_q_ans",{}),wrong=ls("pm_q_wrong",[]),QS=window.__QUIZ__||[];
var LV={1:["入门","#0ea5a4"],2:["进阶","#2f7bf6"],3:["挑战","#9333ea"]};
var filter="all";
if(!QS.length){
  document.querySelectorAll("[data-q]").forEach(function(c){
    c.innerHTML='<div class="t">题库未能加载，请强制刷新页面（Ctrl+F5）重试。</div>';
  });
  return;
}
function paintScore(){
  var box=document.getElementById("scoreBox");if(!box)return;
  var today=QS.filter(function(q){return q.daily;});
  var done=0,right=0,byLv={1:[0,0],2:[0,0],3:[0,0]};
  today.forEach(function(q){
    if(ans[q.id]===undefined)return;
    done++;byLv[q.level][0]++;
    if(ans[q.id]===q.answer){right++;byLv[q.level][1]++;}
  });
  var rate=done?Math.round(right/done*100)+"%":"—";
  var parts=[1,2,3].map(function(l){
    var d=byLv[l][0],r=byLv[l][1];
    return LV[l][0]+" "+(d?Math.round(r/d*100)+"%":"—");
  }).join(" · ");
  box.textContent="已答 "+done+"/"+today.length+" · 正确率 "+rate+" ｜ "+parts;
}
function applyFilter(){
  document.querySelectorAll("[data-q]").forEach(function(c){
    c.style.display=(filter==="all"||c.getAttribute("data-level")===filter)?"":"none";
  });
  var sc=document.getElementById("scoreBox");if(sc)sc.style.display=(filter==="all")?"":"none";
}
document.querySelectorAll("#lvChips .chip").forEach(function(chip){
  chip.addEventListener("click",function(){
    filter=chip.getAttribute("data-lv");
    document.querySelectorAll("#lvChips .chip").forEach(function(x){x.classList.toggle("on",x===chip);});
    applyFilter();
  });
});
function findQ(id){for(var i=0;i<QS.length;i++){if(QS[i].id===id)return QS[i];}return null;}
function renderQ(card,q){
  var picked=ans[q.id];
  var lv=LV[q.level]||LV[1];
  card.innerHTML='<div class="h"><span style="display:inline-block;background:'+lv[1]+';color:#fff;border-radius:980px;padding:2px 9px;font-size:11px;margin-right:8px">'+lv[0]+'</span>'+
    q.date+' · '+(q.kind==="inverse"?"反向边界题":q.kind==="boundary"?"能力边界题":"资讯归属题")+'</div>'+
    '<div class="t">'+q.q.replace(/</g,"&lt;")+'</div><div class="opts"></div><div class="why" style="display:none"></div>';
  var box=card.querySelector(".opts");
  q.options.forEach(function(o,i){
    var b=document.createElement("button");
    b.className="opt"+(picked===i?(i===q.answer?" right":" pick-wrong"):"")+
      (picked!==undefined&&i===q.answer?" right":"");
    b.textContent=String.fromCharCode(65+i)+". "+o;
    b.addEventListener("click",function(){
      if(ans[q.id]!==undefined)return;
      ans[q.id]=i;save("pm_q_ans",ans);
      if(i!==q.answer&&wrong.indexOf(q.id)<0){wrong.push(q.id);save("pm_q_wrong",wrong);}
      renderQ(card,q);renderWrong();paintScore();
    });
    box.appendChild(b);
  });
  var why=card.querySelector(".why");
  if(picked!==undefined){
    why.style.display="block";
    why.innerHTML=(picked===q.answer?'<b style="color:#16a34a">答对了。</b>':'<b style="color:#e11d48">答错了，已加入错题本。</b>')+
      ' '+q.why+' ｜ <a href="k/'+q.eid+'.html">去看这个知识点</a>';
  }
}
document.querySelectorAll("[data-q]").forEach(function(card){
  var q=findQ(card.getAttribute("data-q"));if(q)renderQ(card,q);
});
function renderWrong(){
  var box=document.getElementById("wrongBox");if(!box)return;
  var ids=wrong.filter(function(id){var q=findQ(id);return q&&!q.daily;});
  var today=wrong.filter(function(id){var q=findQ(id);return q&&q.daily;});
  var all=ids.concat(today);
  if(!all.length){box.innerHTML='<div class="empty">错题本是空的。答错自动进这里，次日回来重做一遍。</div>';return;}
  box.innerHTML=all.map(function(id){
    var q=findQ(id);
    return '<div class="row"><div class="main"><div class="t">'+q.q.replace(/</g,"&lt;")+'</div>'+
      '<div class="s">正确答案：'+String.fromCharCode(65+q.answer)+'. '+q.options[q.answer]+'</div></div>'+
      '<div class="m">'+(q.daily?"今日":"回顾")+'</div></div>';
  }).join("")+'<div style="margin-top:10px"><button class="btn ghost" id="clearWrong">清空错题本</button></div>';
  document.getElementById("clearWrong").addEventListener("click",function(){
    wrong=wrong.filter(function(id){var q=findQ(id);return q&&q.date===latestDate&&false;});
    save("pm_q_wrong",wrong);renderWrong();
  });
}
var latestDate=(QS[0]||{}).date||"";
renderWrong();
paintScore();
applyFilter();
}
if(document.readyState==="complete")initQuiz();else window.addEventListener("load",initQuiz);
})();
"""


FONT_LINKS = ""  # 字体已自托管（assets/fonts/*.woff2，@font-face 在 site.css 内），无外部请求


def page(title, nav_on, body, extra_script=""):
    pre = "../" if KDIR_IN_SUB else ""
    nav = "".join(
        '<a href="%s%s%s" class="%s">%s</a>' % (pre, href, "#" if False else "", "on" if key == nav_on else "", name)
        for key, href, name in [("today", "index.html", "今日"), ("map", "map.html", "知识地图"), ("quiz", "quiz.html", "自测"), ("qa", "qa.html", "质量")]
    )
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f7f8fa">
<meta name="description" content="芽课 · 每天 15 分钟，跟着真实行业动态学做产品经理。知识点带 PM 能力边界标注（必须掌握 / 不必深入）。">
<title>__TITLE__</title>
<link rel="stylesheet" href="__ASSETS__assets/site.css">
__FONT_LINKS__
</head><body>
<header class="nav"><div class="wrap">
  <div class="brand">Yake<small>芽课 · PM 入门科普站</small></div>
  <nav>__NAV__</nav>
  <div class="spacer"></div>
  <div class="kbd">已学会 <span data-progress>0</span> 个</div>
</div></header>
<main class="wrap">__BODY__</main>
<footer>芽课 Yake · PM 入门科普站 · 内容由每日学习管线自动生成 · 每期抽检事实性
<br>本站为学习科普用途，财税与政策内容不构成专业意见；资讯均标注来源，不转载原文。</footer>
__EXTRA__
<script src="__ASSETS__assets/site.js"></script>
</body></html>""".replace("__TITLE__", esc(title)).replace("__NAV__", nav).replace("__BODY__", body).replace("__ASSETS__", pre).replace("__FONT_LINKS__", FONT_LINKS).replace("__EXTRA__", extra_script)


KDIR_IN_SUB = False  # 生成 k/ 子目录页面时临时置为 True（资源与导航加 ../ 前缀）


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def card_of(e, prefix=""):
    color = CAT_META.get(e["bucket"], ("#64748b", ""))[0]
    return ('<a class="card" href="%sk/%s.html"><span class="cat"><i class="dot" style="background:%s"></i>%s</span>'
            '<h3>%s</h3><p>%s</p><div class="foot"><span>%s</span><span>%s</span></div></a>'
            % (prefix, e["id"], color, esc(e["bucket"]), esc(e["text"]),
               esc((e["snippet"] or "")[:110]), e["date"], esc(e["typeName"])))


def main():
    global KDIR_IN_SUB
    data, entries, quiz_pool = build_data()
    quiz = build_quiz(entries, data["dates"])
    latest = data["dates"][0] if data["dates"] else ""
    pick_daily(quiz, latest)   # 每日组卷：标记 daily，兑现「每天 3 题」
    boundary = boundary_stats(entries)
    bounded_n, cov_pct = boundary["bounded"], boundary["coverage"]
    srcstat = source_stats(entries)
    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(KDIR, exist_ok=True)
    # 清理上一轮遗留的知识点页：条目 id 变化后旧页会变成可直达的"僵尸页"。
    # 说明：不直接删除（安全策略会拦截批量删除），改为移动到 _stale/ 归档，可随时人工清理。
    stale_dir = os.path.join(OUT, "_stale")
    for fn in os.listdir(KDIR):
        if fn.endswith(".html"):
            try:
                os.makedirs(stale_dir, exist_ok=True)
                dst = os.path.join(stale_dir, fn)
                if os.path.exists(dst):
                    os.replace(os.path.join(KDIR, fn), dst)
                else:
                    shutil.move(os.path.join(KDIR, fn), dst)
            except OSError:
                pass
    write(os.path.join(ASSETS, "site.css"), CSS)
    write(os.path.join(ASSETS, "site.js"), JS)
    write(os.path.join(OUT, "data.json"), json.dumps(
        {"generated": data["generated"], "dates": data["dates"], "entries": entries, "quiz": quiz,
         "boundary": boundary, "source": srcstat}, ensure_ascii=False, indent=1))

    # ---- 首页 ----
    # 今日速览取 3 条：按板块去重，避免首屏三条全落在同一方向（GAP-05 同质化）
    today_pool = [e for e in entries if e["date"] == latest]
    seen_b, today_entries = set(), []
    for e in today_pool:
        if e["bucket"] in seen_b:
            continue
        seen_b.add(e["bucket"])
        today_entries.append(e)
        if len(today_entries) == 3:
            break
    if not today_entries:
        today_entries = entries[:3]
    cat_counts = {}
    for e in entries:
        cat_counts[e["bucket"]] = cat_counts.get(e["bucket"], 0) + 1
    body = ['<section class="hero"><div class="eyebrow">Daily PM Briefing</div>'
            '<h1>每天 15 分钟，跟着真实行业动态学做产品经理</h1>'
            '<p>不是大纲式课程，而是把当天真实发生的事，翻译成 PM 必须懂的知识点，并明确告诉你——哪些必须掌握，哪些不用深入。</p>'
            '<div class="meta">最新一期 %s ｜ 已归档 %d 个知识点 ｜ 覆盖 %d 个方向 ｜ 能力边界已标注 %d%%（%d/%d 知识型）</div></section>'
            % (latest, len(entries), len(cat_counts), cov_pct, bounded_n, boundary["total"])]
    body.append('<div class="sect"><h2>今日速览</h2><span>先看这 3 条，再决定深入哪个</span></div>')
    body.append('<div class="grid g3">%s</div>' % "".join(card_of(e) for e in today_entries))
    body.append('<div class="sect"><h2>按方向浏览</h2><span>共 %d 条知识点</span></div>' % len(entries))
    body.append('<div class="chips">%s</div>' % "".join(
        '<a class="chip" href="map.html#%s">%s · %d</a>' % (e["bucket"], e["bucket"], cat_counts[e["bucket"]])
        for e in [{"bucket": c} for c in CATS if c in cat_counts]))
    body.append('<div class="sect"><h2>最新期数</h2><span>每日 21:00 自动更新</span></div>')
    body.append('<div class="grid g2">%s</div>' % "".join(card_of(e) for e in entries[3:9]))
    write(os.path.join(OUT, "index.html"), page("芽课 · 每天 15 分钟学产品经理", "today", "".join(body)))

    # ---- 知识地图 ----
    rows = "".join(
        '<div class="row" data-bucket="%s" data-text="%s"><i class="dot" style="background:%s;margin-top:8px"></i>'
        '<div class="main"><div class="t"><a href="k/%s.html">%s</a></div>'
        '<div class="s">%s</div></div><div class="m">%s · %s</div></div>'
        % (esc(e["bucket"]), esc((e["text"] + e["snippet"]).lower().replace('"', " ")),
           CAT_META.get(e["bucket"], ("#64748b", ""))[0], e["id"], esc(e["text"]),
           esc((e["snippet"] or "")[:90]), e["date"], esc(e["typeName"]))
        for e in entries)
    chips = '<button class="chip on" data-cat="全部">全部 %d</button>' % len(entries) + "".join(
        '<button class="chip" data-cat="%s">%s %d</button>' % (c, c, cat_counts[c]) for c in CATS if c in cat_counts)
    map_body = ('<section class="hero"><div class="eyebrow">Knowledge Map</div>'
                '<h1>知识地图</h1><p>按方向集中补短板，或直接搜关键词。每条都能看到它来自哪一天的哪份简报。</p></section>'
                '<input class="search" id="q" placeholder="搜索知识点（如：留存、增值税、Agent、SQL）…">'
                '<div class="chips">%s</div><div id="list">%s</div>'
                '<div class="empty" id="nores" style="display:none">没有匹配的知识点，换个关键词试试</div>' % (chips, rows))
    map_js = """<script>
(function(){
var q=document.getElementById("q"),rows=[].slice.call(document.querySelectorAll("#list .row")),
    nores=document.getElementById("nores"),cat="全部";
function paint(){
  var kw=q.value.trim().toLowerCase(),n=0;
  rows.forEach(function(r){
    var ok=(cat==="全部"||r.getAttribute("data-bucket")===cat)&&(!kw||r.getAttribute("data-text").indexOf(kw)>=0);
    r.style.display=ok?"":"none";if(ok)n++;
  });
  nores.style.display=n?"none":"block";
}
document.querySelectorAll(".chip[data-cat]").forEach(function(c){
  c.addEventListener("click",function(){
    cat=c.getAttribute("data-cat");
    document.querySelectorAll(".chip[data-cat]").forEach(function(x){x.classList.toggle("on",x===c);});
    paint();
  });
});
q.addEventListener("input",paint);paint();
if(location.hash){var h=decodeURIComponent(location.hash.slice(1));
  var t=document.querySelector('.chip[data-cat="'+h+'"]');if(t)t.click();}
})();
</script>"""
    write(os.path.join(OUT, "map.html"), page("知识地图 · 芽课", "map", map_body, map_js))

    # ---- 自测（分层选择题 + 错题本） ----
    daily_q = [q for q in quiz if q.get("daily")]
    extra_q = [q for q in quiz if q["date"] == latest and not q.get("daily")]
    lv_count = {1: 0, 2: 0, 3: 0}
    for q in daily_q:
        lv_count[q["level"]] = lv_count.get(q["level"], 0) + 1
    daily_n = len(daily_q)
    qcard = '<div class="q" data-q="%s" data-date="%s" data-level="%s"></div>'
    qs = "".join(qcard % (q["id"], q["date"], q["level"]) for q in daily_q) \
        or '<div class="empty">今日暂无组卷题目</div>'
    extra_html = "".join(qcard % (q["id"], q["date"], q["level"]) for q in extra_q)
    extra_block = (
        '<details style="margin-top:22px"><summary style="cursor:pointer;font-size:14px">'
        '补充练习（%d 题，可选 · 不计入今日完成度）</summary>'
        '<div class="quiz" style="margin-top:12px">%s</div></details>' % (len(extra_q), extra_html)
    ) if extra_q else ""
    quiz_body = ('<section class="hero"><div class="eyebrow">Daily Quiz</div><h1>今日自测</h1>'
                 '<p><b>每天 3 题</b>，全部取自当天真实内容，5 分钟内做完：<b>入门</b>考"这条属于哪个板块"，'
                 '<b>进阶</b>考"哪项 PM 必须掌握"，<b>挑战</b>是反向题——问"哪项其实不必深入"。'
                 '答错自动进错题本，次日回来重做。</p>'
                 '<div class="meta">%s ｜ 今日组卷 %d 题（入门 %d / 进阶 %d / 挑战 %d）｜ 题库共 %d 题 ｜ 记录存在你的浏览器本地</div></section>'
                 '<div class="chips" id="lvChips">'
                 '<button class="chip on" data-lv="all">全部 %d</button>'
                 '<button class="chip" data-lv="1">入门 %d</button>'
                 '<button class="chip" data-lv="2">进阶 %d</button>'
                 '<button class="chip" data-lv="3">挑战 %d</button>'
                 '<span class="kbd" id="scoreBox" style="margin-left:auto">已答 0/0 · 正确率 —</span></div>'
                 '<div class="sect"><h2>错题本</h2><span>答错自动收录 · 次日回顾</span></div>'
                 '<div id="wrongBox"></div>'
                 '<div class="sect"><h2>今日组卷</h2><span>组卷规则：优先 1 入门 + 1 进阶 + 1 挑战，当天固定不变</span></div>'
                 '<div class="quiz">%s</div>%s'
                 '<div class="note">难度说明：入门=识别归档；进阶=正向辨析能力边界；挑战=反向辨析（更容易错，答对说明边界真的掌握）。'
                 '所有题目与选项都来自当天真实内容，不做 AI 编造。</div>'
                 % (latest, daily_n,
                    lv_count.get(1, 0), lv_count.get(2, 0), lv_count.get(3, 0), len(quiz),
                    daily_n, lv_count.get(1, 0), lv_count.get(2, 0), lv_count.get(3, 0), qs, extra_block))
    quiz_js = ('<script>window.__QUIZ__=%s;</script>' % json.dumps(quiz, ensure_ascii=False).replace("</", "<\\/"))
    write(os.path.join(OUT, "quiz.html"), page("今日自测 · 芽课", "quiz", quiz_body, quiz_js))

    # ---- 知识点详情页 ----
    KDIR_IN_SUB = True
    for e in entries:
        rel = related_of(e, entries)
        must = e["must"]
        skip = e["skip"]
        if must or skip:
            bound = ('<div class="bound"><div class="b must"><b>✅ PM 必须掌握</b><ul>%s</ul></div>'
                     '<div class="b skip"><b>❌ PM 不需要深入</b><ul>%s</ul></div></div>'
                     % ("".join("<li>%s</li>" % esc(x) for x in must) or "<li>待补充</li>",
                        "".join("<li>%s</li>" % esc(x) for x in skip) or "<li>待补充</li>"))
        else:
            bound = ('<div class="empty">该知识点的「能力边界」条目待补齐——内容质量门（M3）会统一为每条知识点补上 ✅必须掌握 / ❌不必深入。</div>')
        rel_html = "".join('<div class="row"><div class="main"><div class="t"><a href="%s.html">%s</a></div>'
                           '<div class="m">%s · %s</div></div></div>'
                           % (r["id"], esc(r["text"]), r["date"], esc(r["typeName"])) for r in rel) or \
                   '<div class="empty">同方向暂无其他知识点</div>'
        disclaimer = ('<br><b>本页涉及财税/政策内容，仅为学习科普，不构成任何专业意见或操作建议。</b>'
                      if e["bucket"] in ("财税政策", "财税知识", "政策法规") else "")
        if e.get("source_url"):
            src_line = ('<p style="font-size:13px;margin:8px 0 0">原文来源：'
                        '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a></p>'
                        % (esc(e["source_url"]), esc(e["source_url"])))
        else:
            src_line = ('<p style="font-size:13px;margin:8px 0 0;color:#b45309">'
                        '原文链接待补齐（GAP-02）｜本条来源：%s</p>' % esc(e.get("source") or "未标注"))
        body = ('<article class="prose"><h1>%s</h1><div class="kicker">%s ｜ %s ｜ 来源：%s（%s）</div>%s'
                '<h2>它是什么</h2><p>%s</p>'
                '<h2>为什么 PM 要懂</h2><p>这类知识通常出现在需求评审、数据核对、与研发/财务对齐的场景里。看懂它，你才能在会上问对问题，而不是只记结论。</p>'
                '<h2>能力边界</h2>%s'
                '<h2>我们怎么判断你学会了</h2><p>不看笔记，用自己的话说清"它是什么、什么场景会用到、我需要掌握到哪一步"。说得出来，就算过关。</p>'
                '<div class="acts" style="margin-top:18px"><button class="btn" data-read="%s">标记已学会</button>'
                '<a class="btn ghost" href="../quiz.html">去自测</a></div>'
                '<div class="note">内容由每日学习管线自动生成，事实性以原始来源为准；如需引用请回到来源文章核对。%s</div></article>'
                '<div class="sect"><h2>同方向知识点</h2><span>%s</span></div>%s'
                % (esc(e["text"]), e["date"], esc(e["bucket"]), esc(e["source"]), esc(e["typeName"]),
                   src_line,
                   esc(e["snippet"] or "（这条来自当日资讯，完整背景请查看对应的每日简报。）"),
                   bound, e["id"], disclaimer, esc(e["bucket"]), rel_html))
        title = "%s · %s ｜ 芽课" % (e["text"], e["bucket"])
        write(os.path.join(KDIR, "%s.html" % e["id"]),
              page(title, "map", body))
    KDIR_IN_SUB = False

    # ---- 内容质量看板（读 qa_check.py 的输出） ----
    qa_path = os.path.join(BASE, "docs", "qa-report.json")
    if os.path.exists(qa_path):
        qa = json.load(open(qa_path, encoding="utf-8"))
        st = qa.get("stats", {})
        ic = qa.get("issue_count", {})
        issues = qa.get("issues", [])
        errs = [i for i in issues if i["level"] == "error"]
        warns = [i for i in issues if i["level"] == "warn"]

        def issue_html(i):
            tag = "错误" if i["level"] == "error" else "疑点"
            color = "#e11d48" if i["level"] == "error" else "#f59e0b"
            return ('<div class="row"><div class="main"><div class="t">'
                    '<span style="display:inline-block;background:%s;color:#fff;border-radius:980px;padding:1px 8px;font-size:11px;margin-right:8px">%s</span>'
                    '%s</div><div class="s">%s ｜ %s</div></div><div class="m">%s</div></div>'
                    % (color, tag, esc(i["type"]), esc(i["detail"]), esc(i["date"]), esc(i["target"])))

        sample_html = "".join(
            '<div class="row"><i class="dot" style="background:%s;margin-top:8px"></i>'
            '<div class="main"><div class="t">%s</div><div class="s">%s</div>'
            '<div class="s" style="color:var(--faint)">核对方式：%s</div></div></div>'
            % (CAT_META.get(s["bucket"], ("#64748b", ""))[0], esc(s["text"]),
               esc(s["snippet"]), esc(s["how"]))
            for s in qa.get("sample", []))
        qa_body = (
            '<section class="hero"><div class="eyebrow">Content QA</div><h1>内容质量看板</h1>'
            '<p>这是给自动产出内容的"质量门"：机器先做七项校验（结构完整性、板块归类、能力边界矛盾、'
            '能力边界覆盖率、来源覆盖、原文来源 URL、每日抽检），人工只需核对抽检清单。发现问题会记入勘误并回补。</p>'
            '<div class="meta">校验时间 %s ｜ 覆盖 %s 天 ｜ 知识点 %s 个</div></section>'
            '<div class="grid g4" style="margin-top:26px">'
            '<div class="card"><div class="cat">结构/边界错误</div><h3 style="font-size:30px">%d</h3><p>需修复</p></div>'
            '<div class="card"><div class="cat">疑似问题</div><h3 style="font-size:30px">%d</h3><p>需人工判断</p></div>'
            '<div class="card"><div class="cat">原文来源 URL</div><h3 style="font-size:30px">%s</h3><p>含原文链接 %s/%s ｜ 资讯原文覆盖率 %s</p></div>'
            '<div class="card"><div class="cat">能力边界覆盖率</div><h3 style="font-size:30px">%s</h3><p>知识型知识点已标注 ✅/❌ %s/%s（GAP-01）</p></div>'
            '</div>'
            '<div class="sect"><h2>校验发现</h2><span>错误 %d · 疑点 %d</span></div>'
            '%s'
            '<div class="sect"><h2>今日抽检清单</h2><span>人工核对这 3 条的事实性</span></div>'
            '%s'
            '<div class="note">校验规则：① 三份报告是否齐全、条目数是否过低；'
            '② 资讯条目是否含所属板块特征词；③ ✅必须掌握与❌不必深入是否重叠或串味；'
            '④ 资讯是否有来源；⑤ 每日随机抽 3 条供人工核对；'
            '⑥ 每条知识点是否都标注了能力边界（GAP-01 覆盖率，目标 100%%）；'
            '⑦ 每条知识点/资讯是否带原文链接并抽检可达性（GAP-02，目标 100%%）。'
            '发现错误请记入 <code>docs/errata.md</code>。</div>'
            % (esc(qa.get("generated", "")), len(qa.get("dates", [])), st.get("校验知识点数", "—"),
               ic.get("error", 0), ic.get("warn", 0),
               st.get("来源URL覆盖率", "—"), st.get("含URL条目数", "—"), st.get("条目总数", "—"),
               st.get("资讯原文覆盖率", "—"),
               st.get("边界覆盖率", "—"), st.get("含边界知识点数", "—"), st.get("知识点总数", "—"),
               ic.get("error", 0), ic.get("warn", 0),
               "".join(issue_html(i) for i in (errs + warns)) or '<div class="empty">本期未发现质量问题</div>',
               sample_html or '<div class="empty">暂无抽检条目</div>'))
        write(os.path.join(OUT, "qa.html"), page("内容质量看板 · 芽课", "qa", qa_body))
        qa_note = "｜质量页已生成"
    else:
        qa_note = "｜质量页跳过（未运行 qa_check.py）"

    print("站点已生成：%s" % OUT)
    print("  知识点页 %d 个 ｜ 首页/地图/自测 各 1 个 ｜ 题库 %d 题（今日组卷 %d 题）｜ 能力边界覆盖率 %d%%（%d/%d 知识型）%s" % (
        len(entries), len(quiz), len(daily_q),
        cov_pct, bounded_n, boundary["total"], qa_note))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
