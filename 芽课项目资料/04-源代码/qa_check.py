# -*- coding: utf-8 -*-
"""
内容质量门（M3）：对每日自动产出的简报做机器校验，输出可执行的抽检清单。

校验项
  1. 结构完整性   —— 某天三份报告是否齐全、META 字段是否完整、条目数是否过低
  2. 板块归类     —— 资讯条目是否含所属板块的特征词；可疑项给出"更像哪个板块"的建议
  3. 能力边界矛盾 —— ✅必须掌握 与 ❌不必深入 是否重叠；两侧是否互相串味
  4. 来源覆盖     —— 资讯条目是否标注来源（教学科普的可追溯性）
  5. 抽检清单     —— 每日随机抽 3 条，供人工核对事实性，结果记入 docs/errata.md

输出：docs/qa-report.json + 控制台报告
用法：python qa_check.py
"""
import io
import json
import os
import random
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import build  # noqa: E402

BUCKET_KW = {
    "AI资讯": ["AI", "大模型", "模型", "Agent", "智能体", "算力", "芯片", "OpenAI", "英伟达",
               "Meta", "谷歌", "微软", "智能", "GPT", "生成式", "语料", "DeepSeek", "Anthropic",
               "Claude", "Gemini", "豆包", "通义", "文心", "Kimi", "智谱", "推理", "训练",
               "多模态", "机器人", "自动驾驶"],
    "行业资讯": ["短剧", "电影", "音乐", "文化", "IP", "内容", "综艺", "游戏", "演出", "非遗",
                 "播放", "影视", "文旅", "文学", "动漫", "票房"],
    "财税政策": ["税", "财政部", "税务总局", "财政", "补贴", "发票", "征管", "申报", "抵扣",
                 "留抵", "社保", "消费税", "增值税", "收费", "专项资金", "财政政策", "企业所得"],
}
DEEP_TERMS = ["底层实现", "实现机制", "系统架构", "后端接口", "算法原理", "加密", "范式分解",
              "源码", "性能影响分析", "训练原理", "注意力机制", "数据库设计理论"]
PM_ACTION_TERMS = ["产品需", "需要在产品", "需求评审", "PRD", "展示", "预警", "流程设计", "交互",
                   "功能设计", "用户", "界面"]


def find_md(report):
    for src in build.SOURCES:
        if src["key"] != report["type"]:
            continue
        p = os.path.join(src["path"], "%s_%s.md" % (src["prefix"], report["date"]))
        if os.path.exists(p):
            return p
    return None


