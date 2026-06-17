"""Tests for blacklist management"""


class TestBlacklistModel:
    """Test Blacklist model structure"""

    def test_blacklist_has_required_fields(self):
        from app.models.blacklist import Blacklist
        assert hasattr(Blacklist, 'mac_address')
        assert hasattr(Blacklist, 'mac_address_normalized')
        assert hasattr(Blacklist, 'ip_address')
        assert hasattr(Blacklist, 'reason')
        assert hasattr(Blacklist, 'blocked_at')

    def test_blacklist_has_expires_at(self):
        """Blacklist entries should have expiration support"""
        from app.models.blacklist import Blacklist
        assert hasattr(Blacklist, 'expires_at')
