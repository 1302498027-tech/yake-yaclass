# -*- coding: utf-8 -*-
"""
PM 学习工作台 · 数据聚合与构建脚本
扫描三个自动任务的 outputs/ 目录，解析 META 与标题结构，
归类知识主题，生成供 index.html 使用的内嵌数据。
用法：python build.py
"""
import json
import os
import re
import sys
from datetime import datetime, date, timezone, timedelta

# 统一用北京时间（UTC+8）显示时间：云函数容器是 UTC 时区，
# 若按系统本地时区格式化，9/19 凌晨的报告会显示成"9/18 16:59"。
CN_TZ = timezone(timedelta(hours=8))
from urllib.request import pathname2url

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 数据源路径（GAP 阶段2 上云前置改造：不再硬编码本机绝对路径）
#
#   默认：以本仓库所在目录的**上一级**作为内容管线根目录
#         （本机即 C:\Users\<你>\WorkBuddy，无需写死用户名）
#   覆盖：设置环境变量 YAKE_AUTOMATION_ROOT 指定管线根目录，
#         或用 YAKE_SRC_DEEP / YAKE_SRC_LEARN / YAKE_SRC_JOURNAL
#         分别指定某个源的绝对路径（GitHub Actions 用这个）。
#
#   例（PowerShell）：$env:YAKE_AUTOMATION_ROOT="D:\yake-data"
#   例（bash）      ：YAKE_SRC_DEEP=/data/deep/outputs python build.py
# ---------------------------------------------------------------------------
AUTOMATION_ROOT = os.environ.get("YAKE_AUTOMATION_ROOT") or BASE


def src_path(env_key, default_subdir):
    """单源目录：环境变量优先（绝对路径），否则 AUTOMATION_ROOT/子目录。"""
    v = os.environ.get(env_key)
    if v:
        return v
    return os.path.join(AUTOMATION_ROOT, *default_subdir.split("/"))


SOURCES = [
    {
        "key": "deep",
        "label": "深度版",
        "name": "新闻 · 深度版",
        "prefix": "daily_deep_brief",
        "meta_type": "daily_deep_brief",
        "path": src_path("YAKE_SRC_DEEP", "outputs/deep"),
        # 本机原始产出目录（含 PDF/网页版）。云端构建时它不存在，仅用于"合并历史产物"，
        # 这样云端重建报告目录时不会把本机已生成的 PDF/HTML 弄丢。
        "local_path": os.path.join(AUTOMATION_ROOT, "outputs", "deep"),
    },
    {
        "key": "learn",
        "label": "轻量版",
        "name": "学习 · 轻量版",
        "prefix": "daily_learning_brief",
        "meta_type": "daily_learning_brief",
        "path": src_path("YAKE_SRC_LEARN", "outputs/learn"),
        "local_path": os.path.join(AUTOMATION_ROOT, "outputs", "learn"),
    },
    {
        "key": "journal",
        "label": "技术版",
        "name": "学报 · 技术版",
        "prefix": "daily_tech_tax_journal",
        "meta_type": "daily_tech_tax_journal",
        "path": src_path("YAKE_SRC_JOURNAL", "outputs/journal"),
        "local_path": os.path.join(AUTOMATION_ROOT, "outputs", "journal"),
    },
]

# 模板说明性文字特征（进入简报正文但属于固定模板的引导语，不计入正文检索）
TEMPLATE_HINTS = (
    "教学模式", "面向PM", "客观完整概括", "禁止编造", "浅度科普",
    "PM要懂什么", "PM不需要", "阅读说明", "每条资讯", "深度教学：",
    "导读", "初学者友好", "今日学习主题总览", "输出标准", "元数据",
    "弱化底层", "少底层", "每日只输出", "碎片化", "不要纯", "标注简要",
)

