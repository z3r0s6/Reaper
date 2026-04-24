from __future__ import annotations

import re
import shutil
import sys
import threading
import time
from random import choice

_ANSI = re.compile(r"\033\[[^m]*m")

# ── Dark palette ──────────────────────────────────────────────────────────────
BONE    = (220, 215, 200)   # parchment – primary text
BLOOD   = (210,  55,  50)   # red – errors
CRIMSON = (220,  65,  55)   # crimson – accents / new session
SCARLET = (255,  95,  75)   # bright scarlet – IDs / highlights
ASH     = (150, 148, 160)   # medium ash – secondary / borders
GHOST   = (185, 180, 195)   # ghostly – dim labels
VOID    = (165, 125, 225)   # bright violet – section headers
GOLD    = (210, 175,  75)   # gold – success / OS tags
EMBER   = (225, 130,  55)   # ember orange – warnings
DIM_C   = (90,  88,  100)   # subtle – decorative elements

RST  = "\033[0m"
DIM  = "\033[2m"
BOLD = "\033[1m"

# ── Shorthand color helpers ───────────────────────────────────────────────────
def _b(t):   return f"{BOLD}{t}{RST}"
def _d(t):   return f"{DIM}{t}{RST}"
def _r(t):   return colored_text(t, BLOOD)
def _c(t):   return colored_text(t, BONE)
def _p(t):   return colored_text(t, SCARLET)
def _y(t):   return colored_text(t, GOLD)
def _gr(t):  return colored_text(t, ASH)
def _gh(t):  return colored_text(t, GHOST)
def _v(t):   return colored_text(t, VOID)
def _e(t):   return colored_text(t, EMBER)

# ── MOTD ──────────────────────────────────────────────────────────────────────
MOTD = [
    "They never see the Reaper coming.",
    "Your shells belong to me now.",
    "Death is just a POST request away.",
    "No firewall survives the harvest.",
    "Every port a door. Every door an opportunity.",
    "root@target is my favorite destination.",
    "Come in. Stay a while. Forever.",
    "The harvest begins.",
    "404: Escape not found.",
    "Patience. The shell will come.",
    "Another soul acquired.",
    "The scythe swings both ways.",
]

# ── Core color functions ──────────────────────────────────────────────────────
def cs(rgb: tuple) -> str:
    """Raw ANSI color escape for an RGB tuple."""
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

# keep old name for backward compat
color_signal = cs


def colored_text(text, fg, bg=None) -> str:
    if not sys.stdout.isatty():
        return str(text)
    r, g, b = fg
    if bg:
        br, bg_, bb = bg
        return f"\033[38;2;{r};{g};{b}m\033[48;2;{br};{bg_};{bb}m{text}{RST}"
    return f"\033[38;2;{r};{g};{b}m{text}{RST}"


def gradient_text(text: str, start=SCARLET, end=BONE) -> str:
    if not sys.stdout.isatty():
        return text
    out = ""
    n   = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(start[0] + t * (end[0] - start[0]))
        g = int(start[1] + t * (end[1] - start[1]))
        b = int(start[2] + t * (end[2] - start[2]))
        out += f"\033[38;2;{r};{g};{b}m{ch}"
    return out + RST


def _strip(text: str) -> str:
    return _ANSI.sub("", text)


def _vlen(s: str) -> int:
    return len(_ANSI.sub("", s))

# ── ASCII art ─────────────────────────────────────────────────────────────────

_SKULL = (
    f"{cs(ASH)}    ⠀⠀⢀⣠⡴⠾⠿⠷⣦⣄⠀⠀⠀{RST}",
    f"{cs(ASH)}    ⠀⣴⡿⠋⠀⠀⠀⠀⠀⠙⢿⣦⠀{RST}",
    f"{cs(ASH)}    ⣼⡟⠀{cs(GHOST)}⢀⣾⣦⡀⢀⣾⣦⡀{cs(ASH)}⠈⢿⣧{RST}",
    f"{cs(ASH)}    ⣿⡇⠀{cs(BONE)}⢸⣿⣿⡇⢸⣿⣿⡇{cs(ASH)}⠀⢸⣿{RST}",
    f"{cs(ASH)}    ⣿⣷⠀{cs(GHOST)}⠈⠉⠉⠁⠈⠉⠉⠁{cs(ASH)}⠀⣾⣿{RST}",
    f"{cs(ASH)}    ⠸⣿⣧⡀⠀{cs(DIM_C)}⣀⣀⣀⣀{cs(ASH)}⢀⣼⣿⠇{RST}",
    f"{cs(ASH)}    ⠀⠙⢿⣿⣦{cs(DIM_C)}⣙⣛⣛⣋{cs(ASH)}⣴⣿⡿⠋{RST}",
    f"{cs(ASH)}    ⠀⠀⠀⠉⠛⠿⣿⣿⠿⠛⠉⠀⠀{RST}",
)

