"""Tests for terminal management endpoints"""


class TestTerminalSearch:
    """Test terminal search functionality"""

    def test_normalize_mac_colon(self):
        """MAC with colons should be normalized"""
        from app.services.terminal_service import _normalize_mac
        assert _normalize_mac("9B:E8:30:AB:CD:EF") == "9BE830ABCDEF"

    def test_normalize_mac_dash(self):
        """MAC with dashes should be normalized"""
        from app.services.terminal_service import _normalize_mac
        assert _normalize_mac("9B-E8-30-AB-CD-EF") == "9BE830ABCDEF"

    def test_normalize_mac_dot(self):
        """MAC with dots should be normalized"""
        from app.services.terminal_service import _normalize_mac
        assert _normalize_mac("9BE8.30AB.CDEF") == "9BE830ABCDEF"

    def test_normalize_mac_lowercase(self):
        """Lowercase MAC should be uppercased"""
        from app.services.terminal_service import _normalize_mac
        assert _normalize_mac("9b:e8:30:ab:cd:ef") == "9BE830ABCDEF"

    def test_normalize_mac_already_normalized(self):
        """Already normalized MAC should remain unchanged"""
        from app.services.terminal_service import _normalize_mac
        assert _normalize_mac("9BE830ABCDEF") == "9BE830ABCDEF"

    def test_escape_like_prevents_injection(self):
        """LIKE wildcards should be escaped"""
        from app.services.terminal_service import _escape_like
        assert _escape_like("test%") == r"test\%"
        assert _escape_like("test_") == r"test\_"
        assert _escape_like("100%") == r"100\%"


class TestTerminalModel:
    """Test Terminal model has required fields"""

    def test_terminal_has_normalized_mac(self):
        """Terminal model should have mac_address_normalized field"""
        from app.models.terminal import Terminal
        assert hasattr(Terminal, 'mac_address_normalized')

    def test_whitelist_has_normalized_mac(self):
        """Whitelist model should have mac_address_normalized field"""
        from app.models.whitelist import Whitelist
        assert hasattr(Whitelist, 'mac_address_normalized')

    def test_blacklist_has_normalized_mac(self):
        """Blacklist model should have mac_address_normalized field"""
        from app.models.blacklist import Blacklist
        assert hasattr(Blacklist, 'mac_address_normalized')
