"""
Prometheus metrics definitions for AEGIS.
Used by proxy.py and pure_asgi.py middleware.
"""
from prometheus_client import Counter, Histogram

# ── HTTP Request metrics (used by ASGI middleware) ──

REQUEST_COUNT = Counter(
    "aegis_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── Proxy Execution metrics ──

PROXY_EXECUTIONS = Counter(
    "aegis_proxy_executions_total",
    "Total proxy executions by status",
    ["status"],
)

PROXY_COST = Counter(
    "aegis_proxy_cost_usd_total",
    "Total cost charged through proxy in USD",
)
