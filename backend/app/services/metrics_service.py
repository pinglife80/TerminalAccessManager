"""
Metrics Service for TerminalAccessManager.

Provides:
- Custom Prometheus metrics for business operations
- Terminal statistics (count by status, compliance)
- Block operation counters
- ARP collection duration histograms
- Firewall API latency tracking
- Login attempt tracking
- Notification metrics
"""

from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry, generate_latest

from app.core.config import settings

# Create a custom registry to avoid conflicts with default metrics
_metrics_registry = CollectorRegistry()

# ==================== System Info ====================

SYSTEM_INFO = Info(
    "tam",
    "Terminal Access Manager system information",
    registry=_metrics_registry,
)

SYSTEM_INFO.info({
    "version": settings.VERSION,
    "environment": settings.ENVIRONMENT,
    "project_name": settings.PROJECT_NAME,
})


# ==================== Terminal Metrics ====================

TERMINALS_TOTAL = Gauge(
    "tam_terminals_total",
    "Total number of terminals",
    ["source_tag"],
    registry=_metrics_registry,
)

TERMINALS_BY_STATUS = Gauge(
    "tam_terminals_by_status",
    "Number of terminals by status (blocked/unblocked)",
    ["status"],
    registry=_metrics_registry,
)

TERMINALS_BY_COMPLIANCE = Gauge(
    "tam_terminals_by_compliance",
    "Number of terminals by compliance status",
    ["status"],  # compliant, non_compliant, bypass, unknown
    registry=_metrics_registry,
)

COMPLIANCE_RATE = Gauge(
    "tam_compliance_rate",
    "Terminal compliance rate (percentage)",
    registry=_metrics_registry,
)


# ==================== Block Operation Metrics ====================

BLOCK_OPERATIONS_TOTAL = Counter(
    "tam_block_operations_total",
    "Total number of block/unblock operations",
    ["operation", "result", "source"],
    registry=_metrics_registry,
)

AUTO_BLOCK_TOTAL = Counter(
    "tam_auto_block_total",
    "Total number of auto-block operations triggered by compliance check",
    ["result"],
    registry=_metrics_registry,
)

AUTO_UNBLOCK_TOTAL = Counter(
    "tam_auto_unblock_total",
    "Total number of auto-unblock operations",
    ["result"],
    registry=_metrics_registry,
)


# ==================== ARP Collection Metrics ====================

