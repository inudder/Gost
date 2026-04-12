from __future__ import annotations

from enum import StrEnum


class CheckStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    TIMEOUT = "timeout"
    DNS_FAILED = "dns_failed"
    CONNECT_FAILED = "connect_failed"
    AUTH_FAILED = "auth_failed"
    HANDSHAKE_FAILED = "handshake_failed"
    EGRESS_FAILED = "egress_failed"
    UNKNOWN = "unknown"


class FailedStage(StrEnum):
    RESOLVE = "resolve"
    TCP_CONNECT = "tcp_connect"
    SOCKS5_HANDSHAKE = "socks5_handshake"
    SOCKS5_AUTH = "socks5_auth"
    HTTP_TEST = "http_test"
    EGRESS_IP = "egress_ip"


class NodeSourceType(StrEnum):
    MANUAL = "manual"
    GOST = "gost"
    GOST_SERVICE = "gost_service"
    GOST_CHAIN_NODE = "gost_chain_node"
