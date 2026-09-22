"""A WebSocket client, because the browser speaks one and the standard library does not.

Chrome's DevTools Protocol is JSON over a WebSocket, and Python ships an HTTP client but no WebSocket
client — so this is the smallest thing that can carry the protocol and nothing more: the opening handshake,
the frame format, and the four opcodes that matter (text, binary, ping, close).

What it deliberately does not do: no extensions, no permessage-deflate, no subprotocol negotiation, no
fragmenting on send. It *does* reassemble fragments on receive, because Chrome does not promise to send a
base64 screenshot in one frame, and it answers pings, because a server is entitled to close a connection
whose client ignores them.

Every frame this sends is masked. That is not a preference: RFC 6455 requires a client to mask and requires
a server to close the connection when it does not.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
from typing import Optional

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC 6455's handshake constant, not a secret
_CONTINUATION, _TEXT, _BINARY, _CLOSE, _PING, _PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
_MAX_HEADER_BYTES = 64 * 1024  # a handshake response larger than this is not one


class WebSocketError(RuntimeError):
    """The connection could not be opened, or spoke something other than the protocol."""


class WebSocketClosed(WebSocketError):
    """The other end closed. Reading again will not help."""


class WebSocket:
    """One connection, opened with `ws://host:port/path` and used one message at a time."""

    def __init__(self, url: str, *, timeout_s: float = 30.0) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self._buffer = bytearray()  # bytes read past the handshake, which belong to the first frame
        self._closed = False
        host, port, path = _split(url)
        self._sock = socket.create_connection((host, port), timeout=timeout_s)
        self._sock.settimeout(timeout_s)
        try:
            self._handshake(host, port, path)
        except Exception:
            self._sock.close()
            raise

    # ── opening ──

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self._sock.sendall(request.encode("ascii"))
        raw = b""
        while b"\r\n\r\n" not in raw:
            if len(raw) > _MAX_HEADER_BYTES:
                raise WebSocketError(f"{self.url} sent an implausible handshake response")
            chunk = self._sock.recv(4096)
            if not chunk:
                raise WebSocketError(f"{self.url} closed during the handshake")
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        self._buffer.extend(rest)  # the first frame may already be waiting in here
        lines = head.decode("latin-1").split("\r\n")
        if " 101" not in lines[0]:
            raise WebSocketError(f"{self.url} refused the upgrade: {lines[0]!r}")
        headers = {k.strip().lower(): v.strip() for k, _, v in
                   (line.partition(":") for line in lines[1:])}
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expected:
            raise WebSocketError(f"{self.url} did not prove it understood the handshake")

    # ── reading and writing ──

    def send_text(self, text: str) -> None:
        self._send_frame(_TEXT, text.encode("utf-8"))

    def recv_text(self) -> str:
        """The next complete text message. Raises `WebSocketClosed` when the other end goes away."""
        while True:
            opcode, payload = self._recv_message()
            if opcode == _TEXT:
                return payload.decode("utf-8", errors="replace")
            # A binary frame is not part of this protocol; ignoring it is better than guessing at it.

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._send_frame(_CLOSE, struct.pack("!H", 1000))  # 1000 = normal closure
        except (OSError, WebSocketError):
            pass  # the other end may already be gone; closing the socket is the point, not the goodbye
        finally:
            self._closed = True
            try:
                self._sock.close()
            except OSError:
                pass

    def __enter__(self) -> "WebSocket":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── the frame format ──

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self._closed:
            raise WebSocketClosed("this connection is closed")
        header = bytearray([0x80 | opcode])  # FIN, since nothing here fragments on send
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _recv_exact(self, count: int) -> bytes:
        out = bytearray()
        while len(out) < count:
            if self._buffer:
                take = min(count - len(out), len(self._buffer))
                out += self._buffer[:take]
                del self._buffer[:take]
                continue
            try:
                chunk = self._sock.recv(min(65536, count - len(out)))
            except socket.timeout as exc:
                raise WebSocketError(f"timed out after {self.timeout_s}s waiting on {self.url}") from exc
            if not chunk:
                self._closed = True
                raise WebSocketClosed(f"{self.url} closed the connection")
            out += chunk
        return bytes(out)

    def _recv_message(self) -> tuple[int, bytes]:
        """The next data message, reassembled. Control frames are handled here and never returned."""
        fragments = bytearray()
        started: Optional[int] = None
        while True:
            first, second = self._recv_exact(2)
            final, opcode = bool(first & 0x80), first & 0x0F
            masked, length = bool(second & 0x80), second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if mask:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
            if opcode == _PING:
                self._send_frame(_PONG, payload)
                continue
            if opcode == _PONG:
                continue
            if opcode == _CLOSE:
                self._closed = True
                raise WebSocketClosed(f"{self.url} sent a close frame")
            if opcode == _CONTINUATION:
                if started is None:
                    raise WebSocketError(f"{self.url} sent a continuation with nothing to continue")
                fragments += payload
            elif opcode in (_TEXT, _BINARY):
                started, fragments = opcode, bytearray(payload)
            else:
                continue  # an opcode from the future; the protocol says to ignore what you do not know
            if final and started is not None:
                return started, bytes(fragments)


def _split(url: str) -> tuple[str, int, str]:
    if not url.startswith("ws://"):
        raise WebSocketError(f"only ws:// URLs are supported, not {url!r}")
    rest = url[len("ws://"):]
    authority, _, path = rest.partition("/")
    host, _, port = authority.partition(":")
    if not host:
        raise WebSocketError(f"no host in {url!r}")
    try:
        return host, int(port) if port else 80, "/" + path
    except ValueError as exc:
        raise WebSocketError(f"bad port in {url!r}") from exc


__all__ = ["WebSocket", "WebSocketClosed", "WebSocketError"]
