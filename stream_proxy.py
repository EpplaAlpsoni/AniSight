"""Small local HLS proxy used to attach provider-required request headers."""

import re
import secrets
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class _ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        try:
            path_parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
            if len(path_parts) != 3 or path_parts[0] != "stream":
                raise KeyError
            with self.server.stream_lock:
                upstream, referrer = self.server.streams[path_parts[1]]
        except (KeyError, IndexError, ValueError):
            self.send_error(400)
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": referrer,
        }
        if self.headers.get("Range"):
            headers["Range"] = self.headers["Range"]
        try:
            request = urllib.request.Request(upstream, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                status = response.status
                passthrough = {
                    key: response.headers[key]
                    for key in ("Content-Range", "Accept-Ranges")
                    if response.headers.get(key)
                }
        except Exception as error:
            self.send_error(502, str(error))
            return

        is_playlist = "mpegurl" in content_type.lower() or upstream.partition("?")[0].endswith(".m3u8")
        if is_playlist:
            text = body.decode("utf-8", errors="replace")

            def proxied(resource: str) -> str:
                absolute = urllib.parse.urljoin(upstream, resource)
                return self.server.proxy_url(absolute, referrer)

            lines = []
            for line in text.splitlines():
                if line and not line.startswith("#"):
                    line = proxied(line)
                elif "URI=\"" in line:
                    line = re.sub(r'URI="([^"]+)"', lambda match: f'URI="{proxied(match.group(1))}"', line)
                lines.append(line)
            body = ("\n".join(lines) + "\n").encode()
            content_type = "application/vnd.apple.mpegurl"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in passthrough.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


class StreamProxy:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
        self.server.streams = {}
        self.server.stream_tokens = {}
        self.server.stream_lock = threading.Lock()
        self.server.proxy_url = self.url_for
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url_for(self, url: str, referrer: str) -> str:
        host, port = self.server.server_address
        upstream_path = urllib.parse.urlsplit(url).path
        suffix = upstream_path.rsplit("/", 1)[-1]
        suffix = "." + suffix.rsplit(".", 1)[-1] if "." in suffix else ""
        if not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix):
            suffix = ""
        filename = f"media{suffix}" if suffix else "media.bin"
        key = (url, referrer)
        with self.server.stream_lock:
            token = self.server.stream_tokens.get(key)
            if not token:
                token = secrets.token_urlsafe(9)
                self.server.stream_tokens[key] = token
                self.server.streams[token] = key
        return f"http://{host}:{port}/stream/{token}/{filename}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