_TITLE_LINES = (
    (BLOOD,   CRIMSON, "  ██████╗ ███████╗ █████╗ ██████╗ ███████╗██████╗ "),
    (BLOOD,   CRIMSON, "  ██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗"),
    (CRIMSON, SCARLET, "  ██████╔╝█████╗  ███████║██████╔╝█████╗  ██████╔╝"),
    (CRIMSON, SCARLET, "  ██╔══██╗██╔══╝  ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗"),
    (ASH,     GHOST,   "  ██║  ██║███████╗██║  ██║██║     ███████╗██║  ██║ "),
    (ASH,     GHOST,   "  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝"),
)


def _render_title_line(start: tuple, end: tuple, text: str) -> str:
    out = ""
    n   = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(start[0] + t * (end[0] - start[0]))
        g = int(start[1] + t * (end[1] - start[1]))
        b = int(start[2] + t * (end[2] - start[2]))
        out += f"\033[38;2;{r};{g};{b}m{ch}"
    return out + RST


def display_art(small: bool = False) -> None:
    cols       = shutil.get_terminal_size().columns
    skull_w    = 18   # visual width of skull block
    title_w    = 52   # visual width of title block
    total      = skull_w + 4 + title_w
    left_pad   = max((cols - total) // 2, 0)
    pad        = " " * left_pad

    # Pad skull lines to 8, title lines to 6 → render side by side
    skull_lines = list(_SKULL)
    title_lines = [_render_title_line(s, e, t) for s, e, t in _TITLE_LINES]

    # Align: skull has 8 lines, title has 6 → offset title by 1
    print()
    for i in range(max(len(skull_lines), len(title_lines) + 1)):
        sk = skull_lines[i] if i < len(skull_lines) else " " * skull_w
        tl = title_lines[i - 1] if 0 < i <= len(title_lines) else ""
        print(f"{pad}  {sk}   {tl}")

    # MOTD line
    motd_line = f"{cs(DIM_C)}{'─' * 48}{RST}  {colored_text(choice(MOTD), GHOST)}"
    print(f"\n{pad}  {_d(colored_text('☠', CRIMSON))}  {motd_line}")
    print()


# ── Notifications ─────────────────────────────────────────────────────────────
#
#  Format:  prefix  icon  msg
#  prefix = two spaces
#  icon   = bracketed symbol with color

def _icon(symbol: str, color: tuple) -> str:
    bracket = colored_text("[", DIM_C)
    end     = colored_text("]", DIM_C)
    sym     = colored_text(symbol, color)
    return f"{bracket}{sym}{end}"


_NOTIF = {
    "new":     (_icon("☠", CRIMSON),  BONE),
    "success": (_icon("✓", GOLD),     BONE),
    "error":   (_icon("✗", BLOOD),    BONE),
    "warning": (_icon("!", EMBER),    BONE),
    "info":    (_icon("·", GHOST),    BONE),
    "status":  (_icon("─", ASH),      GHOST),
}


def notify(kind: str, msg: str) -> None:
    icon, txt_color = _NOTIF.get(kind, (_icon("·", GHOST), BONE))
    text = colored_text(msg, txt_color) if sys.stdout.isatty() else msg
    # Strip any existing color from msg so we apply txt_color cleanly
    print(f"  {icon} {msg}")


# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    _FRAMES = [
        colored_text("⣾", CRIMSON),
        colored_text("⣽", CRIMSON),
        colored_text("⣻", BLOOD),
        colored_text("⢿", BLOOD),
        colored_text("⡿", CRIMSON),
        colored_text("⣟", CRIMSON),
        colored_text("⣯", BLOOD),
        colored_text("⣷", BLOOD),
    ]

    def __init__(self, msg: str = ""):
        self._msg    = msg
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        if not sys.stdout.isatty():
            print(f"  {_gh('…')} {self._msg}", flush=True)
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self):
        i = 0
        label = colored_text(self._msg, GHOST)
        while not self._stop.is_set():
            f = self._FRAMES[i % len(self._FRAMES)]
            sys.stdout.write(f"\r  {f} {label}")
            sys.stdout.flush()
            time.sleep(0.07)
            i += 1

    def __exit__(self, *_):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


# ── Boxes / tables ────────────────────────────────────────────────────────────