# 标题/知识点 → 知识分类桶
def bucket_of(text):
    t = text
    tl = t.lower()
    if "sql" in tl or "select" in tl or "where" in tl or "join" in tl:
        return "SQL"
    if "python" in tl:
        return "Python"
    if "数据库" in t:
        return "数据库"
    if "政策法规" in t or "法规政策" in t or "监管政策" in t:
        return "政策法规"
    if "政策" in t and ("财税" in t or "税" in t):
        return "财税政策"
    if "数据统计" in t or "留存" in t or "Cohort" in t or "cohort" in t:
        return "数据统计"
    if "AI前沿" in t or "AI 前沿" in t or "AI产品" in t or "AI 产品" in t or "大语言模型" in t:
        return "AI前沿"
    if "AI科技" in t or "科技新闻" in t or "AI 科技" in t:
        return "AI资讯"
    if "文化" in t:
        return "行业资讯"
    if "财税" in t or "税" in t or "发票" in t:
        return "财税知识"
    if "思考" in t or "落地" in t:
        return "PM思考"
    return "其他"

TOPIC_LINE = re.compile(
    r"^\s*(?:\*\*)?\s*(?:今日学习主题|今日主题|今日知识点名称|今日知识点)\s*[：:]\s*(.*?)\s*(?:\*\*)?\s*$"
)
H3_TOPIC = re.compile(r"^#{2,3}\s*.*?今日知识点\s*[：:]\s*(.+)$")
NEWS_TITLE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(.{4,64}?)\*\*\s*[：:]")
DIR_LINE = re.compile(r"^#{1,4}\s")

# 容器/占位标题：整节作为一条时，这些标题本身不是知识点（总结、思考笔记、速览、失败回退的「XX新闻（精选N条）」等）
CONTAINER_RE = re.compile(
    r"重点总结|落地提示|个人思考笔记|实习落地思考|今日速览|阅读说明|学习导读|今日导读|（精选\d*条?）")


def is_container_entry(e):
    return e.get("kind") == "section" and bool(CONTAINER_RE.search(e.get("text") or ""))


def clean_md_meta(text):
    """去除 META 注释块"""
    text = re.sub(r"<!--\s*META_START.*?META_END\s*-->", "", text, flags=re.S)
    return text


def parse_meta(head):
    meta = {}
    for line in head.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.+)$", line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def line_is_content(line):
    """判断一行是否属于可检索的实质内容"""
    s = line.strip()
    if not s or len(s) < 2:
        return False
    if s.startswith("#") or s.startswith("<!--"):
        return False
    if s.startswith(">") and any(k in s for k in TEMPLATE_HINTS):
        return False
    if any(k in s for k in ("【工作台key", "META_START", "META_END")):
        return False
    return True


def clean_word_line(line):
    s = line.strip()
    s = re.sub(r"^[\s>#*+\-]+", "", s)
    s = re.sub(r"^\d+(\.\d+)*[\.、\s]*", "", s)
    s = re.sub(r"```|`|\[\[|\]\]", "", s)
    s = re.sub(r"【工作台key:[^】]*】", "", s)
    return s.strip()


def section_text_of(lines):
    """从正文行里取前 2-3 个内容行作为小节简介"""
    got = []
    for ln in lines:
        s = clean_word_line(ln)
        if not s or len(s) < 6:
            continue
        if any(k in s for k in TEMPLATE_HINTS):
            continue
        if "目录" == s or s.startswith("今日学习主题总览"):
            continue
        got.append(s)
        if len(got) >= 3:
            break
    return " ｜ ".join(got)[:180]


def split_top_sections(body):
    """按 ## 一级小节切分，返回 [(level, heading_text, body_lines)]"""
    items = []
    cur_level, cur_head, cur_lines = 0, "", []
    for ln in body.splitlines():
        m = re.match(r"^(#{2,4})\s+(.*)$", ln)
        if m:
            if cur_head:
                items.append((cur_level, cur_head, cur_lines))
            cur_level = len(m.group(1))
            cur_head = re.sub(r"【工作台key:[^】]*】", "", m.group(2))
            cur_head = re.sub(r"^[\d.、\s]+", "", cur_head).strip()
            cur_lines = []
        else:
            cur_lines.append(ln)
    if cur_head:
        items.append((cur_level, cur_head, cur_lines))
    return items


URL_RE = re.compile(r"https?://[^\s，。；、）)】」\"'<>｜|]+")


