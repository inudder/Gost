from __future__ import annotations

import ipaddress
import re


IP_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4})"
)


def is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def normalize_bind_host(host: str | None) -> str:
    if not host or host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


def parse_host_port(address: str | None) -> tuple[str, int] | None:
    if not address:
        return None

    value = address.strip()
    if not value:
        return None

    if value.startswith(":"):
        host = "127.0.0.1"
        port_text = value[1:]
    elif value.startswith("[") and "]:" in value:
        host, port_text = value[1:].split("]:", maxsplit=1)
    else:
        if value.count(":") == 1:
            host, port_text = value.rsplit(":", maxsplit=1)
        elif value.count(":") > 1:
            return None
        else:
            return None

    try:
        port = int(port_text)
    except ValueError:
        return None

    if not 1 <= port <= 65535:
        return None

    return normalize_bind_host(host), port


def extract_ip(value: str | None) -> str | None:
    if not value:
        return None

    if is_ip_address(value.strip()):
        return value.strip()

    match = IP_PATTERN.search(value)
    if not match:
        return None
    candidate = match.group("ip")
    return candidate if is_ip_address(candidate) else None
