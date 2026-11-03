"""Client-IP resolution for rate limiting.

`X-Forwarded-For` is client-controlled, so it is only honoured when the direct peer
is a configured trusted proxy (TRUSTED_PROXIES: comma-separated IPs/CIDRs). The
right-most address that isn't itself a trusted proxy is the client. Without that
setting the socket peer (`request.client.host`) is used -- note uvicorn already
rewrites that from proxy headers for peers listed in FORWARDED_ALLOW_IPS.
"""
import ipaddress

from core.config import TRUSTED_PROXIES


def _networks(entries):
    nets = []
    for e in entries:
        try:
            nets.append(ipaddress.ip_network(e, strict=False))
        except ValueError:
            continue
    return nets


_TRUSTED = _networks(TRUSTED_PROXIES)


def _is_trusted(addr, trusted) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in n for n in trusted)


def client_ip(request, trusted=None) -> str:
    trusted = _TRUSTED if trusted is None else trusted
    peer = request.client.host if getattr(request, "client", None) else ""
    if trusted and peer and _is_trusted(peer, trusted):
        hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",")
                if h.strip()]
        for hop in reversed(hops):
            if _is_trusted(hop, trusted):
                continue
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                break     # garbage in the chain: fall back to the proxy itself
    return peer or "unknown"