def main():
    data = build.collect()
    reports = data["reports"]
    dates = data["dates"]
    issues = []
    stats = {}

    # ---------- 1. 结构完整性 ----------
    for d in dates:
        rs = [r for r in reports if r["date"] == d]
        kinds = {r["type"] for r in rs}
        for k, name in (("deep", "深度版"), ("learn", "轻量版"), ("journal", "技术版")):
            if k not in kinds:
                issues.append({"level": "error", "type": "结构缺失", "date": d, "target": name,
                               "detail": "当日未产出该份报告"})
        for r in rs:
            if not r.get("meta_type"):
                issues.append({"level": "warn", "type": "META缺失", "date": d,
                               "target": "%s/%s" % (r["date"], r["type"]), "detail": "缺少 META 元数据块"})
            if len(r.get("entries", [])) < 5:
                issues.append({"level": "warn", "type": "条目过少", "date": d,
                               "target": "%s/%s" % (r["date"], r["type"]),
                               "detail": "仅解析出 %d 条知识点" % len(r.get("entries", []))})
    # ---------- 2. 板块归类 ----------
    mis = 0
    for r in reports:
        for e in r.get("entries", []):
            b = e.get("bucket")
            if b not in BUCKET_KW:
                continue
            text = (e.get("text", "") + " " + e.get("snippet", ""))
            hit = [k for k in BUCKET_KW[b] if k in text]
            if hit:
                continue
            scores = {k: len([w for w in kws if w in text]) for k, kws in BUCKET_KW.items()}
            best = max(scores, key=scores.get)
            suggest = best if scores[best] > 0 else "（无明显特征，建议人工判断）"
            mis += 1
            issues.append({"level": "warn", "type": "板块归类存疑", "date": r["date"],
                           "target": e.get("text", "")[:46], "detail": "标注为「%s」但未见该板块特征词；更像：%s" % (b, suggest)})
    stats["归类存疑数"] = mis
    # ---------- 3. 能力边界矛盾 ----------
    import build_site
    conflicts = 0
    checked = 0
    for r in reports:
        if r["type"] != "journal":
            continue
        try:
            bounds = build_site.parse_boundaries(r)
        except Exception:  # noqa: BLE001
            continue
        for topic, v in bounds.items():
            must, skip = v.get("must", []), v.get("skip", [])
            if not must and not skip:
                continue
            checked += 1
            for m in must:
                for s in skip:
                    a = re.sub(r"[\s，。：:；;、（）()\-—]", "", m)
                    b2 = re.sub(r"[\s，。：:；;、（）()\-—]", "", s)
                    if a and b2 and (a == b2 or (len(a) > 8 and a in b2) or (len(b2) > 8 and b2 in a)):
                        conflicts += 1
                        issues.append({"level": "error", "type": "边界自相矛盾", "date": r["date"],
                                       "target": topic[:30], "detail": "同一条既在必须掌握又在不必深入"})
            for m in must:
                if any(t in m for t in DEEP_TERMS):
                    issues.append({"level": "warn", "type": "边界存疑(必须掌握疑似过深)", "date": r["date"],
                                   "target": topic[:26], "detail": m[:60]})
            for s in skip:
                if any(t in s for t in PM_ACTION_TERMS):
                    issues.append({"level": "warn", "type": "边界存疑(不必深入疑似是PM职责)", "date": r["date"],
                                   "target": topic[:26], "detail": s[:60]})
    stats["校验知识点数"] = checked
    stats["边界冲突数"] = conflicts
    # ---------- 4. 来源覆盖 ----------
    total_news = src_ok = 0
    for r in reports:
        p = find_md(r)
        if not p:
            continue
        md = open(p, encoding="utf-8").read()
        for e in r.get("entries", []):
            if e.get("kind") != "news":
                continue
            total_news += 1
            if e.get("text", "")[:12] and e["text"][:12] in md and "来源" in md:
                src_ok += 1
    stats["资讯条目数"] = total_news
    stats["来源覆盖率"] = ("%d%%" % round(src_ok / total_news * 100)) if total_news else "—"
    # ---------- 5. 抽检清单 ----------
    latest = dates[0] if dates else ""
    pool = [e for r in reports if r["date"] == latest for e in r.get("entries", [])]
    rnd = random.Random("sample" + latest)
    rnd.shuffle(pool)
    sample = []
    seen_b = set()
    for e in pool:
        if e.get("bucket") in seen_b:
            continue
        seen_b.add(e.get("bucket"))
        sample.append({"date": latest, "bucket": e.get("bucket"), "text": e.get("text"),
                       "snippet": (e.get("snippet") or "")[:120],
                       "how": "回到当日原报告核对：数字/主体/生效时间是否与来源一致"})
        if len(sample) == 3:
            break
    stats["抽检条数"] = len(sample)

    report = {"generated": data["generated"], "dates": dates, "stats": stats,
              "issues": issues, "sample": sample,
              "issue_count": {"error": len([i for i in issues if i["level"] == "error"]),
                              "warn": len([i for i in issues if i["level"] == "warn"])}}
    out = os.path.join(BASE, "docs", "qa-report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("内容质量校验完成 →", out)
    print("  结构/边界错误 %d 条 ｜ 疑点 %d 条 ｜ 抽检 %d 条"
          % (report["issue_count"]["error"], report["issue_count"]["warn"], len(sample)))
    print("  来源覆盖率 %s ｜ 归类存疑 %s ｜ 校验知识点 %s"
          % (stats["来源覆盖率"], stats["归类存疑数"], stats["校验知识点数"]))
    for i in [x for x in issues if x["level"] == "error"][:5]:
        print("  [错误] %s | %s | %s" % (i["type"], i["target"], i["detail"][:60]))
    for i in [x for x in issues if x["level"] == "warn"][:6]:
        print("  [疑点] %s | %s | %s" % (i["type"], i["target"], i["detail"][:60]))


if __name__ == "__main__":
    main()
