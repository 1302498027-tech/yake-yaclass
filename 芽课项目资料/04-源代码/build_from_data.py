# -*- coding: utf-8 -*-
"""
芽课工作台 · 从已有数据直接构建（不经 outputs 扫描）

用途：
  build.py 会扫描 WorkBuddy automation outputs 目录重新聚合，
  但那些目录在 2026-09-19 之后停止更新；2026-09-19 至 2026-10-23
  的 34 天内容只存在于线上 payload 中。

  本脚本直接读取 data/reports.json（完整数据快照），
  套用 template.html 生成 index.html，保证源码能独立产出完整版。

用法：
  python build_from_data.py

数据来源优先级：
  1. data/reports.json      （完整快照，39 天）
  2. data/payload-live.json （线上 payload 原始 JSON）

环境变量：
  YAKE_DATA=路径   指定数据文件
"""

import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def load_data():
    """读取完整数据快照"""
    env = os.environ.get("YAKE_DATA")
    candidates = [env] if env else []
    candidates += [
        os.path.join(BASE, "data", "reports.json"),
        os.path.join(BASE, "data", "payload-live.json"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "reports" not in data:
                raise RuntimeError("%s 不是有效的工作台数据（缺 reports 字段）" % path)
            print("数据来源:", path)
            return data
    raise SystemExit(
        "找不到数据文件。请确认以下任一存在：\n  " + "\n  ".join(candidates[1:])
    )


def render_html(data):
    """把数据注入模板"""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tpl_path = os.path.join(BASE, "template.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        template = f.read()
    if "__PAYLOAD__" not in template:
        raise RuntimeError("template.html 缺少 __PAYLOAD__ 占位符")
    return template.replace("__PAYLOAD__", payload)


def main():
    data = load_data()
    html = render_html(data)
    out = os.path.join(BASE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("日期数:", len(data.get("dates", [])),
          "报告数:", len(data.get("reports", [])),
          "关联提示:", len(data.get("hints", [])),
          "题库:", len(data.get("quiz", [])))
    print("数据生成时间:", data.get("generated", "—"))
    print("已生成:", out)
    print()
    print("下一步：把 index.html 复制到 09-线上部署 并部署，")
    print("        或直接双击 ../05-工作台成品/芽课工作台-双击打开.html 查看（需先复制）")


if __name__ == "__main__":
    main()
