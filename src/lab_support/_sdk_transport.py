"""SDK HTTP transport: enforce admission limits and retain OpenRouter raw billing.

The SDK still builds requests, converts responses, executes tools and runs turns.
This adapter delegates only HTTP to the bounded transport shared with web search.
"""
import json

import httpx2

from ._provider import API_BASE, RejectedRequest, RunError


class BudgetTransport(httpx2.AsyncBaseTransport):
    def __init__(self, client, ledger, emit=print):
        self.client = client
        self.ledger = ledger
        self.emit = emit
        self.error = None

    async def handle_async_request(self, request):
        try:
            if str(request.url) != API_BASE + "/chat/completions" or request.method != "POST":
                raise RunError("Unsupported SDK API endpoint.")
            payload = json.loads(request.content)
            self.ledger.reserve(payload, 0)
            self.emit("Working…")
            try:
                # Sequential terminal lab: one bounded HTTP request, no retries.
                response = self.client.complete(payload)
            except RejectedRequest:
                self.ledger.release_rejected(0)
                raise
            # Record BEFORE SDK normalization can discard provider billing fields.
            self.ledger.record(response, 0)
            self._check_completion(response)
            usage = response.get("usage")
            if not isinstance(usage, dict) or any(
                type(usage.get(field)) is not int or usage[field] < 0
                for field in ("prompt_tokens", "completion_tokens", "total_tokens")
            ):
                # SDK expects well-formed standard token fields. The original usage
                # and unknown flags remain in our ledger; do not invent billing data.
                response = {**response, "usage": None}
            return httpx2.Response(200, json=response, request=request)
        except RunError as exc:
            self.error = exc
            raise

    @staticmethod
    def _check_completion(response):
        """Reject truncated/malformed batches before any SDK tool callback runs."""
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RunError("Provider returned no valid completion.")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise RunError("Provider returned an invalid assistant message.")
        if choice.get("finish_reason") == "length":
            raise RunError("Model output was truncated; no tools in this response were executed. Try a smaller task.")
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list) or len(calls) > 8:
            raise RunError("Unexpected tool-call batch size.")
        ids = set()
        for call in calls:
            if not isinstance(call, dict):
                raise RunError("Malformed tool call; no calls were executed.")
            identifier = call.get("id")
            function = call.get("function")
            if (not isinstance(identifier, str) or not identifier or identifier in ids or
                    not isinstance(function, dict) or
                    not isinstance(function.get("name"), str) or
                    not isinstance(function.get("arguments"), str)):
                raise RunError("Malformed tool call; no calls were executed.")
            ids.add(identifier)
