from __future__ import annotations

import http.server
import os
import threading
from pathlib import Path
from typing import Optional


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class FileServer:
    """Lightweight HTTP file server (serves a directory or single file)."""

    def __init__(self, path: str | Path, port: int = 8000):
        self.port    = port
        self._path   = Path(path).resolve()
        self._server: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread]       = None

    @property
    def serving_path(self) -> Path:
        return self._path

    def start(self) -> None:
        target = self._path
        if target.is_file():
            directory = str(target.parent)
        else:
            directory = str(target)

        handler = lambda *args, **kwargs: _SilentHandler(
            *args, directory=directory, **kwargs
        )
        self._server = http.server.HTTPServer(("0.0.0.0", self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None
