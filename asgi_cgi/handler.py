import asyncio
import base64
import binascii
import http.server
import os
import posixpath
import sys
from copy import deepcopy
from typing import cast
from urllib.parse import unquote

import hypercorn
from starlette.concurrency import run_in_threadpool, run_until_first_complete
from starlette.requests import Request

from asgi_cgi.typing import ErrHandler, Receive, Send
from asgi_cgi.utils import parse_header_and_body
from asgi_cgi.version import __version__

SERVER_SOFTWARE = f"asgi_cgi/{__version__}"


async def _base_err_handler(stderr: bytes):
    sys.stderr.write(stderr)  # type: ignore
    sys.stderr.flush()


class BaseCGIHandler:
    def __init__(self, directory: str = None, error_handler: ErrHandler = None):
        """

        :param directory:
        :param error_handler: what to do if cgi script write something to stderr
        """
        self.directory = directory or os.getcwd()
        self.error_handler = error_handler or _base_err_handler
        self.scope: dict
        self.receive: Receive
        self.send: Send
        self.request: Request
        self.closed = False

    async def __call__(self, scope: dict, receive: Receive, send: Send):
        self.scope = scope
        self.receive = receive  # type
        self.send = send
        self.request = Request(scope, receive, send)
        await self.run_cgi()

    async def run_cgi(self):
        raise NotImplementedError

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

        env = deepcopy(os.environ)
        cmdline = []
        env["SERVER_SOFTWARE"] = SERVER_SOFTWARE
        if "server" in self.scope:
            env["SERVER_NAME"] = self.scope["server"][0]
            env["SERVER_PORT"] = str(self.scope["server"][1])
        env["GATEWAY_INTERFACE"] = "CGI/1.1"
        env["SERVER_PROTOCOL"] = "HTTP/" + self.scope["http_version"]
        env["REQUEST_METHOD"] = self.request.method
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
        for k in ('QUERY_STRING', 'REMOTE_HOST', 'CONTENT_LENGTH',
                  'HTTP_USER_AGENT', 'HTTP_COOKIE', 'HTTP_REFERER'):
            env.setdefault(k, "")

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
        stdout, stderr = await process.communicate(body)
        if stderr:
            if asyncio.iscoroutinefunction(self.error_handler):
                asyncio.create_task(self.error_handler(stderr))
            else:
                asyncio.create_task(run_in_threadpool(self.error_handler, stderr))
        status, response_header, response_body = parse_header_and_body(b"HTTP/1.1 200 OK\r\n"+stdout)
        await self.send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": response_header,
            }
        )
        await self.send({"type": "http.response.body", "body": response_body})
        return_code = await process.wait()
        if return_code:
            pass  # todo should we log

    async def return_error(self, code: int, body: bytes):
        await self.send({"type": "http.response.start", "status": code})
        await self.send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )


class WebsocketCGIHandler(BaseCGIHandler):
    async def run_cgi(self):
        if self.scope["type"] != "websocket":
            return
        env = deepcopy(os.environ)
        cmdline = []
        env["SERVER_SOFTWARE"] = SERVER_SOFTWARE
        if "server" in self.scope:
            env["SERVER_NAME"] = self.scope["server"][0]
            env["SERVER_PORT"] = str(self.scope["server"][1])
        env["GATEWAY_INTERFACE"] = "CGI/1.1"
        env["SERVER_PROTOCOL"] = "HTTP/" + self.scope["http_version"]
        env["REQUEST_METHOD"] = self.request.method
        path: str = self.scope["path"]
        env["PATH_INFO"] = path.rpartition("/")[0]
        env["PATH_TRANSLATED"] = self.translate_path(path.rpartition("/")[0])
        env["SCRIPT_NAME"] = path
        if query := self.scope["query_string"]:
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
        for k in ('QUERY_STRING', 'REMOTE_HOST', 'CONTENT_LENGTH',
                  'HTTP_USER_AGENT', 'HTTP_COOKIE', 'HTTP_REFERER'):
            env.setdefault(k, "")

        script_file = self.translate_path(path)
        if not os.path.exists(script_file):
            await self.send({"type": "websocket.close"})
            return

        process = await asyncio.create_subprocess_exec(
            script_file,
            *cmdline,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await self.send({"type": "websocket.accept"})
        await run_until_first_complete(
            (self.read_process_output, {"process": process}),
            (self.read_client_input, {"process": process}),
            (self.read_process_error, {"process": process}),
            (process.wait, {}),
        )
        if not self.closed:  # script itself exit
            status = process.returncode
            if status:
                code = 1006  # todo log?
            else:
                code = 1000
            await self.send(
                {"type": "websocket.close", "code": code, "reason": "script exit"}
            )

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
        while line := await process.stderr.readline():
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
