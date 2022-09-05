<h1 align="center"><i>✨ asgi-cgi-handler ✨ </i></h1>

[![pypi](https://img.shields.io/pypi/v/asgi-cgi-handler.svg)](https://pypi.org/project/asgi-cgi-handler/)
![python](https://img.shields.io/pypi/pyversions/asgi-cgi-handler)
![implementation](https://img.shields.io/pypi/implementation/asgi-cgi-handler)
![wheel](https://img.shields.io/pypi/wheel/asgi-cgi-handler)
![license](https://img.shields.io/github/license/synodriver/asgi-cgi-handler.svg)
![action](https://img.shields.io/github/workflow/status/synodriver/asgi-cgi-handler/build%20wheel)

- run cgi scripts inside an asgi server


- simple usage
```python
import uvicorn
from asgi_cgi import HTTPCGIHandler, WebsocketCGIHandler

uvicorn.run(HTTPCGIHandler())
```

- A more complex example
```python
from fastapi import FastAPI
from asgi_cgi import HTTPCGIHandler, WebsocketCGIHandler, SSECGIHandler

app = FastAPI(title="CGI Server")

app.mount("/cgi-bin", HTTPCGIHandler())  # type: ignore
app.mount("/ws", WebsocketCGIHandler())  # type: ignore
app.mount("/sse", SSECGIHandler())  # type: ignore
```

As you can see, we have websocket support, which is inspired by
[websocketd](https://github.com/joewalnes/websocketd). Currently, more tests are needed.

The ```WebsocketCGIHandler``` route requests to endpoint executables and feed websocket data
into process's stdin and send stdout to client line by line.

The ```SSECGIHandler```, means ```server send event```, is just like the websocket one, but it only send stdout to client.


## Apis

```python
ErrHandler = Callable[[bytes], Union[Awaitable[None], None]]

class HTTPCGIHandler:
    def __init__(self, directory: str=..., error_handler: ErrHandler=...) -> None: ...

class WebsocketCGIHandler:
    def __init__(self, directory: str=..., error_handler: ErrHandler=...) -> None: ...

class SSECGIHandler:
    def __init__(self, directory: str=..., error_handler: ErrHandler=...) -> None: ...
```