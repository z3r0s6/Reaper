from __future__ import annotations

import os
import sys
import termios
import threading
import tty
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, TextIO
import socket

from reaper.utils.ui import _gr, _p, _r, _y, _v, CRIMSON, colored_text

OsType = Literal["linux", "windows_cmd", "windows_ps"] | None


@dataclass
class Session:
    id: int
    conn: socket.socket
    addr: tuple
    connected_at: datetime = field(default_factory=datetime.now)
    alive: bool = True
    upgraded: bool = False
    os_type: OsType = field(default=None)
    encoding: str = field(default="utf-8")
    eol: str = field(default="\n")
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _log_fh: Optional[TextIO] = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    # Uptime / labels
    # ------------------------------------------------------------------ #

    def _uptime(self) -> str:
        secs = int((datetime.now() - self.connected_at).total_seconds())
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def os_label(self) -> str:
        return {
            "linux":       _y("linux"),
            "windows_cmd": colored_text("cmd",        (100, 180, 230)),
            "windows_ps":  colored_text("powershell", (100, 180, 230)),
        }.get(self.os_type or "", _gr("?"))

    def status_dot(self) -> str:
        if not self.alive:
            return _gr("○")
        return _p("◆") if self.upgraded else _r("●")

    # ------------------------------------------------------------------ #
    # I/O
    # ------------------------------------------------------------------ #

    def send(self, data: bytes) -> bool:
        try:
            with self._lock:
                self.conn.sendall(data)
            self._log_write(data, direction="out")
            return True
        except OSError:
            self.alive = False
            return False

    def _log_write(self, data: bytes, direction: str = "in") -> None:
        """Write raw bytes to the session log file if one is open."""
        if self._log_fh is None:
            return
        try:
            text = data.decode("utf-8", errors="replace")
            self._log_fh.write(text)
            self._log_fh.flush()
        except Exception:
            pass

    def open_log(self, log_dir: Path) -> None:
        """Open a log file for this session under *log_dir*."""
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            ts    = self.connected_at.strftime("%Y%m%d_%H%M%S")
            ip    = self.addr[0].replace(":", "_")
            fname = log_dir / f"session_{self.id}_{ip}_{ts}.log"
            self._log_fh = open(fname, "a", encoding="utf-8", errors="replace")
            self._log_fh.write(
                f"# Reaper session #{self.id}  {self.addr[0]}:{self.addr[1]}"
                f"  started {self.connected_at.isoformat()}\n"
            )
        except Exception:
            self._log_fh = None

    def close_log(self) -> None:
        if self._log_fh:
            try:
                self._log_fh.write(f"\n# session #{self.id} closed {datetime.now().isoformat()}\n")
                self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None

    def close(self) -> None:
        self.alive = False
        self.close_log()
        for fn in (lambda: self.conn.shutdown(socket.SHUT_RDWR), self.conn.close):
            try:
                fn()
            except OSError:
                pass


# ------------------------------------------------------------------ #
# Raw terminal context manager
# ------------------------------------------------------------------ #

class RawTerminal:
    def __init__(self):
        self._old = None
        self._fd  = sys.stdin.fileno()

    def __enter__(self):
        self._old = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)
        return self

    def __exit__(self, *_):
        if self._old:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
