"""
Request throttling + hardening headers (added 2026-09-21, security review).

What this does
  * Admin password guessing: after ADMIN_MAX_FAILS wrong X-Admin-Password
    attempts from one IP inside ADMIN_FAIL_WINDOW_S, that IP is locked out
    for ADMIN_LOCK_S (even a correct password is refused during the lock).
  * Public-form abuse: per-IP caps on the endpoints anyone on the internet
    can POST to (lead submit, vendor onboarding, coupon checks, ...).
  * Oversized request bodies are refused before they are read.
  * Adds X-Content-Type-Options / Referrer-Policy (and no-store on admin).

Limits: state is kept in memory, so it is per server process and resets
when Railway restarts the service. That is fine for one instance; if the API
is ever scaled to several instances, move this to Redis.

The client IP is the LAST X-Forwarded-For entry (the one Railway's own proxy
appends), so a caller cannot dodge a limit by sending a fake header.
"""
import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

ADMIN_MAX_FAILS = 10
ADMIN_FAIL_WINDOW_S = 15 * 60
ADMIN_LOCK_S = 15 * 60

MAX_BODY_BYTES = 8 * 1024 * 1024   # vendor upload cap is 5MB; JSON bodies are tiny

# (method, path, path_is_prefix, max_requests, window_seconds)
PUBLIC_LIMITS = [
    ("POST", "/api/vendor-onboarding/submit", False, 20, 3600),
    ("POST", "/api/leads/submit", False, 40, 3600),
    ("POST", "/api/leads/finalize-notify", False, 40, 3600),
    ("POST", "/api/leads/abandoned-cart", False, 40, 3600),
    ("POST", "/api/leads/validate-coupon", False, 30, 600),
    ("POST", "/api/leads/redeem-service", False, 20, 600),
    ("GET", "/api/config/coupons/validate/", True, 30, 600),
    ("POST", "/api/order/start", False, 30, 3600),
]

_fails = defaultdict(deque)   # ip -> times of wrong admin passwords
_locked_until = {}            # ip -> epoch seconds
_hits = defaultdict(deque)    # (rule index, ip) -> request times
_calls = 0


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _prune(dq: deque, now: float, window: float) -> None:
    while dq and now - dq[0] > window:
        dq.popleft()


def _sweep(now: float) -> None:
    """Drop stale keys now and then so the dicts cannot grow without bound."""
    for ip in [k for k, v in _locked_until.items() if v <= now]:
        _locked_until.pop(ip, None)
    for k in [k for k, dq in _fails.items() if not dq or now - dq[-1] > ADMIN_FAIL_WINDOW_S]:
        _fails.pop(k, None)
    for k in [k for k, dq in _hits.items() if not dq or now - dq[-1] > 3600]:
        _hits.pop(k, None)


async def security_middleware(request: Request, call_next):
    global _calls
    if request.method == "OPTIONS":            # CORS preflight — never throttle
        return await call_next(request)

    now = time.time()
    path = request.url.path
    ip = client_ip(request)

    _calls += 1
    if _calls % 500 == 0:
        _sweep(now)

    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > MAX_BODY_BYTES:
        return JSONResponse({"detail": "That upload is too large."}, status_code=413)

    for i, (method, rule_path, is_prefix, max_req, window) in enumerate(PUBLIC_LIMITS):
        if request.method == method and (path.startswith(rule_path) if is_prefix else path == rule_path):
            dq = _hits[(i, ip)]
            _prune(dq, now, window)
            if len(dq) >= max_req:
                retry = int(window - (now - dq[0])) + 1
                logger.warning("Rate limit hit: %s %s from %s", method, path, ip)
                return JSONResponse(
                    {"detail": "Too many requests. Please try again in a few minutes."},
                    status_code=429, headers={"Retry-After": str(retry)},
                )
            dq.append(now)
            break

    has_pw = "x-admin-password" in request.headers
    if has_pw:
        until = _locked_until.get(ip, 0)
        if until > now:
            return JSONResponse(
                {"detail": f"Too many incorrect password attempts. Try again in {int((until - now) // 60) + 1} minute(s)."},
                status_code=429, headers={"Retry-After": str(int(until - now) + 1)},
            )

    response = await call_next(request)

    if has_pw:
        if response.status_code == 401:
            dq = _fails[ip]
            _prune(dq, now, ADMIN_FAIL_WINDOW_S)
            dq.append(now)
            if len(dq) >= ADMIN_MAX_FAILS:
                _locked_until[ip] = now + ADMIN_LOCK_S
                dq.clear()
                logger.warning("Admin login locked for %s after %d wrong passwords", ip, ADMIN_MAX_FAILS)
        elif response.status_code < 400:
            _fails.pop(ip, None)

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if path.startswith("/api/admin"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response
