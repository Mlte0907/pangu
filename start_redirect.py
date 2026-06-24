"""盘古 HTTP→HTTPS 重定向服务器

在 19528 端口运行一个轻量 HTTP 服务器，
将所有请求 301 重定向到对应的 HTTPS 地址。
"""
import asyncio
from aiohttp import web


async def redirect_handler(request: web.Request) -> web.Response:
    """将 HTTP 请求重定向到 HTTPS"""
    path = request.path
    query = request.query_string
    url = f"https://{request.host}{path}"
    if query:
        url += f"?{query}"
    raise web.HTTPMovedPermanently(url)


def create_redirect_app() -> web.Application:
    return web.Application()
    app.router.add_route("*", "/{path_info:.*}", redirect_handler)
    return app


if __name__ == "__main__":
    app = create_redirect_app()
    web.run_app(app, host="0.0.0.0", port=19528, print=None)
