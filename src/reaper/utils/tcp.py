from __future__ import annotations

import socket
import threading
from typing import Callable, Optional


def get_local_ip(remote_addr: str) -> str:
    """Return the local IP that routes toward *remote_addr*."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((remote_addr, 80))
        return s.getsockname()[0]
    finally:
        s.close()


def spawn_send_server(
    data: bytes,
    timeout: float = 30.0,
    on_progress: Optional[Callable[[int], None]] = None,
) -> tuple[int, threading.Thread, list[str]]:
    """
    One-shot TCP server that sends *data* to the first incoming connection.

    Returns (port, thread, errors).
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 0))
    srv.listen(1)
    srv.settimeout(timeout)
    port = srv.getsockname()[1]
    errors: list[str] = []

    def _run() -> None:
        try:
            conn, _ = srv.accept()
            sent = 0
            while sent < len(data):
                chunk = data[sent : sent + 65536]
                conn.sendall(chunk)
                sent += len(chunk)
                if on_progress:
                    on_progress(sent)
            conn.close()
        except Exception as exc:
            errors.append(str(exc))
        finally:
            srv.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return port, t, errors


def spawn_recv_server(timeout: float = 60.0) -> tuple[int, Callable[[], bytes]]:
    """
    One-shot TCP server that collects data from the first incoming connection.

    Returns (port, collect).
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 0))
    srv.listen(1)
    srv.settimeout(timeout)
    port = srv.getsockname()[1]

    def collect() -> bytes:
        try:
            conn, _ = srv.accept()
            chunks: list[bytes] = []
            while chunk := conn.recv(4096):
                chunks.append(chunk)
            conn.close()
            return b"".join(chunks)
        except Exception:
            return b""
        finally:
            srv.close()

    return port, collect
