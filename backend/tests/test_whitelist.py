"""Tests for whitelist management"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.whitelist import Whitelist
from app.services.terminal_service import (
    TerminalService,
    _normalize_mac,
    _validate_mac,
    _validate_mac_prefix,
)

# Create test database engine (SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class TestWhitelistModel:
    """Test Whitelist model structure"""

    def test_whitelist_has_required_fields(self):
        assert hasattr(Whitelist, 'mac_address')
        assert hasattr(Whitelist, 'mac_address_normalized')
        assert hasattr(Whitelist, 'ip_pattern')
        assert hasattr(Whitelist, 'pattern_type')
        assert hasattr(Whitelist, 'comments')

    def test_whitelist_pattern_types(self):
        """Whitelist should support multiple pattern types"""
        assert hasattr(Whitelist, 'pattern_type')


class TestWhitelistValidation:
    """Test whitelist input validation"""

    def test_mac_format_normalization(self):
        """MAC addresses should be normalizable to standard format"""
        assert _normalize_mac("AA:BB:CC:DD:EE:FF") == _normalize_mac("AA-BB-CC-DD-EE-FF")
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == _normalize_mac("AABBCCDDEEFF")


class TestMacPrefix:
    """Test MAC prefix validation and whitelist entry creation"""

    def test_validate_mac_full_address(self):
        """A full MAC address (6 segments) is accepted and normalized."""
        assert _validate_mac("aa:bb:cc:dd:ee:ff") == "AABBCCDDEEFF"
        with pytest.raises(ValueError):
            _validate_mac("AA:BB:CC:DD:EE")  # 5 segments is not a full MAC
        with pytest.raises(ValueError):
            _validate_mac("AA:BB:CC:DD:EE:GG")  # non-hex segment

    def test_validate_mac_prefix_valid(self):
        """3-5 segment prefixes with various separators normalize correctly."""
        assert _validate_mac_prefix("AA:BB:CC") == "AABBCC"
        assert _validate_mac_prefix("aa-bb-cc-dd") == "AABBCCDD"
        assert _validate_mac_prefix("AA:BB:CC:DD:EE") == "AABBCCDDEE"
        assert _validate_mac_prefix("aabbcc") == "AABBCC"
        assert _validate_mac_prefix("AA.BB.CC.DD") == "AABBCCDD"

    def test_validate_mac_prefix_invalid(self):
        """Prefixes with wrong segment counts or non-hex chars are rejected."""
        with pytest.raises(ValueError):
            _validate_mac_prefix("AA:BB")               # 2 segments
        with pytest.raises(ValueError):
            _validate_mac_prefix("AA:BB:CC:DD:EE:FF")   # 6 segments = full MAC, not a prefix
        with pytest.raises(ValueError):
            _validate_mac_prefix("AA:BB:GG")            # non-hex segment
        with pytest.raises(ValueError):
            _validate_mac_prefix("")                    # empty

    @pytest.mark.asyncio
    async def test_add_mac_prefix_entry(self, db_session: AsyncSession):
        """Adding a MAC prefix creates a mac_prefix entry with normalized storage."""
        service = TerminalService(db_session)
        result = await service.add_to_whitelist(
            mac_prefix="AA:BB:CC",
            comments="Printer vendor prefix",
            username="test_user",
        )
        assert result["success"] is True

        stmt = select(Whitelist).where(Whitelist.pattern_type == "mac_prefix")
        result = await db_session.execute(stmt)
        entry = result.scalar_one_or_none()
        assert entry is not None
        assert entry.mac_address == "AABBCC"
        assert entry.mac_address_normalized == "AABBCC"
        assert entry.ip_pattern is None

    @pytest.mark.asyncio
    async def test_add_mac_prefix_conflict_rejected(self, db_session: AsyncSession):
        """MAC prefix cannot be combined with a full MAC address or IP."""
        service = TerminalService(db_session)
        with pytest.raises(ValueError):
            await service.add_to_whitelist(
                mac_prefix="AA:BB:CC",
                mac_address="AA:BB:CC:DD:EE:FF",
                comments="conflict",
                username="test_user",
            )
        with pytest.raises(ValueError):
            await service.add_to_whitelist(
                mac_prefix="AA:BB:CC",
                ip_address="192.168.1.100",
                comments="conflict",
                username="test_user",
            )

    @pytest.mark.asyncio
    async def test_delete_mac_prefix_entry(self, db_session: AsyncSession):
        """A mac_prefix entry can be deleted by its normalized prefix (6 hex chars)."""
        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_prefix="AA:BB:CC",
            comments="Printer vendor prefix",
            username="test_user",
        )

        success = await service.delete_from_whitelist("AABBCC", "test_user")
        assert success is True

        stmt = select(Whitelist).where(Whitelist.pattern_type == "mac_prefix")
        result = await db_session.execute(stmt)
        assert result.scalars().first() is None


class TestWhitelistDeletion:
    """Test whitelist deletion scenarios"""

    @pytest.mark.asyncio
    async def test_delete_mac_only_entry(self, db_session: AsyncSession):
        """Test deleting a MAC-only whitelist entry"""
        # Create a MAC-only entry
        mac_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            pattern_type="mac_only",
            comments="Test MAC only",
            added_by="test_user"
        )
        db_session.add(mac_entry)
        await db_session.commit()

        # Delete by MAC
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AA:BB:CC:DD:EE:FF", "test_user")

        assert result is True

        # Verify entry is deleted
        stmt = Whitelist.__table__.select().where(Whitelist.mac_address == "AABBCCDDEEFF")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_ip_only_entry(self, db_session: AsyncSession):
        """Test deleting an IP-only whitelist entry"""
        # Create an IP-only entry
        ip_entry = Whitelist(
            ip_pattern="192.168.1.100",
            pattern_type="single_ip",
            comments="Test IP only",
            added_by="test_user"
        )
        db_session.add(ip_entry)
        await db_session.commit()

        # Delete by IP
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("192.168.1.100", "test_user")

        assert result is True

        # Verify entry is deleted
        stmt = Whitelist.__table__.select().where(Whitelist.ip_pattern == "192.168.1.100")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_cidr_entry(self, db_session: AsyncSession):
        """Test deleting a CIDR whitelist entry"""
        # Create a CIDR entry
        cidr_entry = Whitelist(
            ip_pattern="10.8.31.0/24",
            pattern_type="cidr",
            comments="Test CIDR",
            added_by="test_user"
        )
        db_session.add(cidr_entry)
        await db_session.commit()

        # Delete by CIDR
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("10.8.31.0/24", "test_user")

        assert result is True

        # Verify entry is deleted
        stmt = Whitelist.__table__.select().where(Whitelist.ip_pattern == "10.8.31.0/24")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_mac_and_ip_entry_by_mac(self, db_session: AsyncSession):
        """Test deleting a whitelist entry with both MAC and IP by MAC"""
        # Create an entry with both MAC and IP
        combined_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            ip_pattern="192.168.1.200",
            pattern_type="single_ip",
            comments="Test MAC and IP",
            added_by="test_user"
        )
        db_session.add(combined_entry)
        await db_session.commit()

        # Delete by MAC
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AABBCCDDEEFF", "test_user")

        assert result is True

        # Verify entry is deleted
        stmt = Whitelist.__table__.select().where(
            (Whitelist.mac_address == "AABBCCDDEEFF") &
            (Whitelist.ip_pattern == "192.168.1.200")
        )
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_mac_and_ip_entry_by_ip(self, db_session: AsyncSession):
        """Test deleting a whitelist entry with both MAC and IP by IP"""
        # Create an entry with both MAC and IP
        combined_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            ip_pattern="192.168.1.200",
            pattern_type="single_ip",
            comments="Test MAC and IP",
            added_by="test_user"
        )
        db_session.add(combined_entry)
        await db_session.commit()

        # Delete by IP
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("192.168.1.200", "test_user")

        assert result is True

        # Verify entry is deleted
        stmt = Whitelist.__table__.select().where(
            (Whitelist.mac_address == "AABBCCDDEEFF") &
            (Whitelist.ip_pattern == "192.168.1.200")
        )
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_entry(self, db_session: AsyncSession):
        """Test deleting a non-existent entry returns False"""
        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("00:11:22:33:44:55", "test_user")

        assert result is False
