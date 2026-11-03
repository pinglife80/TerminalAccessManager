"""Tests for whitelist management"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.terminal import Terminal
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

    @pytest.mark.asyncio
    async def test_delete_mac_prefix_8_segments(self, db_session: AsyncSession):
        """An 8-hex-char (4-segment) MAC prefix entry can be deleted."""
        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_prefix="AA:BB:CC:DD",
            comments="prefix 4 segments",
            username="test_user",
        )

        success = await service.delete_from_whitelist("AABBCCDD", "test_user")
        assert success is True

        stmt = select(Whitelist).where(Whitelist.pattern_type == "mac_prefix")
        result = await db_session.execute(stmt)
        assert result.scalars().first() is None

    @pytest.mark.asyncio
    async def test_delete_mac_prefix_10_segments(self, db_session: AsyncSession):
        """A 10-hex-char (5-segment) MAC prefix entry can be deleted."""
        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_prefix="AA:BB:CC:DD:EE",
            comments="prefix 5 segments",
            username="test_user",
        )

        success = await service.delete_from_whitelist("AABBCCDDEE", "test_user")
        assert success is True

        stmt = select(Whitelist).where(Whitelist.pattern_type == "mac_prefix")
        result = await db_session.execute(stmt)
        assert result.scalars().first() is None

    @pytest.mark.asyncio
    async def test_delete_mac_prefix_with_separators(self, db_session: AsyncSession):
        """A MAC prefix entry can be deleted using the separated (AA:BB:CC) form."""
        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_prefix="AA:BB:CC",
            comments="prefix with separators",
            username="test_user",
        )

        success = await service.delete_from_whitelist("AA:BB:CC", "test_user")
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

    @pytest.mark.asyncio
    async def test_delete_full_mac_without_separators(self, db_session: AsyncSession):
        """A full MAC entry can be deleted using the un-separated 12-hex form."""
        mac_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            pattern_type="mac_only",
            comments="Test MAC no sep",
            added_by="test_user"
        )
        db_session.add(mac_entry)
        await db_session.commit()

        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AABBCCDDEEFF", "test_user")

        assert result is True

        stmt = Whitelist.__table__.select().where(Whitelist.mac_address == "AABBCCDDEEFF")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_full_mac_dash_format(self, db_session: AsyncSession):
        """A full MAC entry can be deleted using the dash-separated form."""
        mac_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            pattern_type="mac_only",
            comments="Test MAC dash",
            added_by="test_user"
        )
        db_session.add(mac_entry)
        await db_session.commit()

        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AA-BB-CC-DD-EE-FF", "test_user")

        assert result is True

        stmt = Whitelist.__table__.select().where(Whitelist.mac_address == "AABBCCDDEEFF")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_non_hex_mac_returns_false(self, db_session: AsyncSession):
        """A 12-char identifier with non-hex chars is NOT treated as a MAC and returns False."""
        mac_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            pattern_type="mac_only",
            comments="Test MAC",
            added_by="test_user"
        )
        db_session.add(mac_entry)
        await db_session.commit()

        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AA:BB:CC:DD:EE:GG", "test_user")

        assert result is False
        # Entry must remain untouched
        stmt = Whitelist.__table__.select().where(Whitelist.mac_address == "AABBCCDDEEFF")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_delete_full_mac_resets_terminal(self, db_session: AsyncSession):
        """Deleting a full-MAC entry resets the exact matching terminal to unknown."""
        terminal = Terminal(
            ip_address="192.168.1.50",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="bypass",
            wl_match_type="mac",
        )
        mac_entry = Whitelist(
            mac_address="AABBCCDDEEFF",
            mac_address_normalized="AABBCCDDEEFF",
            pattern_type="mac_only",
            comments="Test MAC",
            added_by="test_user"
        )
        db_session.add_all([terminal, mac_entry])
        await db_session.commit()

        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AA:BB:CC:DD:EE:FF", "test_user")

        assert result is True
        await db_session.refresh(terminal)
        assert terminal.compliance_status == "unknown"
        assert terminal.wl_match_type is None

    @pytest.mark.asyncio
    async def test_delete_mac_prefix_does_not_reset_matching_terminal(self, db_session: AsyncSession):
        """Deleting a MAC-prefix entry must NOT reset terminals whose MAC merely starts with the prefix."""
        terminal = Terminal(
            ip_address="192.168.1.51",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="bypass",
            wl_match_type="mac",
        )
        prefix_entry = Whitelist(
            mac_address="AABBCC",
            mac_address_normalized="AABBCC",
            pattern_type="mac_prefix",
            comments="vendor prefix",
            added_by="test_user"
        )
        db_session.add_all([terminal, prefix_entry])
        await db_session.commit()

        service = TerminalService(db_session)
        result = await service.delete_from_whitelist("AA:BB:CC", "test_user")

        assert result is True
        await db_session.refresh(terminal)
        assert terminal.compliance_status == "bypass"
        assert terminal.wl_match_type == "mac"


class TestWhitelistTerminalCommentsSync:
    """新增白名单即时生效时终端 comments 同步：清除封锁/解封注释 + 更新 Whitelist 注释。"""

    @pytest.mark.asyncio
    async def test_add_whitelist_syncs_terminal_comments(self, db_session: AsyncSession):
        """终端含封锁/解封注释 + 人工备注 → 添加白名单后 comments 更新并清除 Auto-* 注释。"""
        terminal = Terminal(
            ip_address="192.168.1.60",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="non_compliant",
            comments=(
                "Auto-blocked by TAM on firewall [FW-1]; "
                "Auto-unblocked by TAM from firewall [FW-1]; "
                "人工备注"
            ),
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_address="AA:BB:CC:DD:EE:FF",
            comments="合规设备",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.compliance_status == "bypass"
        assert terminal.wl_match_type == "mac"
        assert terminal.comments == "人工备注; Whitelist: 合规设备"

    @pytest.mark.asyncio
    async def test_add_whitelist_clears_block_comments_without_wl_comments(self, db_session: AsyncSession):
        """白名单 comments 为空：仅清除 Auto-* 注释，不写 Whitelist 注释。"""
        terminal = Terminal(
            ip_address="192.168.1.61",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="non_compliant",
            comments="Auto-blocked by TAM on firewall [FW-1]; 备注",
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_address="AA:BB:CC:DD:EE:FF",
            comments="",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.comments == "备注"

    @pytest.mark.asyncio
    async def test_add_whitelist_updates_existing_whitelist_comment(self, db_session: AsyncSession):
        """已有旧 Whitelist 注释 → 更新为新值，不重复追加。"""
        terminal = Terminal(
            ip_address="192.168.1.62",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="bypass",
            wl_match_type="mac",
            comments="Whitelist: old; 备注",
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_address="AA:BB:CC:DD:EE:FF",
            comments="new",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.comments == "备注; Whitelist: new"
        assert terminal.comments.count("Whitelist:") == 1

    @pytest.mark.asyncio
    async def test_add_mac_prefix_syncs_terminal_comments(self, db_session: AsyncSession):
        """mac_prefix 命中终端同样同步 comments。"""
        terminal = Terminal(
            ip_address="192.168.1.63",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="non_compliant",
            comments="Auto-blocked by TAM on firewall [FW-1]; 打印机组",
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_prefix="AA:BB:CC",
            comments="打印机厂商前缀",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.comments == "打印机组; Whitelist: 打印机厂商前缀"

    @pytest.mark.asyncio
    async def test_add_whitelist_unmatched_terminal_untouched(self, db_session: AsyncSession):
        """不匹配终端 comments 不受影响。"""
        terminal = Terminal(
            ip_address="192.168.1.64",
            mac_address="00:11:22:33:44:55",
            mac_address_normalized="001122334455",
            compliance_status="non_compliant",
            comments="Auto-blocked by TAM on firewall [FW-1]; 备注",
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_address="AA:BB:CC:DD:EE:FF",
            comments="合规设备",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.comments == "Auto-blocked by TAM on firewall [FW-1]; 备注"
        assert terminal.compliance_status == "non_compliant"

    @pytest.mark.asyncio
    async def test_add_whitelist_keeps_manual_comments(self, db_session: AsyncSession):
        """无 Auto-* 注释时人工备注原样保留并追加 Whitelist 注释。"""
        terminal = Terminal(
            ip_address="192.168.1.65",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            compliance_status="non_compliant",
            comments="备注1; 备注2",
        )
        db_session.add(terminal)
        await db_session.commit()

        service = TerminalService(db_session)
        await service.add_to_whitelist(
            mac_address="AA:BB:CC:DD:EE:FF",
            comments="合规设备",
            username="test_user",
        )

        await db_session.refresh(terminal)
        assert terminal.comments == "备注1; 备注2; Whitelist: 合规设备"
