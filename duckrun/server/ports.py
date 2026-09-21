"""Free-port allocation for backend child servers."""
from __future__ import annotations

import socket


def find_free_port(host: str = "127.0.0.1") -> int:
    """Bind port 0, read back the assigned port, release it. Small race, fine in practice."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])