def print_report_box(title: str, data: dict, indent: int = 2) -> None:
    pad  = " " * indent
    rows: list[tuple[str, str]] = []
    has_groups = any(isinstance(v, dict) for v in data.values())

    if has_groups:
        for group, items in data.items():
            rows.append((colored_text(f" {group}", VOID), ""))
            if isinstance(items, dict):
                for k, v in items.items():
                    rows.append((f"  {k}", v))
            else:
                rows.append(("  " + str(items), ""))
    else:
        for k, v in data.items():
            rows.append((k, v))

    key_w = max((_vlen(r[0]) for r in rows if r[1]), default=0)
    val_w = max((_vlen(r[1]) for r in rows if r[1]), default=0)
    col_w = max(_vlen(title) + 2, key_w + val_w + 6)

    # Double-line top, single-line body
    tl = colored_text("╔", CRIMSON)
    tr = colored_text("╗", CRIMSON)
    bl = colored_text("╚", ASH)
    br = colored_text("╝", ASH)
    ml = colored_text("╠", ASH)
    mr = colored_text("╣", ASH)
    ht = colored_text("═", CRIMSON)   # top horizontal
    hb = colored_text("─", ASH)       # body horizontal
    vt = colored_text("║", CRIMSON)   # title bar vertical
    vb = colored_text("│", ASH)       # body vertical

    title_str  = f" {_b(colored_text(title, BONE))} "
    title_fill = col_w + 2 - _vlen(title_str)

    print()
    print(f"{pad}{tl}{ht * (col_w + 2)}{tr}")
    print(f"{pad}{vt}{title_str}{' ' * title_fill}{vt}")
    print(f"{pad}{ml}{hb * (col_w + 2)}{mr}")

    for key, val in rows:
        if not val:
            # group section label
            line   = f" {key}"
            spaces = col_w + 2 - _vlen(line)
            print(f"{pad}{vb}{line}{' ' * spaces}{vb}")
        else:
            sep    = colored_text("·", DIM_C)
            kpad   = " " * (key_w - _vlen(key))
            line   = f" {key}{kpad}  {sep}  {val}"
            spaces = col_w + 2 - _vlen(line)
            print(f"{pad}{vb}{line}{' ' * spaces}{vb}")

    print(f"{pad}{bl}{hb * (col_w + 2)}{br}")
    print()


# ── Separators ────────────────────────────────────────────────────────────────

def breaker() -> None:
    cols = shutil.get_terminal_size().columns
    half = (cols - 4) // 2
    line = (
        colored_text("─" * half, DIM_C)
        + colored_text(" ☠ ", CRIMSON)
        + colored_text("─" * half, DIM_C)
    )
    print(line)


def breaker_with_text(text: str) -> None:
    cols = shutil.get_terminal_size().columns
    bar  = "─" * ((cols - _vlen(text) - 2) // 2)
    print(colored_text(f"{bar} {text} {bar}", ASH))


# ── Yes/No prompt ─────────────────────────────────────────────────────────────

def yesno(prompt: str) -> bool:
    yn = colored_text("[y/N]", DIM_C)
    try:
        ans = input(f"  {_icon('?', EMBER)} {prompt} {yn} ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# ── Payload display ───────────────────────────────────────────────────────────

def _print_payload_block(iface: str, ip: str, port: int, payloads: dict[str, str]) -> None:
    cols = shutil.get_terminal_size().columns

    top_bar    = colored_text("═" * cols, CRIMSON)
    bottom_bar = colored_text("─" * cols, DIM_C)

    # Header
    skull  = colored_text("☠", CRIMSON)
    iface_ = _b(colored_text(iface, SCARLET))
    arrow  = colored_text("→", ASH)
    ip_    = colored_text(ip, BONE)
    colon  = colored_text(":", DIM_C)
    port_  = colored_text(str(port), GOLD)

    print()
    print(top_bar)
    print(f"  {skull}  {iface_}  {arrow}  {ip_}{colon}{port_}")
    print(colored_text("─" * cols, ASH))

    for i, (name, cmd) in enumerate(payloads.items(), 1):
        num   = colored_text(f"[{i:02d}]", CRIMSON)
        label = colored_text(name, VOID)
        cmd_  = colored_text(cmd, BONE)
        print(f"\n  {num} {label}")
        print(f"      {cmd_}")

    print()
    print(bottom_bar)
    print()


def print_payloads(iface: str | None, port: int) -> None:
    from reaper.utils.payloads import PayloadGenerator
    gen        = PayloadGenerator(port=port)
    interfaces = gen.get_interfaces()

    if iface:
        payloads = gen.for_interface(iface)
        if payloads is None:
            notify("error", f"Interface {_p(iface)!r} not found.")
            notify("status", colored_text(f"Available: {', '.join(interfaces) or 'none'}", GHOST))
            return
        ip = interfaces.get(iface, "?")
        _print_payload_block(iface, ip, port, payloads)
    else:
        if not interfaces:
            notify("status", colored_text("No network interfaces detected.", GHOST))
            return
        for _iface, ip in interfaces.items():
            payloads = gen.for_interface(_iface) or {}
            _print_payload_block(_iface, ip, port, payloads)
