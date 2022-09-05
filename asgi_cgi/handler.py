import asyncio
import base64
import binascii
import os
import posixpath
import sys
from copy import deepcopy
from typing import List, MutableMapping, Tuple
from urllib.parse import unquote

from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool, run_until_first_complete
from starlette.requests import HTTPConnection, Request
from starlette.websockets import WebSocket

from asgi_cgi.typing import ErrHandler, Receive, Send
from asgi_cgi.utils import parse_header_and_body
from asgi_cgi.version import __version__

SERVER_SOFTWARE = f"asgi-cgi/{__version__}"


async def _base_err_handler(stderr: bytes):
    sys.stderr.write(stderr)  # type: ignore
    sys.stderr.flush()


class BaseCGIHandler:
    def __init__(
        self,
        directory: str = None,
        error_handler: ErrHandler = None,
        timeout: float = 1.0,
        max_process: int = 10,
    ):
        """

        :param directory: CGI root.
        :param error_handler: Called when scripts write something to stderr.
        :param timeout: If client disconnect, wait process for timeout second until it exits. For CGI scripts,
        they can't run more than timeout second.
        :param max_process: Limit max process count to prevent from dos attack.
        """
        self.directory = directory or os.getcwd()
        self.error_handler = error_handler or _base_err_handler
        self.timeout = timeout
        self._sem = asyncio.Semaphore(max_process)
        self.scope: dict
        self.receive: Receive
        self.send: Send
        self.request: HTTPConnection
        self.closed = False

    async def __call__(self, scope: dict, receive: Receive, send: Send):
        self.scope = scope
        self.receive = receive  # type
        self.send = send
        if scope["type"] == "http":
            self.request = Request(scope, receive, send)  # todo add starlette websocket
        elif scope["type"] == "websocket":
            self.request = WebSocket(scope, receive, send)
        async with self._sem:
            await self.run_cgi()

    async def run_cgi(self):
        raise NotImplementedError

    def prepare_env_and_cmd(self) -> Tuple[MutableMapping, List[str]]:
        env = deepcopy(os.environ)
        cmdline: List[str] = []
        env["SERVER_SOFTWARE"] = SERVER_SOFTWARE
        if "server" in self.scope:
            env["SERVER_NAME"] = self.scope["server"][0]
            env["SERVER_PORT"] = str(self.scope["server"][1])
        env["GATEWAY_INTERFACE"] = "CGI/1.1"
        env["SERVER_PROTOCOL"] = "HTTP/" + self.scope["http_version"]
        env["REQUEST_METHOD"] = self.scope.get("method", "GET")
        path: str = self.scope["path"]
        env["PATH_INFO"] = path
        env["PATH_TRANSLATED"] = self.translate_path(path)
        env["SCRIPT_NAME"] = path.rpartition("/")[-1]
        if query := self.scope["query_string"]:
            if query:
                env["QUERY_STRING"] = query.decode()
            if b"=" not in query:
                cmdline.append(query.decode())
        env["REMOTE_ADDR"] = self.request.client.host
        authorization = self.request.headers.get("authorization")
        if authorization:
            authorization = authorization.split()
            if len(authorization) == 2:

                env["AUTH_TYPE"] = authorization[0]
                if authorization[0].lower() == "basic":
                    try:
                        authorization = authorization[1].encode("ascii")
                        authorization = base64.decodebytes(authorization).decode(
                            "ascii"
                        )
                    except (binascii.Error, UnicodeError):
                        pass
                    else:
                        authorization = authorization.split(":")
                        if len(authorization) == 2:
                            env["REMOTE_USER"] = authorization[0]

        for k, v in self.request.headers.items():
            env[f"HTTP_{k.replace('-', '_').upper()}"] = v
        for k in (
            "QUERY_STRING",
            "REMOTE_HOST",
            "CONTENT_LENGTH",
            "HTTP_USER_AGENT",
            "HTTP_COOKIE",
            "HTTP_REFERER",
        ):
            env.setdefault(k, "")
        return env, cmdline

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)

        """
        # abandon query parameters
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith("/")
        try:
            path = unquote(path, errors="surrogatepass")
        except UnicodeDecodeError:
            path = unquote(path)
        path = posixpath.normpath(path)
        words = path.split("/")
        words = filter(None, words)
        path = self.directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += "/"
        return path


class HTTPCGIHandler(BaseCGIHandler):
    async def run_cgi(self):
        if self.scope["type"] != "http":
            return
        body = None
        if self.request.method == "POST":
            body = await self.request.body()

        env, cmdline = self.prepare_env_and_cmd()
        path = self.scope["path"]
        script_file = self.translate_path(path)
        if not os.path.exists(script_file):
            await self.return_error(
                404, f"No such CGI script {path.rpartition('/')[-1]}".encode()
            )
            return
        if not os.path.isfile(script_file):
            await self.return_error(
                403,
                f"CGI script is not a plain file {path.rpartition('/')[-1]}".encode(),
            )
            return

        process = await asyncio.create_subprocess_exec(
            script_file,
            *cmdline,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(body), self.timeout
            )
            if stderr:
                if asyncio.iscoroutinefunction(self.error_handler):
                    asyncio.create_task(self.error_handler(stderr))
                else:
                    asyncio.create_task(run_in_threadpool(self.error_handler, stderr))
            status, response_header, response_body = parse_header_and_body(
                b"HTTP/1.1 200 OK\r\n" + stdout
            )
            await self.send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": response_header,
                }
            )
            await self.send({"type": "http.response.body", "body": response_body})
            return_code = process.returncode
            if return_code:
                pass  # todo should we log
        except asyncio.TimeoutError:  # CGI script execute more than self.timeout
            pass  # todo should we log
        finally:  # ensure process is killed
            if process.returncode is None:
                process.terminate()

    async def return_error(self, code: int, body: bytes):
        await self.send({"type": "http.response.start", "status": code})
        await self.send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )


class WebsocketCGIHandler(BaseCGIHandler):
    """
    Feed websocket data into stdin, and send stdout to client.
    """

    async def run_cgi(self):
        if self.scope["type"] != "websocket":
            return
        env, cmdline = self.prepare_env_and_cmd()
        path = self.scope["path"]
        script_file = self.translate_path(path)
        await self.receive()  # wesocket.connect
        if not os.path.exists(script_file) or not os.path.isfile(script_file):
            await self.send({"type": "websocket.close"})
            return
        await self.send({"type": "websocket.accept"})
        process = await asyncio.create_subprocess_exec(
            script_file,
            *cmdline,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            await run_until_first_complete(
                (self.read_process_output, {"process": process}),
                (self.read_client_input, {"process": process}),
                # (process.wait, {}),
            )
            await asyncio.wait_for(
                self.read_process_error(process), self.timeout
            )  # handle stderr
            status = await asyncio.wait_for(process.wait(), self.timeout)
            if status:
                code = 1006  # todo log?
            else:
                code = 1000
            await self.send(
                {"type": "websocket.close", "code": code, "reason": "script exit"}
            )
        except asyncio.TimeoutError:
            pass
        finally:
            if process.returncode is None:
                process.terminate()

    async def read_process_output(self, process: asyncio.subprocess.Process):
        assert process.stdout is not None
        # stdout = cast(asyncio.StreamReader, process.stdout)
        while line := await process.stdout.readline():
            try:
                await self.send({"type": "websocket.send", "text": line.decode()})
            except UnicodeDecodeError:
                await self.send({"type": "websocket.send", "bytes": line})

    async def read_process_error(self, process: asyncio.subprocess.Process):
        assert process.stderr is not None
        if line := await process.stderr.read():  # readall
            if asyncio.iscoroutinefunction(self.error_handler):
                await self.error_handler(line)  # type: ignore
            else:
                await run_in_threadpool(self.error_handler, line)

    async def read_client_input(self, process: asyncio.subprocess.Process):
        assert process.stdin is not None
        while True:
            data = await self.receive()
            if data["type"] == "websocket.disconnect":
                self.closed = True
                break
            if text := data.get("text"):
                process.stdin.write(text.encode())
            elif bt := data.get("bytes"):
                process.stdin.write(bt)
            await process.stdin.drain()


async def read_process_output(process: asyncio.subprocess.Process):
    assert process.stdout is not None
    # stdout = cast(asyncio.StreamReader, process.stdout)
    while line := await process.stdout.readline():
        yield ServerSentEvent(data=line.decode())


class SSECGIHandler(HTTPCGIHandler):
    """
    Send stdout to client as event source response.
    """

    async def run_cgi(self):
        if self.scope["type"] != "http":
            return
        body = None
        if self.request.method == "POST":
            body = await self.request.body()

        env, cmdline = self.prepare_env_and_cmd()
        path = self.scope["path"]
        script_file = self.translate_path(path)
        if not os.path.exists(script_file):
            await self.return_error(
                404, f"No such CGI script {path.rpartition('/')[-1]}".encode()
            )
            return
        if not os.path.isfile(script_file):
            await self.return_error(
                403,
                f"CGI script is not a plain file {path.rpartition('/')[-1]}".encode(),
            )
            return

        process = await asyncio.create_subprocess_exec(
            script_file,
            *cmdline,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            if body:
                process.stdin.write(body)
                await process.stdin.drain()
            await EventSourceResponse(read_process_output(process))(
                self.scope, self.receive, self.send
            )  # client disconnect is handled by sse-starlette
            stderr = await asyncio.wait_for(process.stderr.read(), self.timeout)
            if stderr:
                if asyncio.iscoroutinefunction(self.error_handler):
                    asyncio.create_task(self.error_handler(stderr))
                else:
                    asyncio.create_task(run_in_threadpool(self.error_handler, stderr))
            return_code = await asyncio.wait_for(process.wait(), self.timeout)
            if return_code:
                pass  # todo should we log
        except asyncio.TimeoutError:  # client disconnect but script does not exit
            pass  # todo
        finally:
            if process.returncode is None:
                process.terminate()