def extract_source(lines, start=0, limit=9):
    """从 start 起的若干行里找「来源 / 信息来源 / 资料来源」行。

    返回 (来源名, 原文URL)。GAP-02：来源必须带原文链接，这里同步解析出 URL。
    """
    for j in range(start, min(start + limit, len(lines))):
        ln = lines[j]
        if "来源" not in ln:
            continue
        m = re.match(r"^\s*[>*\-–—\s]*\**\s*(信息来源|资料来源|数据来源|来源)\s*\**\s*[：:]\s*(.+)$", ln)
        if not m:
            continue
        body = m.group(2).replace("**", "").strip()
        url = ""
        um = URL_RE.search(body)
        if um:
            url = um.group(0).rstrip(".,;，。；")
            body = (body[:um.start()] + body[um.end():]).strip(" \u3000,，、;；")
        return body[:80], url
    return "", ""


def news_entries(lines):
    """资讯小节：抓取加粗的新闻标题（容忍前导 - / * 与行内「资讯标题：」），并提取摘要与来源"""
    BAN = ("核心摘要", "政策要点", "PM启发", "信息来源", "行业影响", "阅读提示",
           "阅读说明", "来源", "摘要", "今日主题", "今日知识点")
    out = []
    for i, ln in enumerate(lines):
        # 支持三种写法：`**标题**`、`- **标题**`、`- **资讯标题：标题**`
        m = re.match(r"^\s*(?:[-*+]\s*)?\*\*([^*]+?)\*\*\s*[：:]?\s*$", ln)
        if not m:
            continue
        txt = m.group(1).strip()
        if any(txt.startswith(b) for b in BAN):
            continue
        txt = re.sub(r"^(资讯标题|标题)\s*[：:]", "", txt).strip()
        txt = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", txt).strip()
        if not (8 <= len(txt) <= 90):
            continue
        snip = ""
        for j in range(i + 1, min(i + 9, len(lines))):
            l2 = lines[j]
            if "摘要" in l2:
                s = re.sub(r"^[\s>*#\-]+", "", l2)
                s = s.replace("**", "")
                s = re.sub(r"^(核心)?摘要\s*[：:]\s*", "", s).strip()
                snip = s[:150]
                break
        sname, surl = extract_source(lines, i + 1, 9)
        out.append({"kind": "news", "text": txt[:80], "snippet": snip,
                    "source_name": sname, "source_url": surl})
    return out


# 技术版「今日学习主题总览」的前缀 → 知识分类
BUCKET_PREFIX = {
    "数智财税": "财税知识", "财税": "财税知识",
    "AI基础": "AI前沿", "AI": "AI前沿",
    "数据库": "数据库",
    "SQL": "SQL",
    "Python": "Python",
}


def entries_of_section(level, head, lines):
    """把一个小节转成知识条目列表（不含 bucket，由调用方决定归类）"""
    bucket = bucket_of(head)
    if head.startswith("目录"):
        return []
    joined = "\n".join(lines)

    topics = []
    topic_bucket = {}
    # 1) 独立一行的“今日知识点/主题：xxx”
    for ln in lines:
        m = TOPIC_LINE.match(ln)
        if m and m.group(1).strip():
            topics.append(m.group(1).strip())
    # 2) 三级标题 “### 今日知识点：xxx”
    for ln in lines:
        m = H3_TOPIC.match(ln)
        if m and m.group(1).strip():
            topics.append(m.group(1).strip())
    # 2a) 技术版「今日学习主题总览」：- 数智财税：数电票系统操作流程
    if not topics and ("导读" in head or "总览" in head):
        for ln in lines:
            m = re.match(r"^\s*[-*]\s*([^：:\s]{2,8})\s*[：:]\s*(.+)$", ln)
            if m and m.group(2).strip():
                topics.append(m.group(2).strip())
                topic_bucket[m.group(2).strip()] = BUCKET_PREFIX.get(m.group(1).strip(), "")
    # 2b) 技术版结构：“### 今日知识点：”下面用编号列表写核心概念
    #     例：  1. 核心概念：数电票
    if not topics:
        for ln in lines:
            m = re.match(r"^\s*(?:\d+[.、)]|[-*])\s*(?:核心概念|知识点名称|今日学习主题|学习主题)\s*[：:]\s*(.+)$", ln)
            if m and m.group(1).strip():
                topics.append(m.group(1).strip())
    if topics:
        sname, surl = extract_source(lines, 0, len(lines))
        out = []
        for txt in topics:
            txt = re.sub(r"^今日(学习主题|主题|知识点名称|知识点)\s*[：:]\s*", "", txt).strip()
            if not txt:
                continue
            item = {"kind": "topic", "text": txt[:100], "snippet": txt[:80],
                    "source_name": sname, "source_url": surl}
            hint = topic_bucket.get(txt)
            if hint:
                item["bucket_hint"] = hint
            out.append(item)
        return out

    # 3) 资讯小节：只抓新闻标题；抓不到就返回空，绝不伪造「XX新闻（精选N条）」这类容器条目
    if bucket in ("AI资讯", "行业资讯", "财税政策", "政策法规"):
        return news_entries(lines)

    # 4) 兜底：小节本身作为一条
    snip = section_text_of(lines)
    head_txt = re.sub(r"^今日知识点\s*[：:]\s*", "", head).strip()
    sname, surl = extract_source(lines, 0, len(lines))
    if not head_txt:
        return []
    return [{
        "kind": "section",
        "text": re.sub(r"[【】]", "", head_txt).strip(" ｜·:：")[:60],
        "snippet": snip,
        "source_name": sname,
        "source_url": surl,
    }]


