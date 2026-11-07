# -*- coding: utf-8 -*-
"""
芽课 · 工作台构建（P0）
把 payload.json 内联进 template-v2.html，产出单文件 HTML。
用法：python build_workbench.py
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(BASE, "template-v2.html")
PAYLOAD = os.path.join(BASE, "..", "05-工作台成品", "payload.json")
OUT = os.path.join(BASE, "..", "05-工作台成品", "芽课个人工作库.html")
MARK_A = "/*__PAYLOAD__*/"
MARK_B = "/*__END__*/"


def main():
    if "--no-ingest" not in sys.argv:
        r = subprocess.run([sys.executable, os.path.join(BASE, "ingest.py")],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print("ingest 失败：\n" + (r.stderr or r.stdout))
            sys.exit(1)
        print(r.stdout.strip())
        print("-" * 52)

    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    with open(PAYLOAD, encoding="utf-8") as f:
        data = json.load(f)

    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # 防止内容里的 </script> 提前闭合标签
    blob = blob.replace("</", "<\\/")

    i, j = tpl.find(MARK_A), tpl.find(MARK_B)
    if i < 0 or j < 0:
        print("模板缺少注入标记")
        sys.exit(1)
    html = tpl[:i] + blob + tpl[j + len(MARK_B):]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(OUT) / 1024
    print(f"输出  {os.path.abspath(OUT)}")
    print(f"体积  {size:.0f} KB（数据 {len(blob)/1024:.0f} KB）")
    print(f"检查  外链 {html.count('http://') + html.count('https://')} 处 · script 标签 {html.count('<script')} 个")


if __name__ == "__main__":
    main()
