from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "dclid",
    "yclid",
    "referrer",
    "ref_src",
}


def normalize_url(url: str | None, source_id: str | None = None) -> str | None:
    if not url:
        return None
    value = url.strip()
    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    cleaned = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in TRACKING_PARAMS:
            continue
        cleaned.append((key, val))
    cleaned.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(cleaned, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))