def parse_md(path, src):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", os.path.basename(path))
    if not m:
        return None
    fdate = m.group(1)
    # 元数据
    meta = {}
    mb = re.search(r"<!--\s*META_START.*?META_END\s*-->", raw, flags=re.S)
    if mb:
        meta = parse_meta(mb.group(0))
    meta.setdefault("meta_type", src["meta_type"])
    meta.setdefault("meta_date", fdate)
    tags = [t.strip() for t in meta.get("meta_tags", "").split(",") if t.strip()]
    if not tags:
        tags = {
            "deep": ["ai科技", "文化", "财税政策", "ai前沿", "财税基础", "数据统计"],
            "learn": ["ai科技", "文化", "财税政策", "ai前沿", "财税基础", "数据统计"],
            "journal": ["数智财税", "AI基础", "数据库", "SQL", "Python"],
        }.get(src["key"], [])

    body = clean_md_meta(raw)
    lines = body.splitlines()
    title = ""
    for ln in lines:
        if ln.startswith("# "):
            title = re.sub(r"^#\s*", "", ln).strip()
            break

    words = []
    for ln in lines:
        if not line_is_content(ln):
            continue
        w = clean_word_line(ln)
        if w:
            words.append(w)
    words_text = "\n".join(words)

    sections = []
    entries = []
    parent_bucket = None
    parent_has_topic = False
    for level, head, blines in split_top_sections(body):
        sections.append({"level": level, "text": head})
        b = bucket_of(head)
        if level <= 2:
            parent_bucket = b
            parent_has_topic = False
        eff = b
        if level > 2 and eff in ("其他", "PM思考") and parent_bucket and parent_bucket != "其他":
            eff = parent_bucket
        for e in entries_of_section(level, head, blines):
            if e["kind"] == "section":
                if not e["snippet"]:
                    continue
                if eff == "其他":
                    continue
                if level > 2 and eff == parent_bucket and parent_has_topic:
                    continue
            if e["kind"] == "topic":
                parent_has_topic = True
            e.setdefault("source_name", "")
            e.setdefault("source_url", "")
            if is_container_entry(e):
                continue
            hint = e.pop("bucket_hint", "")
            e["bucket"] = hint if (hint and eff == "其他") else eff
            # 生成器偶尔把知识点写成 <xxx>，尖括号是模板残留，清掉再展示
            for _k in ("text", "snippet"):
                if e.get(_k):
                    e[_k] = re.sub(r"<([^<>]+)>", r"\1", e[_k])
            entries.append(e)

    # 同一知识点常在两处出现（章节正文的「今日知识点名称」与能力边界区的「### 今日知识点」），
    # 按「分类 + 去空白文本」去重、保留首次出现，避免卡片上出现同名重复条目
    _seen, _uniq = set(), []
    for e in entries:
        k = (e.get("bucket"), re.sub(r"\s+", "", e.get("text", "")))
        if k in _seen:
            continue
        _seen.add(k)
        _uniq.append(e)
    entries = _uniq

    # 链接
    base = os.path.join(src["path"], src["prefix"] + "_" + fdate)
    md_path = base + ".md"
    pdf_path = None
    for cand in (base + "_final.pdf", base + ".pdf"):
        if os.path.exists(cand):
            pdf_path = cand
            break
    html_path = base + ".html" if os.path.exists(base + ".html") else None

    def to_url(p):
        return "file:///" + pathname2url(os.path.abspath(p))

    return {
        "date": fdate,
        "type": src["key"],
        "label": src["label"],
        "name": src["name"],
        "meta_type": meta.get("meta_type", src["meta_type"]),
        "title": title,
        "duration": meta.get("meta_duration", ""),
        "tags": tags,
        "entries": entries,
        "words": words_text,
        "links": {
            "md": to_url(md_path) if os.path.exists(md_path) else "",
            "pdf": to_url(pdf_path) if pdf_path else "",
            "html": to_url(html_path) if html_path else "",
        },
    }


