#!/usr/bin/env python3
"""
OAuth2 中间层代理脚本。

监听本机 8000 端口，接收对 /api/profile 的请求，转发到
http://example.com/oauth2/profile，并在返回的 JSON 中根据 id 字段
补充一个 email 字段（id + "@example.com"），最后把结果返回给调用方。

仅使用标准库实现，无需额外安装依赖，直接运行:
    python3 oauth2_proxy.py
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LISTEN_PORT = 8000
PROXY_PATH = "/api/profile"
UPSTREAM_URL = "https://pass.hust.edu.cn/cas/oauth2.0/profile"
EMAIL_DOMAIN = "@hust.edu.cn"
UPSTREAM_TIMEOUT_SECONDS = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("oauth2_proxy")


class ProfileProxyHandler(BaseHTTPRequestHandler):
    """处理 /api/profile 请求并转发到上游 OAuth2 服务。"""

    def do_GET(self) -> None:
        self._handle_request("GET")

    def do_POST(self) -> None:
        self._handle_request("POST")

    def _handle_request(self, method: str) -> None:
        if self.path != PROXY_PATH:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        try:
            upstream_json = self._forward_to_upstream(method, body)
        except HTTPError as exc:
            logger.warning("上游返回错误状态码: %s", exc.code)
            self._send_json(exc.code, {"error": f"upstream error: {exc.code}"})
            return
        except URLError as exc:
            logger.error("请求上游失败: %s", exc)
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "failed to reach upstream"})
            return
        except json.JSONDecodeError:
            logger.error("上游返回内容不是合法 JSON")
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "upstream returned invalid json"})
            return

        profile_id = upstream_json.get("id")
        if profile_id is None:
            logger.warning("上游 JSON 缺少 id 字段: %s", upstream_json)
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "upstream response missing 'id' field"})
            return

        upstream_json["email"] = f"{profile_id}{EMAIL_DOMAIN}"
        self._send_json(HTTPStatus.OK, upstream_json)

    def _forward_to_upstream(self, method: str, body: bytes | None) -> dict:
        # 转发调用方携带的 Authorization 等鉴权头，保证上游能识别用户身份。
        forward_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in ("host", "content-length")
        }

        request = Request(UPSTREAM_URL, data=body, headers=forward_headers, method=method)
        with urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
            raw = response.read()
        return json.loads(raw)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - 匹配基类签名
        logger.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), ProfileProxyHandler)
    logger.info("代理服务已启动，监听端口 %d，转发 %s -> %s", LISTEN_PORT, PROXY_PATH, UPSTREAM_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭服务")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
