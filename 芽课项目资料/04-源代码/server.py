# -*- coding: utf-8 -*-
"""
PM 学习工作台 · 本地服务
提供桌面应用模式的数据接口与页面：
  GET /            实时渲染工作台页面
  GET /api/data    实时聚合数据 JSON
  GET /api/refresh 强制重新扫描并返回
端口 8848，Ctrl+C 停止。
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import pathname2url

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import build  # noqa: E402
import db  # noqa: E402

db.init()

PORT = 8848
SRC_DIRS = {s["key"]: s["path"] for s in build.SOURCES}
FILE_TYPES = {".pdf": "application/pdf", ".md": "text/plain", ".html": "text/html"}
PM_SITE = os.path.join(BASE, "pm")  # 科普站静态目录（build.py 从 pm-site 复制）
PM_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
            ".json": "application/json", ".png": "image/png", ".ico": "image/x-icon",
            ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff"}


def favicon_bytes():
    """芽课应用图标（icon/sprout_256.png），缺失时回退到内联 SVG"""
    p = os.path.join(BASE, "icon", "sprout_256.png")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read(), "image/png"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="8" fill="#1f9d55"/>'
           '<path d="M9 17l5 5 9-12" stroke="#fff" stroke-width="3.5" fill="none" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return svg.encode("utf-8"), "image/svg+xml"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                data = build.collect()
                html = build.render_html(data)
                # 把 file:/// 报告链接改写为服务路由，浏览器才允许从 http 页面打开
                for key, dirpath in SRC_DIRS.items():
                    html = html.replace(
                        "file:///" + pathname2url(dirpath) + "/",
                        "/files/" + key + "/",
                    )
                self._send(200, "text/html", html.encode("utf-8"))
            elif path.startswith("/files/"):
                self._serve_report_file(path)
            elif path.startswith("/pm/"):
                self._serve_pm(path)
            elif path == "/api/data":
                data = build.collect()
                self._send(200, "application/json", json.dumps(data, ensure_ascii=False).encode("utf-8"))
            elif path == "/api/state":
                self._send(200, "application/json", json.dumps(db.get_state(), ensure_ascii=False).encode("utf-8"))
            elif path == "/favicon.ico":
                body, ctype = favicon_bytes()
                self._send(200, ctype, body)
            else:
                self._send(404, "text/plain", b"not found")
        except Exception as e:  # noqa: BLE001
            try:
                self._send(500, "text/plain", ("server error: %s" % e).encode("utf-8"))
            except Exception:  # noqa: BLE001
                pass

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if path == "/api/read":
                db.set_read(str(body.get("date", "")), str(body.get("type", "")), bool(body.get("value")))
                self._send(200, "application/json", b'{"ok":true}')
            elif path == "/api/star":
                starred = db.toggle_star(body.get("item") or {})
                self._send(200, "application/json", json.dumps({"ok": True, "starred": starred}).encode("utf-8"))
            elif path == "/api/answer":
                db.record_answer(str(body.get("qid", "")), body.get("picked", -1),
                                 1 if body.get("correct") else 0)
                self._send(200, "application/json", b'{"ok":true}')
            elif path == "/api/quiz-clear":
                db.clear_quiz()
                self._send(200, "application/json", b'{"ok":true}')
            else:
                self._send(404, "text/plain", b"not found")
        except Exception as e:  # noqa: BLE001
            try:
                self._send(500, "text/plain", ("server error: %s" % e).encode("utf-8"))
            except Exception:  # noqa: BLE001
                pass

    def _serve_pm(self, path):
        """科普站静态文件（/pm/... → pm/ 目录，路径规整防目录穿越）"""
        rel = os.path.normpath(path[len("/pm/"):]).lstrip("\\/").replace("/", os.sep)
        if rel.startswith(".."):
            return self._send(404, "text/plain", b"not found")
        fpath = os.path.join(PM_SITE, rel)
        if not os.path.isfile(fpath):
            return self._send(404, "text/plain", b"not found")
        ext = os.path.splitext(fpath)[1].lower()
        with open(fpath, "rb") as f:
            body = f.read()
        self._send(200, PM_TYPES.get(ext, "application/octet-stream"), body)

    def _serve_report_file(self, path):
        """托管三个任务 outputs 目录中的报告文件（白名单校验，禁止目录穿越）"""
        rest = path[len("/files/"):]
        parts = rest.split("/", 1)
        if len(parts) != 2 or parts[0] not in SRC_DIRS:
            return self._send(404, "text/plain", b"not found")
        key, fname = parts[0], parts[1]
        if not re.fullmatch(r"[\w][\w\-.]*", fname):
            return self._send(404, "text/plain", b"not found")
        fpath = os.path.join(SRC_DIRS[key], fname)
        if not os.path.isfile(fpath):
            return self._send(404, "text/plain", b"file not found")
        ext = os.path.splitext(fname)[1].lower()
        ctype = FILE_TYPES.get(ext, "application/octet-stream")
        with open(fpath, "rb") as f:
            body = f.read()
        self._send(200, ctype, body)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("芽课 · PM 学习工作台服务已启动: http://127.0.0.1:%d/" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
