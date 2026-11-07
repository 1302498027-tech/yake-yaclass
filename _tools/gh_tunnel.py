#!/usr/bin/env python3
"""GitHub 本地转发通道。

本机 DNS 解析到的 github.com IP（20.205.243.166）在 443 上被重置，
但 GitHub 还有若干入口 IP 是通的。这个脚本在本机起一个 CONNECT 代理，
把发往 github.com:443 的流量改接到可用 IP，TLS 的 SNI 与证书保持不变，
所以 git、浏览器都不会报证书错误。

用法：
    python _tools/gh_tunnel.py            # 监听 127.0.0.1:8899
    git -c http.proxy=http://127.0.0.1:8899 push
    # 浏览器：把 HTTP/HTTPS 代理设为 127.0.0.1:8899

IP 变了就改下面的 CANDIDATES（按顺序探测，第一个通的会被采用）。
"""
import socket
import sys
import threading
import time

LISTEN = ("127.0.0.1", 8899)
HOSTS = {"github.com", "www.github.com", "gist.github.com", "github.io"}
CANDIDATES = [
    "140.82.116.3",
    "140.82.121.3",
    "140.82.112.4",
    "20.27.177.113",
    "20.200.245.247",
    "4.237.22.38",
    "20.87.245.0",
    "20.175.192.147",
    "20.207.73.82",
    "20.233.83.145",
]
UPSTREAM = None
LOCK = threading.Lock()


def alive(ip, timeout=4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, 443))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_upstream():
    """探测出一个 443 可用的 GitHub 入口。"""
    for ip in CANDIDATES:
        if alive(ip):
            print(f"[tunnel] 采用入口 {ip}", flush=True)
            return ip
    return None


def repick(bad=None):
    """当前入口失效时换一个。"""
    global UPSTREAM
    with LOCK:
        if bad is not None and UPSTREAM != bad:
            return UPSTREAM          # 别的线程已经换过了
        new = pick_upstream()
        if new:
            UPSTREAM = new
        return UPSTREAM


def watchdog():
    """入口 IP 会不时被封，定期体检，掉了就换。"""
    while True:
        time.sleep(30)
        cur = UPSTREAM
        if cur and not alive(cur):
            print(f"[tunnel] 入口 {cur} 失联，重新探测", flush=True)
            repick(bad=cur)


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def handle(client):
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(4096)
            if not chunk:
                client.close()
                return
            head += chunk
            if len(head) > 65536:
                client.close()
                return

        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split()
        if len(parts) < 2 or parts[0] != "CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            client.close()
            return

        host, _, port = parts[1].partition(":")
        port = int(port or 443)
        host = host.lower()

        if host in HOSTS and UPSTREAM:
            upstream = (UPSTREAM, 443)
        else:
            upstream = (host, port)

        remote = socket.socket()
        remote.settimeout(15)
        try:
            remote.connect(upstream)
        except OSError as e:
            if host not in HOSTS:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                print(f"[tunnel] {host}:{port} 失败 {e}", flush=True)
                client.close()
                return
            # GitHub 入口掉了，换一个再试一次
            print(f"[tunnel] 入口 {UPSTREAM} 连接失败，切换", flush=True)
            new = repick(bad=UPSTREAM)
            if not new:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                client.close()
                return
            remote = socket.socket()
            remote.settimeout(15)
            try:
                remote.connect((new, 443))
            except OSError as e2:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                print(f"[tunnel] 备用入口 {new} 也失败 {e2}", flush=True)
                client.close()
                return

        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        client.settimeout(None)
        remote.settimeout(None)
        threading.Thread(target=pipe, args=(client, remote), daemon=True).start()
        threading.Thread(target=pipe, args=(remote, client), daemon=True).start()
    except OSError:
        try:
            client.close()
        except OSError:
            pass


def main():
    global UPSTREAM
    UPSTREAM = pick_upstream()
    if not UPSTREAM:
        print("[tunnel] 所有入口都连不上，放弃")
        return 1
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(64)
    print(f"[tunnel] 监听 {LISTEN[0]}:{LISTEN[1]} → github.com 走 {UPSTREAM}", flush=True)
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        while True:
            c, _ = srv.accept()
            threading.Thread(target=handle, args=(c,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
