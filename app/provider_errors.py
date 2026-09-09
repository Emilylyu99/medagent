"""Sanitized provider diagnostics. Never expose exception messages, bodies or credentials."""

from __future__ import annotations

import math
import re

from app.models import ProviderFailure

CODE_CATEGORIES = {
    "credit_balance_exhausted": "credits_exhausted",
    "insufficient_quota": "quota_exceeded",
    "organization_spend_limit_exceeded": "spend_limit",
    "project_spend_limit_exceeded": "spend_limit",
    "organization_usage_limit_exceeded": "usage_limit",
    "rate_limit_exceeded": "rate_limited",
    "slow_down": "rate_limited",
    "server_is_overloaded": "service_unavailable",
}
MESSAGES = {
    "credits_exhausted": (
        "The API organization has no prepaid credits remaining.",
        "Use offline mode without payment, or review API Billing before a future model run.",
    ),
    "quota_exceeded": (
        "The provider reported insufficient API quota.",
        "Check the API organization's credits and usage limits. Repeated retries will not restore quota.",
    ),
    "spend_limit": (
        "An organization or project API spending limit was reached.",
        "Review the applicable spending limit. No limits are changed automatically; offline mode remains available.",
    ),
    "usage_limit": (
        "The organization reached its provider-assigned API usage limit.",
        "Review organization usage limits or use offline mode. Do not repeatedly retry.",
    ),
    "rate_limited": (
        "The provider reported a request or token rate limit.",
        "Wait for Retry-After when provided, then reduce request frequency before a manual retry.",
    ),
    "rate_limit_or_quota": (
        "The provider returned HTTP 429 without a recognized cause.",
        "Check API Billing and rate limits before retrying. This record cannot distinguish quota from throttling.",
    ),
    "timeout": (
        "The model request timed out before a usable response arrived.",
        "No automatic retry was made. Check connectivity before a manual retry; the original request may be billable.",
    ),
    "connection": (
        "The application could not connect to the model provider.",
        "Check network or proxy configuration. Keep using offline mode while disconnected.",
    ),
    "authentication": (
        "The provider rejected the API credentials.",
        "Check the locally configured API key and organization. Do not paste credentials into chat or logs.",
    ),
    "permission": (
        "The provider denied access to this request.",
        "Check project permissions and provider access restrictions; retrying unchanged will not help.",
    ),
    "model_unavailable": (
        "The requested model or API resource was not found or is not accessible.",
        "Check OPENAI_MODEL and model access for the API project. No model substitution was performed.",
    ),
    "invalid_request": (
        "The provider rejected the request format or parameters.",
        "Inspect the model/schema configuration before retrying. No answer was accepted from this request.",
    ),
    "service_unavailable": (
        "The provider returned a server-side error or overload response.",
        "Wait for Retry-After when provided before a manual retry. No automatic retry was made.",
    ),
    "unknown": (
        "The provider request failed without a recognized error category.",
        "Inspect sanitized diagnostics or use offline mode. No unverified answer was released.",
    ),
}


def classify_provider_error(exc: Exception) -> ProviderFailure:
    status = getattr(exc, "status_code", None)
    status = status if type(status) is int and 400 <= status <= 599 else None
    raw_code = getattr(exc, "code", None)
    # Only known codes are exported. Arbitrary provider fields can contain user data.
    code = raw_code if isinstance(raw_code, str) and raw_code in CODE_CATEGORIES else None
    error_type = getattr(exc, "type", None)
    name = type(exc).__name__
    if status == 429 or name == "RateLimitError":
        category = CODE_CATEGORIES.get(code, "rate_limit_or_quota")
        if category == "rate_limit_or_quota":
            if error_type == "insufficient_quota":
                category = "quota_exceeded"
            elif error_type == "rate_limit_error":
                category = "rate_limited"
    elif isinstance(exc, TimeoutError) or name == "APITimeoutError":
        category = "timeout"
    elif isinstance(exc, ConnectionError) or name == "APIConnectionError":
        category = "connection"
    elif status == 401:
        category = "authentication"
    elif status == 403:
        category = "permission"
    elif status == 404:
        category = "model_unavailable"
    elif status in {400, 422}:
        category = "invalid_request"
    elif status is not None and status >= 500:
        category = "service_unavailable"
    else:
        category = "unknown"
    headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
    try:
        retry_after = float(headers.get("retry-after", ""))
        if not math.isfinite(retry_after) or not 0 <= retry_after <= 86400:
            retry_after = None
    except (TypeError, ValueError):
        retry_after = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str) or not re.fullmatch(r"req_[a-fA-F0-9]{16,64}", request_id):
        request_id = None
    message, action = MESSAGES[category]
    return ProviderFailure(
        category=category,
        code=code,
        http_status=status,
        request_id=request_id,
        retry_after_seconds=retry_after,
        retryable=category in {"rate_limited", "timeout", "connection", "service_unavailable"},
        message=message,
        suggested_action=action,
    )
