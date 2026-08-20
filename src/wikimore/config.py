import importlib.metadata
import logging
import os
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def env_flag(name: str, fallback: str | None = None) -> bool:
    """Return True if the environment variable ``name`` (or ``fallback``) is set
    to a truthy value (anything other than empty string, ``0``, ``false``,
    ``no``, or ``off``)."""
    value = os.environ.get(name)
    if value is None and fallback:
        value = os.environ.get(fallback)
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


DEBUG_ENABLED = env_flag("WIKIMORE_DEBUG", "DEBUG")
LOG_LEVEL = logging.DEBUG if DEBUG_ENABLED else logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def get_version() -> str:
    """Return the installed package version, or ``"dev"`` if not installed."""
    try:
        return importlib.metadata.version("wikimore")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def get_instance_hostname() -> str:
    """Return the hostname of this instance for use in the User-Agent header.

    Checks ``WIKIMORE_INSTANCE_HOSTNAME`` first, then ``X-Forwarded-Host``,
    then ``request.host``.  Falls back to ``"unknown"`` outside a request context.
    """
    # Import here to avoid a hard Flask dependency at module load time
    from flask import request  # noqa: PLC0415

    if env_host := os.environ.get("WIKIMORE_INSTANCE_HOSTNAME"):
        return env_host
    try:
        if "X-Forwarded-Host" in request.headers:
            return request.headers["X-Forwarded-Host"]
        return request.host
    except RuntimeError:
        return "unknown"


def get_admin_email() -> str | None:
    """Return the admin email from ``WIKIMORE_ADMIN_EMAIL``, or ``None`` if unset."""
    return os.environ.get("WIKIMORE_ADMIN_EMAIL")


def urlopen(url, headers={}, **kwargs):
    """Wrapper around ``urllib.request.urlopen`` that injects a Wikimore User-Agent.

    Accepts the same arguments as the stdlib function; ``timeout`` defaults to 30 s
    if not supplied.
    """
    user_agent = (
        f"Wikimore/{get_version()} "
        f"(instance: {get_instance_hostname()}; "
        f"admin: {get_admin_email() or 'not set'}; "
        f"source: https://git.private.coffee/privatecoffee/wikimore)"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, **headers},
    )
    kwargs.setdefault("timeout", 30)
    return urllib.request.urlopen(req, **kwargs)


def get_retry_after(exc: urllib.error.HTTPError) -> int | None:
    """Parse the ``Retry-After`` header from an HTTP 429 response.

    Returns the number of seconds to wait, or ``None`` if the header is absent
    or unparseable.
    """
    try:
        value = exc.headers.get("Retry-After")
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            pass
        delta = parsedate_to_datetime(value) - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))
    except Exception:
        return None
