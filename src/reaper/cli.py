from __future__ import annotations

from reaper.utils.ui import (
    _b, _c, _gr, _p, _y, _r, _v, _gh,
    colored_text, CRIMSON, VOID, ASH
)


def print_help() -> None:
    rows = [
        ("",            "",                           ""),
        ("SESSION",     "",                           ""),
        ("  ls",        "list",                       "List all active sessions"),
        ("  go",        "go <id>",                    "Interact with session"),
        ("  upgrade",   "upgrade <id>",               "Upgrade shell to PTY"),
        ("  kill",      "kill <id>",                  "Terminate a session"),
        ("  log",       "log <id>",                   "Show log path for a session"),
        ("",            "",                           ""),
        ("PAYLOADS",    "",                           ""),
        ("  payloads",  "payloads <iface>",           "Print reverse-shell payloads for interface"),
        ("",            "",                           ""),
        ("MODULES",     "",                           ""),
        ("  modules",   "modules",                    "List available modules"),
        ("  run",       "run <mod> <id> [args]",      "Run module on session"),
        ("  reload",    "reload",                     "Hot-reload all modules"),
        ("",            "",                           ""),
        ("SERVER",      "",                           ""),
        ("  serve",     "serve [path] [port]",        "Start HTTP file server"),
        ("  stopserve", "stopserve",                  "Stop HTTP file server"),
        ("",            "",                           ""),
        ("MISC",        "",                           ""),
        ("  listeners", "listeners",                  "List active listeners"),
        ("  addport",   "addport <port>",             "Start listening on a new port"),
        ("  rmport",    "rmport <port>",              "Stop listening on a port"),
        ("  clear",     "clear",                      "Clear the screen"),
        ("  help",      "help",                       "Show this help"),
        ("  exit",      "exit",                       "Gracefully quit Reaper"),
        ("",            "",                           ""),
        ("SHORTCUTS",   "",                           ""),
        ("  Ctrl+Z",    "",                           "Background current session"),
        ("  Ctrl+C",    "",                           "Send SIGINT to remote (when in session)"),
        ("",            "",                           ""),
    ]

    cmd_w = max(len(r[0]) for r in rows) + 2
    syn_w = max(len(r[1]) for r in rows) + 2

    print()
    print(f"  {_b(_c('Reaper'))}{_gr(' – reverse shell handler')}")
    print()
    for cmd, syntax, desc in rows:
        if not cmd and not syntax and not desc:
            print()
            continue
        if not syntax and not desc:
            # section header
            print(f"  {colored_text(cmd, VOID)}")
            continue
        c_cmd  = _p(cmd).ljust(cmd_w + 20)   # +20 for ANSI codes
        c_syn  = _gr(syntax).ljust(syn_w + 20)
        c_desc = _c(desc)
        print(f"    {c_cmd}  {c_syn}  {c_desc}")
    print()