def file_to_links(src, fdate):
    base = os.path.join(src["path"], src["prefix"] + "_" + fdate)
    links = {}
    if os.path.exists(base + ".md"):
        links["md"] = "file:///" + pathname2url(os.path.abspath(base + ".md"))
    pdf = None
    for cand in (base + "_final.pdf", base + ".pdf"):
        if os.path.exists(cand):
            pdf = cand
            break
    if pdf:
        links["pdf"] = "file:///" + pathname2url(os.path.abspath(pdf))
    if os.path.exists(base + ".html"):
        links["html"] = "file:///" + pathname2url(os.path.abspath(base + ".html"))
    return links


def same_date_overlap(reports):
    """同一天不同报告之间的主题关联提示"""
    by_date = {}
    for r in reports:
        by_date.setdefault(r["date"], []).append(r)
    hints = []
    KB_BUCKETS = ("AI前沿", "财税知识", "数据统计", "数据库", "SQL", "Python", "数智财税")
    KWS = {
        "AI前沿": ("agent", "智能体", "大模型", "llm", "rag", "多模态", "computer", "mcp", "工具调用", "上下文"),
        "财税知识": ("增值税", "发票", "抵扣", "留抵", "价内", "价外", "开票", "进项", "销项", "税"),
        "数据统计": ("留存", "cohort", "环比", "同比", "转化率", "ab test", "abtest", "显著性", "样本", "抽样", "p值"),
        "数据库": ("表", "字段", "主键", "外键", "关系型"),
        "SQL": ("select", "where", "查询", "过滤", "join"),
        "Python": ("pandas", "python", "脚本", "自动化"),
    }
    seen_pair = set()
    for d, rlist in by_date.items():
        if len(rlist) < 2:
            continue
        for i in range(len(rlist)):
            for j in range(i + 1, len(rlist)):
                a, b = rlist[i], rlist[j]
                for ea in a["entries"]:
                    if ea["bucket"] not in KB_BUCKETS:
                        continue
                    for eb in b["entries"]:
                        if eb["bucket"] != ea["bucket"]:
                            continue
                        pkey = (d, ea["bucket"], a["label"], b["label"])
                        if pkey in seen_pair:
                            continue
                        ta = re.sub(r"[\s\-—–·]", "", ea["text"].lower())
                        tb = re.sub(r"[\s\-—–·]", "", eb["text"].lower())
                        if ta and tb and (ta == tb or (len(ta) > 8 and ta in tb) or (len(tb) > 8 and tb in ta)):
                            seen_pair.add(pkey)
                            hints.append({"date": d, "bucket": ea["bucket"], "a": a["label"], "b": b["label"],
                                          "ta": ea["text"], "tb": eb["text"], "kind": "dup"})
                            continue
                        kws = KWS.get(ea["bucket"], ())
                        hit = [k for k in kws if k in ea["text"].lower() or k in eb["text"].lower()]
                        if hit:
                            seen_pair.add(pkey)
                            hints.append({"date": d, "bucket": ea["bucket"], "a": a["label"], "b": b["label"],
                                          "ta": ea["text"], "tb": eb["text"], "kind": "related", "kw": hit[0]})
    return hints


