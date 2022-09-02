"""
Copyright (c) 2008-2022 synodriver <synodriver@gmail.com>
"""
from unittest import TestCase

from asgi_cgi.utils import parse_header_and_body


class TestAll(TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_parse(self):
        status, header, body = parse_header_and_body(
            b"""HTTP/1.1 200 ok\r\nContent-Type: text/html\r\n\r\nbody"""
        )
        self.assertEqual(status, 200)
        self.assertEqual(b"text/html", dict(header)[b"content-type"])
        self.assertEqual(body, b"body")
