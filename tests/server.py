"""
Copyright (c) 2008-2023 synodriver <diguohuangjiajinweijun@gmail.com>
"""
from fastapi import FastAPI
from asgi_cgi import HTTPCGIHandler, WebsocketCGIHandler, SSECGIHandler

app = FastAPI(title="CGI Server")
app.mount("/cgi-bin", HTTPCGIHandler())
app.mount("/ws", WebsocketCGIHandler())


if __name__ == "__main__":
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    import asyncio

    conf = Config()
    conf.bind = "127.0.0.1:9000"
    conf.loglevel = "DEBUG"
    asyncio.run(serve(app, conf))