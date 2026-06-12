"""
Stateless return-path / breadcrumb trail, carried in the URL as ?trail=.

Design (chosen for stability): the whole trail lives in the URL, so it survives
browser back/forward, refresh, multiple tabs, and link-sharing — none of which a
session-stored trail handles reliably. Each hop is {url, label}. The trail is
capped so URLs can't balloon.

Encoding: a compact, URL-safe base64 of a JSON list of [path, label] pairs.
Every path is validated as a safe internal path (no host, no scheme) before it's
ever emitted as a link or used as a redirect target — this is also the project's
single safe-redirect gate.

Public API:
    decode_trail(request)            -> list[{"url","label"}]
    append_to_trail(trail, url, lbl) -> new capped trail list
    encode_trail(trail)              -> str (for ?trail=)
    safe_internal_path(request, url) -> url or None
    back_target(request, fallback)   -> the URL "back" should go to
"""
import base64
import json

from django.utils.http import url_has_allowed_host_and_scheme

MAX_TRAIL = 5
TRAIL_PARAM = "trail"


def safe_internal_path(request, url):
    """Return url if it's a safe same-host relative path, else None.
    The single gate for any user-supplied navigation target (anti open-redirect)."""
    if not url:
        return None
    # only allow root-relative paths ("/...") to keep it strictly internal
    if not url.startswith("/") or url.startswith("//"):
        return None
    allowed = url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return url if allowed else None


def decode_trail(request):
    """Parse ?trail= into a list of {'url','label'} dicts (safe entries only)."""
    raw = request.GET.get(TRAIL_PARAM)
    if not raw:
        return []
    try:
        pad = "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(raw + pad).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return []
    out = []
    if isinstance(data, list):
        for item in data[:MAX_TRAIL]:
            if (isinstance(item, list) and len(item) == 2
                    and safe_internal_path(request, item[0])):
                out.append({"url": item[0], "label": str(item[1])[:60]})
    return out


def encode_trail(trail):
    """Encode a list of {'url','label'} (or [url,label]) into the ?trail= token."""
    pairs = []
    for h in trail[:MAX_TRAIL]:
        if isinstance(h, dict):
            pairs.append([h["url"], h["label"]])
        else:
            pairs.append([h[0], h[1]])
    raw = json.dumps(pairs, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def append_to_trail(trail, url, label):
    """Return a new trail with (url,label) appended, de-duped + capped.
    If the url already exists in the trail, truncate back to it (so navigating
    'up' to an ancestor collapses the trail rather than looping)."""
    trail = list(trail or [])
    for i, h in enumerate(trail):
        if h["url"] == url:
            return trail[:i + 1]
    trail.append({"url": url, "label": label})
    return trail[-MAX_TRAIL:]


def back_target(request, fallback):
    """Where a single 'back' should go: the last trail hop, else the fallback.
    Fallback is trusted (it's a server-provided module default)."""
    trail = decode_trail(request)
    if trail:
        return trail[-1]["url"]
    return fallback
