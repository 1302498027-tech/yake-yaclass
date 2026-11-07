# -*- coding: utf-8 -*-
"""
芽课 · 本地数据库层（SQLite，单文件：data/sprout.db）
设计原则：
  - 与云端兼容：将来把 server.py + 本文件搬上云即可，表结构不变
  - 行为数据四张表：reads（打卡）/ stars（收藏）/ answers（答题）/ notes（笔记，预留）
  - 线程安全：每次操作独立连接（http.server ThreadingHTTPServer 多线程）
"""
import json
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "data", "sprout.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS reads(
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY(date,type)
        );
        CREATE TABLE IF NOT EXISTS stars(
            key TEXT PRIMARY KEY,
            date TEXT, label TEXT, bucket TEXT,
            text TEXT, snippet TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS answers(
            qid TEXT PRIMARY KEY,
            picked INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            answered_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(date,type)
        );
        """)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---- 打卡 ----
def set_read(date, rtype, value):
    with _conn() as c:
        if value:
            c.execute("INSERT OR REPLACE INTO reads(date,type,read_at) VALUES(?,?,?)",
                      (date, rtype, _now()))
        else:
            c.execute("DELETE FROM reads WHERE date=? AND type=?", (date, rtype))


# ---- 收藏 ----
def toggle_star(item):
    with _conn() as c:
        row = c.execute("SELECT 1 FROM stars WHERE key=?", (item.get("key", ""),)).fetchone()
        if row:
            c.execute("DELETE FROM stars WHERE key=?", (item["key"],))
            return False  # 取消收藏后
        c.execute("INSERT INTO stars(key,date,label,bucket,text,snippet,created_at) VALUES(?,?,?,?,?,?,?)",
                  (item.get("key", ""), item.get("date", ""), item.get("label", ""),
                   item.get("bucket", ""), item.get("text", ""), item.get("snippet", ""), _now()))
        return True


# ---- 答题 ----
def record_answer(qid, picked, correct):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO answers(qid,picked,correct,answered_at) VALUES(?,?,?,?)",
                  (qid, int(picked), int(correct), _now()))


def clear_quiz():
    with _conn() as c:
        c.execute("DELETE FROM answers")


# ---- 汇总状态（前端启动时拉取） ----
def get_state():
    with _conn() as c:
        read_map = {}
        for d, t in c.execute("SELECT date,type FROM reads"):
            read_map.setdefault(d, {})[t] = True
        stars = []
        for r in c.execute("SELECT key,date,label,bucket,text,snippet FROM stars ORDER BY created_at DESC"):
            stars.append({"key": r[0], "date": r[1], "label": r[2],
                          "bucket": r[3], "text": r[4], "snippet": r[5]})
        answers = {}
        for qid, picked, correct in c.execute("SELECT qid,picked,correct FROM answers"):
            answers[qid] = {"picked": picked, "correct": correct}
    return {"read": read_map, "stars": stars, "answers": answers}


if __name__ == "__main__":
    init()
    print("数据库已初始化:", DB_PATH)
    print("当前状态:", json.dumps(get_state(), ensure_ascii=False)[:200])
