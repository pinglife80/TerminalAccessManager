"""
Unit tests for the metrics service module.

All Prometheus metric objects are module-level singletons backed by a custom
CollectorRegistry, so no external scrape endpoint or real registry is needed.
"""

import app.services.metrics_service as ms


class TestGetMetrics:
    def test_returns_nonempty_bytes(self):
        output = ms.get_metrics()
        assert isinstance(output, bytes)
        assert len(output) > 0


class TestUpdateTerminalMetrics:
    def test_sets_gauges_and_compliance_rate(self):
        ms.update_terminal_metrics({
            "total": 100,
            "blocked": 20,
            "unblocked": 80,
            "compliant": 70,
            "non_compliant": 10,
            "bypass": 20,
            "unknown": 0,
        })

        reg = ms._metrics_registry
        assert reg.get_sample_value("tam_terminals_total", {"source_tag": "all"}) == 100.0
        assert reg.get_sample_value("tam_terminals_by_status", {"status": "blocked"}) == 20.0
        assert reg.get_sample_value("tam_terminals_by_status", {"status": "unblocked"}) == 80.0
        assert reg.get_sample_value("tam_terminals_by_compliance", {"status": "compliant"}) == 70.0
        assert reg.get_sample_value("tam_terminals_by_compliance", {"status": "bypass"}) == 20.0
        # (70 + 20) / 100 * 100
        assert reg.get_sample_value("tam_compliance_rate") == 90.0

    def test_zero_total_sets_zero_compliance_rate(self):
        ms.update_terminal_metrics({"total": 0, "compliant": 0, "bypass": 0})
        assert ms._metrics_registry.get_sample_value("tam_compliance_rate") == 0.0


class TestRecordFunctions:
    def test_record_block_operation(self):
        ms.record_block_operation("block", "success", source="auto")
        assert ms._metrics_registry.get_sample_value(
            "tam_block_operations_total",
            {"operation": "block", "result": "success", "source": "auto"},
        ) is not None

    def test_record_login_attempt(self):
        ms.record_login_attempt("success", provider="local")
        assert ms._metrics_registry.get_sample_value(
            "tam_login_attempts_total", {"result": "success"}
        ) is not None

    def test_record_arp_collection_sets_entries(self):
        ms.record_arp_collection("lab", "arp_ssh", 1.5, "success", entries_count=42)
        assert ms._metrics_registry.get_sample_value(
            "tam_arp_entries_collected", {"source_tag": "lab"}
        ) == 42.0

    def test_record_arp_collection_negative_entries_skipped(self):
        # entries_count < 0 must not raise and must skip the gauge set
        ms.record_arp_collection("lab", "arp_ssh", 1.5, "success", entries_count=-1)

    def test_record_firewall_api_call(self):
        ms.record_firewall_api_call("fw1", "block", 0.3, "success")
        assert ms._metrics_registry.get_sample_value(
            "tam_firewall_api_total",
            {"firewall_tag": "fw1", "operation": "block", "result": "success"},
        ) is not None

    def test_record_notification(self):
        ms.record_notification("email", "blocked", "success")
        assert ms._metrics_registry.get_sample_value(
            "tam_notification_sent_total",
            {"channel": "email", "event_type": "blocked", "result": "success"},
        ) is not None

    def test_record_compliance_check_positive_counts(self):
        ms.record_compliance_check(1.0, compliant=5, non_compliant=2, bypass=3)
        reg = ms._metrics_registry
        assert reg.get_sample_value("tam_compliance_check_total", {"result": "compliant"}) is not None
        assert reg.get_sample_value("tam_compliance_check_total", {"result": "non_compliant"}) is not None
        assert reg.get_sample_value("tam_compliance_check_total", {"result": "bypass"}) is not None

    def test_record_compliance_check_zero_counts(self):
        # zero counts skip all three inc() calls; must not raise
        ms.record_compliance_check(1.0, compliant=0, non_compliant=0, bypass=0)