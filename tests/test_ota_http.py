"""Exercise fragmented and hostile HTTP framing without any network access."""
import unittest
import time
from ota_http import Response, DeviceHTTP

class Socket:
    def __init__(self, data, fragment=7): self.data,self.fragment=data,fragment
    def recv_into(self, out):
        n=min(len(out),self.fragment,len(self.data))
        out[:n]=self.data[:n];self.data=self.data[n:];return n

def response(data, limit=100):
    return Response(Socket(data),limit,lambda:None,time.monotonic()+5)

class HTTPTests(unittest.TestCase):
    def test_fragmented_content_length_and_chunked(self):
        for data in (b'HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\n{"a":1}',
                     b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\n{"a\r\n4\r\n":1}\r\n0\r\n\r\n'):
            self.assertEqual(response(data).json(),{'a':1})
    def test_rejects_ambiguous_compressed_unbounded_and_truncated(self):
        headers=(b'Content-Length: 1\r\nTransfer-Encoding: chunked',b'Content-Length: 1\r\nContent-Length: 1',
                 b'Content-Encoding: gzip\r\nContent-Length: 1',b'Content-Length: 101',b'X-Test: no-length')
        for h in headers:
            with self.assertRaises(ValueError):response(b'HTTP/1.1 200 OK\r\n'+h+b'\r\n\r\nx')
        with self.assertRaises(OSError):list(response(b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nx').chunks())
    def test_chunked_cannot_exceed_limit(self):
        with self.assertRaises(ValueError):list(response(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n100\r\nx').chunks())
    def test_endpoint_and_identity_validation(self):
        good='https://digirdu-lights.firebaseapp.com/device-api/v1'
        for endpoint in ('http://digirdu-lights.firebaseapp.com/device-api/v1',good+'?token=x',
                         'https://evil.example/device-api/v1','https://user@x.firebaseapp.com/device-api/v1'):
            with self.assertRaises(ValueError):DeviceHTTP(None,'abc123','a'*64,endpoint)
        client=DeviceHTTP(None,'abc123','a'*64,good)
        for route in ('../settings.toml','artifacts/'+'a'*64+'/../boot.py','https://evil.example'):
            with self.assertRaises(ValueError):client.request(route,lambda:None,lambda r:None)
