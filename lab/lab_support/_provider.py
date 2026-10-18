"""Fixed OpenRouter transport and persistent accounting."""

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

MODEL = "z-ai/glm-5.3-flash"
API_BASE = "https://openrouter.ai/api/v1"
BUDGET_USD = 1.0
SEARCH_LIMIT = 20
MAX_TOKENS = 4096
MAX_REQUEST_BYTES = 160_000


class RunError(RuntimeError):
    """A safe message that the UI can display."""


class RejectedRequest(RunError):
    """A request rejected before inference (no generation to account for)."""


def load_config(root: Path) -> tuple[str, str]:
    """Read only two configuration variables; never execute/interpolate .env text."""
    values = {}
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if separator and name.strip() in {"OPENROUTER_API_KEY", "OPENROUTER_MODEL"}:
                values[name.strip()] = value.strip().strip("\"'")
    key = os.environ.get("OPENROUTER_API_KEY", values.get("OPENROUTER_API_KEY", "")).strip()
    model = os.environ.get("OPENROUTER_MODEL", values.get("OPENROUTER_MODEL", MODEL)).strip()
    if not key or key.startswith("your-"):
        raise RunError("Set OPENROUTER_API_KEY in lab/.env or the environment; see .env.example.")
    if "\n" in key or "\r" in key:
        raise RunError("The API key contains invalid characters.")
    if model != MODEL:
        raise RunError(f"This lab uses {MODEL}. Check OPENROUTER_MODEL.")
    return key, model


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RunError("Unexpected API redirect; no credentials were forwarded.")


class OpenRouter:
    def __init__(self, key: str):
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, endpoint: str, payload: dict | None = None) -> dict:
        if endpoint not in {"/chat/completions", "/key"}:
            raise RunError("Unsupported API endpoint.")
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(API_BASE + endpoint, data=data, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
            "X-OpenRouter-Title": "HAID Part 1 Product Analysis Lab",
        })
        try:
            with self.opener.open(request, timeout=180) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RunError("API response exceeded the size limit.")
                result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            hints = {401: "Check your API key.", 402: "The API key/account budget is exhausted.",
                     429: "Rate limit reached. Wait before trying again.",
                     400: "Check model/server-tool support and the request configuration.",
                     404: "The selected model or endpoint is unavailable.",
                     503: "No compatible provider is currently available."}
            detail = ""
            try:
                error = json.loads(exc.read(8192)).get("error", {})
                message = error.get("message", "")
                if isinstance(message, str):
                    message = message.replace(self.key, "[REDACTED]")
                    message = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", message)
                    message = "".join(c for c in message if ord(c) >= 32 and ord(c) != 127)
                    detail = " " + " ".join(message.split())[:400]
            except (ValueError, TypeError, AttributeError):
                pass
            error_type = RejectedRequest if exc.code in {400, 401, 402, 403, 404, 422, 429} else RunError
            raise error_type(f"OpenRouter HTTP {exc.code}. " + hints.get(exc.code, "Provider request failed.") + detail) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RunError("Network request failed or timed out. No automatic retry was made.") from None
        except (ValueError, UnicodeError):
            raise RunError("OpenRouter returned invalid JSON.") from None
        if not isinstance(result, dict) or result.get("error"):
            raise RunError("OpenRouter returned an API error. Check the dashboard; no automatic retry was made.")
        return result

    def complete(self, payload: dict) -> dict:
        return self.request("/chat/completions", payload)

    def check_key(self) -> dict:
        data = self.request("/key").get("data")
        if not isinstance(data, dict):
            raise RunError("Could not verify the API key's spending limit.")
        remaining = data.get("limit_remaining")
        if isinstance(remaining, (int, float)) and remaining <= 0:
            raise RunError("This OpenRouter key has no remaining credit allowance.")
        return {"limit": data.get("limit"), "remaining": remaining, "usage": data.get("usage")}


def search_tool(remaining: int) -> dict:
    allowance = min(2, remaining)
    return {"type": "openrouter:web_search", "parameters": {
        "engine": "parallel", "mode": "fast", "max_results": 3,
        "max_characters": 1500, "max_uses": allowance, "max_total_results": 3 * allowance,
    }}


