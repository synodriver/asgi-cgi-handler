import os
from typing import Sequence, Tuple

import h11


def parse_header_and_body(
    raw_body: bytes,
) -> Tuple[int, Sequence[Tuple[bytes, bytes]], bytes]:
    """
    parse data into status code, header and body
    :param raw_body: header and body
    :return:
    """
    connection = h11.Connection(h11.CLIENT)
    connection.receive_data(raw_body)
    status = None
    headers = None
    body = None
    while True:
        event = connection.next_event()
        if isinstance(event, h11.Response):
            status = event.status_code
            headers = event.headers
        elif isinstance(event, h11.Data):
            body = event.data
        elif isinstance(event, h11.NEED_DATA):
            break
    if not all((status, headers, body)):
        raise ValueError("invalid cgi response")
    return status, headers, body  # type: ignore


def is_python(path: str) -> bool:
    """Test whether argument path is a Python script."""
    head, tail = os.path.splitext(path)
    return tail.lower() in (".py", ".pyw")
