#!/usr/bin/env python3
"""egress_logger: a tiny forward proxy that logs every outbound connection attempt.

Point a harness at it with HTTPS_PROXY / HTTP_PROXY to see exactly which hosts
the harness (and the commands it runs) try to reach. Hosts on the allowlist are
tunneled through; everything else is refused and logged.

    python3 egress_logger.py --port 8899 --allow llm.internal.example,127.0.0.1
    HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899 <harness command>

Standard library only. For auditing and teaching, not for production use.
"""
import argparse
import select
import socket
import socketserver
import sys
import threading
import time
from urllib.parse import urlsplit

LOCK = threading.Lock()
SEEN = {}


def log(verdict: str, host: str, port: int, detail: str = ""):
    key = (verdict, host, port)
    with LOCK:
        SEEN[key] = SEEN.get(key, 0) + 1
        stamp = time.strftime("%H:%M:%S")
        print(f"{stamp}  {verdict:<7} {host}:{port}  {detail}", flush=True)


class Handler(socketserver.StreamRequestHandler):
    allow = set()

    def allowed(self, host: str) -> bool:
        host = host.lower()
        return any(host == a or host.endswith("." + a) for a in self.allow)

    def handle(self):
        request_line = self.rfile.readline(65536).decode("latin-1").strip()
        if not request_line:
            return
        headers = []
        while True:
            line = self.rfile.readline(65536)
            if line in (b"\r\n", b"\n", b""):
                break
            headers.append(line)
        try:
            method, target, _ = request_line.split(" ", 2)
        except ValueError:
            return
        if method.upper() == "CONNECT":  # HTTPS: tunnel bytes, can't see content
            host, _, port = target.rpartition(":")
            port = int(port or 443)
            if not self.allowed(host):
                log("DENIED", host, port, "(HTTPS tunnel)")
                self.wfile.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            log("ALLOWED", host, port, "(HTTPS tunnel)")
            self.tunnel(host, port)
            return
        parts = urlsplit(target)  # plain HTTP: absolute URL in the request line
        host, port = parts.hostname or "", parts.port or 80
        if not self.allowed(host):
            log("DENIED", host, port, f"{method} {parts.path}")
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        log("ALLOWED", host, port, f"{method} {parts.path}")
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        length = 0
        kept = []
        for h in headers:
            name = h.split(b":", 1)[0].strip().lower()
            if name == b"content-length":
                length = int(h.split(b":", 1)[1])
            if name not in (b"connection", b"proxy-connection", b"keep-alive"):
                kept.append(h)
        body = self.rfile.read(length) if length else b""
        upstream = socket.create_connection((host, port), timeout=30)
        upstream.sendall(f"{method} {path or '/'} HTTP/1.1\r\n".encode("latin-1") + b"".join(kept)
                         + b"Connection: close\r\n\r\n" + body)
        try:  # relay the response until the server closes the connection
            while True:
                data = upstream.recv(65536)
                if not data:
                    break
                self.wfile.write(data)
        finally:
            upstream.close()

    def tunnel(self, host, port):
        try:
            upstream = socket.create_connection((host, port), timeout=30)
        except OSError as err:
            self.wfile.write(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{err}".encode())
            return
        self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        self.pipe(upstream)

    def pipe(self, upstream):
        client = self.connection
        try:
            while True:
                ready, _, _ = select.select([client, upstream], [], [], 60)
                if not ready:
                    break
                for sock in ready:
                    data = sock.recv(65536)
                    if not data:
                        return
                    (upstream if sock is client else client).sendall(data)
        finally:
            upstream.close()


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--allow", default="", help="comma-separated hosts (subdomains included)")
    args = parser.parse_args()
    Handler.allow = {h.strip().lower() for h in args.allow.split(",") if h.strip()}
    with Server(("127.0.0.1", args.port), Handler) as server:
        print(f"egress_logger on 127.0.0.1:{args.port}; allowed: "
              f"{', '.join(sorted(Handler.allow)) or '(nothing)'}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    print("\nsummary")
    for (verdict, host, port), n in sorted(SEEN.items()):
        print(f"  {verdict:<7} {host}:{port}  x{n}")
    sys.exit(0)


if __name__ == "__main__":
    main()