class Ledger:
    """Reserve searches before requests; never silently treat unknown cost as zero.

    API key limits remain the account-side control. This local file cannot guard
    against students deliberately editing the program or its counters.
    """

    def __init__(self, directory: Path, key: str = "offline-demo"):
        self.directory = directory
        self.path = directory / "usage.json"
        self.identity = hashlib.sha256(key.encode()).hexdigest()[:16]
        self.search_limit = SEARCH_LIMIT
        self.data = {"key_id": self.identity, "cost": 0.0, "searches": 0,
                     "reserved_searches": 0, "prompt_tokens": 0, "completion_tokens": 0,
                     "requests": 0, "pending": False, "unknown_cost": False, "unknown_tokens": False}
        if directory.is_symlink() or self.path.is_symlink():
            raise RunError("Accounting paths must not be symbolic links.")
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                loaded.setdefault("unknown_tokens", False)
                for name in self.data:
                    if name not in loaded:
                        raise ValueError()
                if loaded["key_id"] != self.identity:
                    raise RunError("This workspace has usage for a different key. Use a separate lab copy.")
                for name in ("cost", "searches", "reserved_searches", "prompt_tokens", "completion_tokens", "requests"):
                    value = loaded[name]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                        raise ValueError()
                    if name != "cost" and not isinstance(value, int):
                        raise ValueError()
                if any(type(loaded[n]) is not bool for n in ("pending", "unknown_cost", "unknown_tokens")):
                    raise ValueError()
                self.data = loaded
            except (ValueError, TypeError, OSError):
                raise RunError("Invalid accounting file; ask the instructor to reconcile usage before continuing.") from None

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.directory / "usage.tmp"
        if temp.is_symlink():
            raise RunError("Invalid accounting temporary path.")
        temp.write_text(json.dumps(self.data, indent=2) + "\n")
        temp.replace(self.path)

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "session.lock"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RunError("Another lab session holds the lock. Close it first; see README for stale locks.") from None
        try:
            os.write(descriptor, str(os.getpid()).encode())
            yield
        finally:
            os.close(descriptor)
            path.unlink(missing_ok=True)

    @property
    def remaining_searches(self):
        return max(0, self.search_limit - self.data["searches"] - self.data["reserved_searches"])

    def reserve(self, payload: dict, searches: int):
        if self.data["pending"] or self.data["unknown_cost"]:
            raise RunError("Previous request cost is unknown. Paid calls are paused; reconcile usage with the instructor (README).")
        size = len(json.dumps(payload).encode())
        if size > MAX_REQUEST_BYTES:
            raise RunError("Conversation reached the context-size limit. Restart and explicitly read the saved plan/report.")
        # Admission estimate at planning rates, NOT a price ceiling or billing
        # guarantee. Actual provider rates can differ; the key limit controls spending.
        reserve = (size * 0.15 / 1_000_000 + MAX_TOKENS * 0.50 / 1_000_000) * (searches + 1) + searches * .001
        if self.data["cost"] + reserve > BUDGET_USD:
            raise RunError("Insufficient remaining lab budget for another bounded request. Saved files remain available.")
        if searches > self.remaining_searches:
            raise RunError("Search allowance exceeded.")
        self.data["reserved_searches"] += searches
        self.data["pending"] = True
        self.data["requests"] += 1
        self.save()

    def record(self, response: dict, reserved: int):
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        # Billing metadata only: no prompt, API key, source text, or reasoning.
        record = {"id": response.get("id"), "usage": usage}
        with (self.directory / "requests.jsonl").open("a") as log:
            log.write(json.dumps(record) + "\n")
        cost = usage.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
            self.data["cost"] += cost   # Already includes charged search fees: never add them twice.
        else:
            self.data["unknown_cost"] = True
        for name in ("prompt_tokens", "completion_tokens"):
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.data[name] += value
            else:
                self.data["unknown_tokens"] = True
        server_use = usage.get("server_tool_use") or {}
        searches = server_use.get("web_search_requests") if isinstance(server_use, dict) else None
        if isinstance(searches, int) and not isinstance(searches, bool) and searches >= 0:
            self.data["reserved_searches"] -= reserved
            self.data["searches"] += searches
            if searches > reserved:
                self.data["unknown_cost"] = True  # Provider did not respect our search cap; stop.
        # Missing search usage keeps the reserved allowance consumed, conservatively.
        self.data["pending"] = False
        self.save()

    def release_rejected(self, reserved: int):
        self.data["reserved_searches"] -= reserved
        self.data["pending"] = False
        self.save()

    def summary(self) -> str:
        d = self.data
        cost = f"${d['cost']:.4f}" + (" + unknown (calls paused)" if d["unknown_cost"] or d["pending"] else "")
        searches = f"{d['searches']} confirmed + {d['reserved_searches']} reserved/unknown"
        tokens = f"{d['prompt_tokens']} in, {d['completion_tokens']} out" + (" + unknown" if d["unknown_tokens"] else "")
        return f"Usage: {cost} / $1.00; searches {searches} / {self.search_limit}; tokens {tokens}."
