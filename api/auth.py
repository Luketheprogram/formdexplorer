from functools import wraps

from django.http import JsonResponse

from .models import ApiKey


def _extract_key(request) -> str:
    h = request.META.get("HTTP_AUTHORIZATION", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return request.GET.get("api_key", "").strip()


def api_key_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        raw = _extract_key(request)
        key = ApiKey.lookup(raw)
        if key is None:
            return JsonResponse(
                {"error": "invalid_api_key", "detail": "Missing or invalid API key."},
                status=401,
            )
        user = key.user
        if not user.is_active or user.subscription_tier != user.SUBSCRIPTION_API:
            return JsonResponse(
                {"error": "inactive_subscription", "detail": "API Access subscription required."},
                status=403,
            )
        allowed, remaining = key.consume()
        if not allowed:
            resp = JsonResponse(
                {"error": "rate_limited", "detail": "Monthly request limit exceeded."}, status=429
            )
            resp["X-RateLimit-Limit"] = str(key.monthly_limit)
            resp["X-RateLimit-Remaining"] = "0"
            return resp
        request.api_key = key
        response = view(request, *args, **kwargs)
        response["X-RateLimit-Limit"] = str(key.monthly_limit)
        response["X-RateLimit-Remaining"] = str(remaining)
        return response

    return wrapper
