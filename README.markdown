# asgi-cgi-handler

- run cgi scripts inside an asgi server


- simple usage
```python
from fastapi import FastAPI
from asgi_cgi import HTTPCGIHandler, WebsocketCGIHandler

app = FastAPI(title="CGI Server")

app.mount("/cgi-bin", HTTPCGIHandler())  # type: ignore
app.mount("/ws", WebsocketCGIHandler())
```
As you can see, we have websocket support, which is inspired by
[websocketd](https://github.com/joewalnes/websocketd). Currently, more tests are needed.


## Apis

```python
ErrHandler = Callable[[bytes], Union[Awaitable[None], None]]

class HTTPCGIHandler:
    def __init__(self, directory: str=..., error_handler: ErrHandler=...) -> None: ...

class WebsocketCGIHandler:
    def __init__(self, directory: str=..., error_handler: ErrHandler=...) -> None: ...

```