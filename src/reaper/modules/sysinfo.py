from __future__ import annotations

from reaper.modules.blueprint import ReaperModule


class SysInfoModule(ReaperModule):
    name        = "sysinfo"
    description = "Gather basic system information from the target."
    category    = "Enumeration"
    platform    = ["linux"]

    def run(self) -> None:
        self.notify("info", "Gathering system info…")

        checks = {
            "hostname":  "hostname",
            "whoami":    "whoami",
            "id":        "id",
            "os":        "uname -a 2>/dev/null || cat /etc/os-release 2>/dev/null | head -3",
            "kernel":    "uname -r",
            "uptime":    "uptime -p 2>/dev/null || uptime",
            "env":       "env 2>/dev/null | grep -E '(HOME|USER|SHELL|PATH)' | head -10",
            "sudo":      "sudo -l 2>/dev/null | head -15",
            "crontabs":  "crontab -l 2>/dev/null; ls /etc/cron* 2>/dev/null | head -5",
            "network":   "ip addr show 2>/dev/null || ifconfig 2>/dev/null | head -30",
            "listeners": "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null | head -20",
            "processes": "ps aux --no-headers 2>/dev/null | head -20",
        }

        data = {}
        for label, cmd in checks.items():
            try:
                with self.spinner(f"  {label}…"):
                    result = self.exec(cmd, timeout=10.0)
                output = result.stdout.strip()
                if output:
                    data[label] = output[:120] + ("…" if len(output) > 120 else "")
                else:
                    data[label] = self.ui._gr("(empty)")
            except Exception as exc:
                data[label] = self.ui._r(f"error: {exc}")

        self.box("System Info", data)
