#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from reaper.listener import BindConnector, Listener
from reaper.server import FileServer
from reaper.utils.ui import display_art, notify, print_payloads, _b, _gr, _p


class _ArtHelpAction(argparse.Action):
    def __init__(self, option_strings, dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest,
                         default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        display_art(small=True)
        parser.print_help()
        parser.exit()


def _parse_ports(s: str) -> list[int]:
    ports = []
    for part in s.split(","):
        part = part.strip()
        if part:
            try:
                ports.append(int(part))
            except ValueError:
                raise argparse.ArgumentTypeError(f"Invalid port: {part!r}")
    return ports


def main():
    parser = argparse.ArgumentParser(
        prog="reaper",
        description="Reaper – multi-session reverse/bind shell handler",
        add_help=False,
    )
    parser.add_argument("-h", "--help",      action=_ArtHelpAction,
                        help="Show help and exit.")

    # Listener
    listener_grp = parser.add_argument_group("Listener")
    listener_grp.add_argument(
        "-i", "--interface", dest="host", default="0.0.0.0", metavar="HOST",
        help="Bind address / interface IP.  (default: 0.0.0.0)",
    )
    listener_grp.add_argument(
        "-p", "--ports", dest="ports", type=_parse_ports,
        default=[4444], metavar="PORT[,PORT…]",
        help="Port(s) to listen on, comma-separated.  (default: 4444)",
    )

    # Bind shell
    bind_grp = parser.add_argument_group("Bind shell")
    bind_grp.add_argument(
        "-c", "--connect", dest="connect", default=None, metavar="HOST",
        help="Connect to a bind shell at HOST (use -p for port).",
    )

    # File server
    serve_grp = parser.add_argument_group("HTTP file server")
    serve_grp.add_argument(
        "-s", "--serve", dest="serve", default=None, metavar="PATH",
        help="Serve a file or directory over HTTP and exit (default port 8000).",
    )
    serve_grp.add_argument(
        "--serve-port", dest="serve_port", type=int, default=8000,
        help="Port for the HTTP file server.  (default: 8000)",
    )

    # Hints
    hints_grp = parser.add_argument_group("Hints")
    hints_grp.add_argument(
        "-a", "--payloads", dest="payloads", nargs="?", const="__all__",
        metavar="IFACE",
        help="Print reverse-shell payloads (optionally for a specific interface) and exit.",
    )

    # Logging
    log_grp = parser.add_argument_group("Session logging")
    log_grp.add_argument(
        "-L", "--no-log", dest="no_log", action="store_true",
        help="Disable session log files.",
    )
    log_grp.add_argument(
        "--log-dir", dest="log_dir", default=None, metavar="DIR",
        help="Directory for session logs.  (default: ~/.reaper/logs)",
    )

    # Misc
    misc_grp = parser.add_argument_group("Misc")
    misc_grp.add_argument(
        "-v", "--version", action="version", version="reaper 0.1.0",
    )

    args = parser.parse_args()

    # --- Serve-only mode ---
    if args.serve is not None:
        p = Path(args.serve).resolve()
        if not p.exists():
            notify("error", f"Path not found: {p}")
            sys.exit(1)
        srv = FileServer(p, port=args.serve_port)
        srv.start()
        notify("success", f"Serving {p}  on port {_b(str(args.serve_port))}")
        notify("status",  _gr("Ctrl+C to stop."))
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass
        srv.stop()
        return

    # --- Payload-only mode ---
    if args.payloads is not None:
        iface = None if args.payloads == "__all__" else args.payloads
        print_payloads(iface, args.ports[0])
        sys.exit(0)

    # --- Bind-shell mode ---
    if args.connect is not None:
        listener = Listener(
            host         = args.host,
            ports        = args.ports,
            log_sessions = not args.no_log,
            log_dir      = Path(args.log_dir) if args.log_dir else None,
        )
        signal.signal(
            signal.SIGINT,
            lambda *_: (print(), notify("warning", f"Use {_b('exit')} to quit cleanly."))
        )
        try:
            bc = BindConnector(host=args.connect, port=args.ports[0], listener=listener)
            bc.connect()
            listener.start()
        except (PermissionError, OSError) as exc:
            notify("error", f"Cannot start: {exc}")
            sys.exit(1)
        return

    # --- Reverse-shell listener mode (default) ---
    listener = Listener(
        host         = args.host,
        ports        = args.ports,
        log_sessions = not args.no_log,
        log_dir      = Path(args.log_dir) if args.log_dir else None,
    )

    signal.signal(
        signal.SIGINT,
        lambda *_: (print(), notify("warning", f"Use {_b('exit')} to quit cleanly."))
    )

    try:
        listener.start()
    except PermissionError:
        notify("error", f"Permission denied on port(s) {args.ports}.")
        sys.exit(1)
    except OSError as exc:
        notify("error", f"Cannot start listener: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