def collect():
    """扫描全部数据源，返回聚合数据（供构建与本地服务共用）"""
    reports = []
    for src in SOURCES:
        if not os.path.isdir(src["path"]):
            print("跳过（目录不存在）:", src["path"])
            continue
        for fn in sorted(os.listdir(src["path"])):
            if fn.startswith(src["prefix"] + "_") and fn.endswith(".md") and "final" not in fn:
                r = parse_md(os.path.join(src["path"], fn), src)
                if r:
                    r["links"] = file_to_links(src, r["date"])
                    # 统一按北京时间显示：云端容器是 UTC，若用本地时区，同一天的报告会显示成"前一天"
                    r["mtime"] = datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(src["path"], fn)),
                        CN_TZ).strftime("%Y-%m-%d %H:%M")
                    reports.append(r)
    reports.sort(key=lambda x: (x["date"], x["type"]))

    dates = sorted({r["date"] for r in reports}, reverse=True)
    hints = same_date_overlap(reports)

    sources = []
    for s in SOURCES:
        cnt = sum(1 for r in reports if r["type"] == s["key"])
        latest_d = max((r["date"] for r in reports if r["type"] == s["key"]), default="")
        sources.append({
            "key": s["key"], "label": s["label"], "name": s["name"],
            "prefix": s["prefix"], "path": s["path"],
            "exists": os.path.isdir(s["path"]), "count": cnt, "latest": latest_d,
        })

    gen = max((r["mtime"] for r in reports), default=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"))
    return {
        "generated": gen,
        "source_count": len(SOURCES),
        "dates": dates,
        "reports": reports,
        "hints": hints,
        "sources": sources,
    }


def attach_extras(data):
    """并入科普站能力：自测题库（复用 build_site 的真实内容出题）+ 内容质检报告"""
    try:
        import build_site
        sdata, sentries, _pool = build_site.build_data()
        data["quiz"] = build_site.build_quiz(sentries, sdata["dates"])
        build_site.pick_daily(data["quiz"], (sdata["dates"] or [""])[0])  # 与科普站一致：每日组卷 3 题
    except Exception as e:  # noqa: BLE001
        data["quiz"] = []
        print("题库生成失败（自测页将显示空态）:", e)
    qa_path = os.path.join(BASE, "docs", "qa-report.json")
    if os.path.exists(qa_path):
        try:
            with open(qa_path, "r", encoding="utf-8") as f:
                data["qa"] = json.load(f)
        except Exception:  # noqa: BLE001
            data["qa"] = None
    else:
        data["qa"] = None
    return data


def render_html(data):
    """用最新数据渲染完整工作台页面"""
    if "quiz" not in data:  # 服务端实时聚合路径：collect() 后未附加题库/质检
        attach_extras(data)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(BASE, "template.html"), "r", encoding="utf-8") as f:
        template = f.read()
    if "__PAYLOAD__" not in template:
        raise RuntimeError("template.html 缺少 __PAYLOAD__ 占位符")
    return template.replace("__PAYLOAD__", payload)


def main():
    data = collect()
    data = attach_extras(data)
    with open(os.path.join(BASE, "data", "reports.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    html = render_html(data)
    out = os.path.join(BASE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("报告数:", len(data["reports"]), "日期数:", len(data["dates"]), "关联提示:", len(data["hints"]))
    print("已生成:", out)

    # 科普站并入工作台：复制 pm-site 到 BASE/pm（跳过 _ 开头的内部文件），侧边栏链接即可用
    pm_src = os.path.join(BASE, "pm-site")
    pm_dst = os.path.join(BASE, "pm")
    if os.path.isdir(pm_src):
        import shutil
        import time
        # 不直接删除（安全策略拦截批量删除）：上一轮 pm/ 整体移入 _archive/ 后再重建
        if os.path.isdir(pm_dst):
            arch = os.path.join(BASE, "_archive", "pm-local-" + time.strftime("%Y%m%d-%H%M%S"))
            os.makedirs(os.path.dirname(arch), exist_ok=True)
            try:
                shutil.move(pm_dst, arch)
            except OSError:
                pass
        os.makedirs(pm_dst, exist_ok=True)
        n = 0
        for root, dirs, files in os.walk(pm_src):
            dirs[:] = [d for d in dirs if not d.startswith("_")]   # 跳过 _stale 等内部归档
            rel = os.path.relpath(root, pm_src)
            dst_root = os.path.normpath(os.path.join(pm_dst, rel)) if rel != "." else pm_dst
            os.makedirs(dst_root, exist_ok=True)
            for fn in files:
                if fn.startswith("_"):
                    continue
                shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))
                n += 1
        print("科普站已并入: pm/ (%d 个文件)" % n)


if __name__ == "__main__":
    main()