ARP_COLLECTION_DURATION = Histogram(
    "tam_arp_collection_duration_seconds",
    "Duration of ARP collection operations",
    ["source_tag", "source_type"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=_metrics_registry,
)

ARP_COLLECTION_TOTAL = Counter(
    "tam_arp_collection_total",
    "Total number of ARP collection operations",
    ["source_tag", "source_type", "result"],
    registry=_metrics_registry,
)

ARP_ENTRIES_COLLECTED = Gauge(
    "tam_arp_entries_collected",
    "Number of ARP entries collected in last collection",
    ["source_tag"],
    registry=_metrics_registry,
)


# ==================== Firewall API Metrics ====================

FIREWALL_API_LATENCY = Histogram(
    "tam_firewall_api_latency_seconds",
    "Latency of firewall API calls",
    ["firewall_tag", "operation"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=_metrics_registry,
)

FIREWALL_API_TOTAL = Counter(
    "tam_firewall_api_total",
    "Total number of firewall API calls",
    ["firewall_tag", "operation", "result"],
    registry=_metrics_registry,
)


# ==================== Authentication Metrics ====================

LOGIN_ATTEMPTS_TOTAL = Counter(
    "tam_login_attempts_total",
    "Total number of login attempts",
    ["result"],  # success, failed, locked
    registry=_metrics_registry,
)

LOGIN_ATTEMPTS_BY_PROVIDER = Counter(
    "tam_login_attempts_by_provider_total",
    "Login attempts by authentication provider",
    ["provider", "result"],
    registry=_metrics_registry,
)

TOKEN_REFRESH_TOTAL = Counter(
    "tam_token_refresh_total",
    "Total number of token refresh operations",
    ["result"],
    registry=_metrics_registry,
)


# ==================== Notification Metrics ====================

NOTIFICATION_SENT_TOTAL = Counter(
    "tam_notification_sent_total",
    "Total number of notifications sent",
    ["channel", "event_type", "result"],
    registry=_metrics_registry,
)

NOTIFICATION_QUEUE_SIZE = Gauge(
    "tam_notification_queue_size",
    "Current size of notification queue",
    ["channel"],
    registry=_metrics_registry,
)


# ==================== DataSource Metrics ====================

DATASOURCE_SYNC_DURATION = Histogram(
    "tam_datasource_sync_duration_seconds",
    "Duration of data source synchronization",
    ["source_tag", "source_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=_metrics_registry,
)

DATASOURCE_SYNC_TOTAL = Counter(
    "tam_datasource_sync_total",
    "Total number of data source sync operations",
    ["source_tag", "result"],
    registry=_metrics_registry,
)


# ==================== Compliance Check Metrics ====================

COMPLIANCE_CHECK_DURATION = Histogram(
    "tam_compliance_check_duration_seconds",
    "Duration of compliance check operations",
    ["result"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=_metrics_registry,
)

COMPLIANCE_CHECK_TOTAL = Counter(
    "tam_compliance_check_total",
    "Total number of compliance check operations",
    ["result"],  # compliant, non_compliant, bypass
    registry=_metrics_registry,
)


# ==================== Whitelist/Blacklist Metrics ====================

WHITELIST_OPERATIONS_TOTAL = Counter(
    "tam_whitelist_operations_total",
    "Total number of whitelist operations",
    ["operation", "result"],
    registry=_metrics_registry,
)

BLACKLIST_OPERATIONS_TOTAL = Counter(
    "tam_blacklist_operations_total",
    "Total number of blacklist operations",
    ["operation", "result"],
    registry=_metrics_registry,
)

BLACKLIST_ENTRIES = Gauge(
    "tam_blacklist_entries",
    "Current number of blacklist entries",
    ["firewall_tag"],
    registry=_metrics_registry,
)


# ==================== HTTP Request Metrics ====================

HTTP_REQUESTS_TOTAL = Counter(
    "tam_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=_metrics_registry,
)

HTTP_REQUEST_DURATION = Histogram(
    "tam_http_request_duration_seconds",
    "Duration of HTTP requests",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=_metrics_registry,
)


# ==================== Database Metrics ====================

DATABASE_CONNECTIONS_ACTIVE = Gauge(
    "tam_database_connections_active",
    "Number of active database connections",
    registry=_metrics_registry,
)

DATABASE_QUERY_DURATION = Histogram(
    "tam_database_query_duration_seconds",
    "Duration of database queries",
    ["operation_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=_metrics_registry,
)


# ==================== Helper Functions ====================


def get_metrics() -> bytes:
    """Generate Prometheus metrics output"""
    return generate_latest(_metrics_registry)


def update_terminal_metrics(stats: dict):
    """
    Update terminal-related metrics from statistics dict.

    Args:
        stats: Dict with keys like 'total', 'blocked', 'unblocked',
               'compliant', 'non_compliant', 'bypass', 'unknown'
    """
    # Update total terminals
    total = stats.get("total", 0)
    TERMINALS_TOTAL.labels(source_tag="all").set(total)

    # Update by status
    TERMINALS_BY_STATUS.labels(status="blocked").set(stats.get("blocked", 0))
    TERMINALS_BY_STATUS.labels(status="unblocked").set(stats.get("unblocked", 0))

    # Update by compliance
    TERMINALS_BY_COMPLIANCE.labels(status="compliant").set(stats.get("compliant", 0))
    TERMINALS_BY_COMPLIANCE.labels(status="non_compliant").set(stats.get("non_compliant", 0))
    TERMINALS_BY_COMPLIANCE.labels(status="bypass").set(stats.get("bypass", 0))
    TERMINALS_BY_COMPLIANCE.labels(status="unknown").set(stats.get("unknown", 0))

    # Calculate compliance rate
    if total > 0:
        compliant = stats.get("compliant", 0)
        bypass = stats.get("bypass", 0)
        rate = ((compliant + bypass) / total) * 100
        COMPLIANCE_RATE.set(rate)
    else:
        COMPLIANCE_RATE.set(0)


def record_block_operation(operation: str, result: str, source: str = "manual"):
    """Record a block/unblock operation"""
    BLOCK_OPERATIONS_TOTAL.labels(
        operation=operation,
        result=result,
        source=source,
    ).inc()


def record_login_attempt(result: str, provider: str = "local"):
    """Record a login attempt"""
    LOGIN_ATTEMPTS_TOTAL.labels(result=result).inc()
    LOGIN_ATTEMPTS_BY_PROVIDER.labels(provider=provider, result=result).inc()


def record_arp_collection(
    source_tag: str,
    source_type: str,
    duration: float,
    result: str,
    entries_count: int = 0,
):
    """Record an ARP collection operation"""
    ARP_COLLECTION_DURATION.labels(
        source_tag=source_tag,
        source_type=source_type,
    ).observe(duration)

    ARP_COLLECTION_TOTAL.labels(
        source_tag=source_tag,
        source_type=source_type,
        result=result,
    ).inc()

    if entries_count >= 0:
        ARP_ENTRIES_COLLECTED.labels(source_tag=source_tag).set(entries_count)


def record_firewall_api_call(
    firewall_tag: str,
    operation: str,
    duration: float,
    result: str,
):
    """Record a firewall API call"""
    FIREWALL_API_LATENCY.labels(
        firewall_tag=firewall_tag,
        operation=operation,
    ).observe(duration)

    FIREWALL_API_TOTAL.labels(
        firewall_tag=firewall_tag,
        operation=operation,
        result=result,
    ).inc()


def record_notification(channel: str, event_type: str, result: str):
    """Record a notification sent"""
    NOTIFICATION_SENT_TOTAL.labels(
        channel=channel,
        event_type=event_type,
        result=result,
    ).inc()


def record_compliance_check(
    duration: float,
    compliant: int = 0,
    non_compliant: int = 0,
    bypass: int = 0,
):
    """Record a compliance check operation"""
    COMPLIANCE_CHECK_DURATION.labels(result="check").observe(duration)

    if compliant > 0:
        COMPLIANCE_CHECK_TOTAL.labels(result="compliant").inc(compliant)
    if non_compliant > 0:
        COMPLIANCE_CHECK_TOTAL.labels(result="non_compliant").inc(non_compliant)
    if bypass > 0:
        COMPLIANCE_CHECK_TOTAL.labels(result="bypass").inc(bypass)
