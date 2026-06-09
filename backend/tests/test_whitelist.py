"""Tests for whitelist management"""
import pytest


class TestWhitelistModel:
    """Test Whitelist model structure"""

    def test_whitelist_has_required_fields(self):
        from app.models.whitelist import Whitelist
        assert hasattr(Whitelist, 'mac_address')
        assert hasattr(Whitelist, 'mac_address_normalized')
        assert hasattr(Whitelist, 'ip_pattern')
        assert hasattr(Whitelist, 'pattern_type')
        assert hasattr(Whitelist, 'comments')

    def test_whitelist_pattern_types(self):
        """Whitelist should support multiple pattern types"""
        from app.models.whitelist import Whitelist
        # pattern_type column should exist
        assert hasattr(Whitelist, 'pattern_type')


class TestWhitelistValidation:
    """Test whitelist input validation"""

    def test_mac_format_normalization(self):
        """MAC addresses should be normalizable to standard format"""
        from app.services.terminal_service import _normalize_mac
        # Various MAC formats should normalize to same value
        assert _normalize_mac("AA:BB:CC:DD:EE:FF") == _normalize_mac("AA-BB-CC-DD-EE-FF")
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == _normalize_mac("AABBCCDDEEFF")
