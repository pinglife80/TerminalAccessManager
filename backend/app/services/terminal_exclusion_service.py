"""Terminal exclusion rules.

Rules are applied before ARP entries are persisted. A matching terminal is
never written to the ``terminals`` table, so it does not take part in
compliance calculation, auto block/unblock, notifications or statistics.

Matching semantics:
- A rule may define an IP condition, a MAC condition, or both (AND).
- Multiple rules are OR'ed.
"""

import ipaddress
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blacklist import Blacklist
from app.models.terminal import Terminal
from app.models.terminal_exclusion import TerminalExclusion
from app.schemas.terminal_exclusion import (
    ExclusionImpact,
    ExclusionSample,
    ExclusionUnblockResult,
    TerminalExclusionCreate,
    TerminalExclusionPreview,
    TerminalExclusionUpdate,
)
from app.services.terminal_service import (
    _normalize_mac,
    _validate_mac,
    _validate_mac_prefix,
)

logger = logging.getLogger(__name__)

IP_PATTERN_TYPES = {"single_ip", "cidr", "ip_range"}
MAC_PATTERN_TYPES = {"mac", "mac_prefix"}

_IP_RANGE_RE = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})-(\d{1,3})$")
_SAMPLE_LIMIT = 20
_DELETE_CHUNK_SIZE = 500


def _format_mac_hex(value: str) -> str:
    """'AABBCCDDEEFF' -> 'AA:BB:CC:DD:EE:FF'"""
    return ":".join(value[i:i + 2] for i in range(0, len(value), 2))


def _column_equals(column, value):
    """Render ``= value`` or ``IS NULL`` for nullable columns."""
    return column.is_(None) if value is None else column == value


class TerminalExclusionService:
    """CRUD, matching and retroactive cleanup for terminal exclusion rules."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Validation / normalization
    # ------------------------------------------------------------------
    @classmethod
    def validate_and_normalize(
        cls,
        ip_type: str | None,
        ip_value: str | None,
        mac_type: str | None,
        mac_value: str | None,
    ) -> dict[str, str | None]:
        """Validate a rule condition set and return normalized column values.

        At least one of the IP / MAC conditions must be present. Raises
        ``ValueError`` with a user-facing message on invalid input.
        """
        ip_value = (ip_value or "").strip()
        mac_value = (mac_value or "").strip()

        if not ip_value and not mac_value:
            raise ValueError("At least one of IP condition or MAC condition is required")

        ip_pattern: str | None = None
        ip_pattern_type: str | None = None
        if ip_value:
            if ip_type not in IP_PATTERN_TYPES:
                raise ValueError("IP condition type is required when an IP value is provided")
            ip_pattern, ip_pattern_type = cls._normalize_ip(ip_type, ip_value)

        mac_address: str | None = None
        mac_pattern_type: str | None = None
        if mac_value:
            if mac_type not in MAC_PATTERN_TYPES:
                raise ValueError("MAC condition type is required when a MAC value is provided")
            mac_address, mac_pattern_type = cls._normalize_mac_condition(mac_type, mac_value)

        return {
            "ip_pattern": ip_pattern,
            "ip_pattern_type": ip_pattern_type,
            "mac_address": mac_address,
            "mac_pattern_type": mac_pattern_type,
        }

    @staticmethod
    def _normalize_ip(ip_type: str, ip_value: str) -> tuple[str, str]:
        if ip_type == "single_ip":
            try:
                return str(ipaddress.IPv4Address(ip_value)), ip_type
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid IP address: '{ip_value}': {exc}") from exc

        if ip_type == "cidr":
            if "/" not in ip_value:
                raise ValueError(
                    f"Invalid IP CIDR: '{ip_value}'. Expected format: 192.168.1.0/24"
                )
            prefix_str = ip_value.rsplit("/", 1)[1]
            if not prefix_str.isdigit() or not 0 <= int(prefix_str) <= 32:
                raise ValueError(
                    f"Invalid IP CIDR prefix: '{ip_value}'. Prefix must be an integer in 0-32"
                )
            try:
                return str(ipaddress.IPv4Network(ip_value, strict=False)), ip_type
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid IP CIDR: '{ip_value}': {exc}") from exc

        match = _IP_RANGE_RE.match(ip_value)
        if not match:
            raise ValueError(
                f"Invalid IP range: '{ip_value}'. Expected format: 192.168.1.1-100"
            )
        prefix, start_str, end_str = match.groups()
        try:
            ipaddress.IPv4Address(f"{prefix}.1")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid IP range: '{ip_value}': {exc}") from exc
        start, end = int(start_str), int(end_str)
        if start > end:
            raise ValueError(f"Invalid IP range: start ({start}) is greater than end ({end})")
        if end > 255:
            raise ValueError(f"Invalid IP range: end ({end}) exceeds 255")
        return f"{prefix}.{start}-{end}", ip_type

    @staticmethod
    def _normalize_mac_condition(mac_type: str, mac_value: str) -> tuple[str, str]:
        if mac_type == "mac":
            return _format_mac_hex(_validate_mac(mac_value)), mac_type
        return _format_mac_hex(_validate_mac_prefix(mac_value)), mac_type

    # ------------------------------------------------------------------
    # Pure matching helpers
    # ------------------------------------------------------------------
    @staticmethod
    def match_ip(ip_address: str, pattern: str | None, pattern_type: str | None) -> bool:
        if not pattern or not pattern_type:
            return False
        try:
            address = ipaddress.IPv4Address((ip_address or "").strip())
        except (ValueError, TypeError):
            return False

        if pattern_type == "single_ip":
            return str(address) == pattern

        if pattern_type == "cidr":
            try:
                return address in ipaddress.IPv4Network(pattern, strict=False)
            except (ValueError, TypeError):
                return False

        if pattern_type == "ip_range":
            match = _IP_RANGE_RE.match(pattern)
            if not match:
                return False
            prefix, start_str, end_str = match.groups()
            parts = str(address).split(".")
            if ".".join(parts[:3]) != prefix:
                return False
            return int(start_str) <= int(parts[3]) <= int(end_str)

        return False

    @staticmethod
    def match_mac(mac_address: str, value: str | None, pattern_type: str | None) -> bool:
        if not value or not pattern_type:
            return False
        normalized = _normalize_mac(mac_address or "")
        if not normalized:
            return False
        target = _normalize_mac(value)
        if pattern_type == "mac":
            return normalized == target
        if pattern_type == "mac_prefix":
            return normalized.startswith(target)
        return False

    @classmethod
    def matches_rule(
        cls,
        rule: dict[str, Any],
        ip_address: str,
        mac_address: str,
    ) -> bool:
        """Evaluate one rule. IP and MAC conditions, when both present, are AND'ed."""
        has_ip = bool(rule.get("ip_pattern"))
        has_mac = bool(rule.get("mac_address"))
        if not has_ip and not has_mac:
            return False
        if has_ip and not cls.match_ip(ip_address, rule.get("ip_pattern"), rule.get("ip_pattern_type")):
            return False
        return not (
            has_mac
            and not cls.match_mac(mac_address, rule.get("mac_address"), rule.get("mac_pattern_type"))
        )

    @classmethod
    def matches_any(
        cls,
        rules: list[dict[str, Any]],
        ip_address: str,
        mac_address: str,
    ) -> bool:
        return any(cls.matches_rule(rule, ip_address, mac_address) for rule in rules)

    @classmethod
    def first_match(
        cls,
        rules: list[dict[str, Any]],
        ip_address: str,
        mac_address: str,
    ) -> dict[str, Any] | None:
        """Return the first matching rule (for diagnostics/logging), or None."""
        for rule in rules:
            if cls.matches_rule(rule, ip_address, mac_address):
                return rule
        return None

    @staticmethod
    def describe_rule(rule: dict[str, Any] | None) -> str:
        """Render a rule as a compact human-readable string for logs."""
        if not rule:
            return "<none>"
        parts: list[str] = []
        if rule.get("ip_pattern"):
            parts.append(f"IP {rule.get('ip_pattern_type')}={rule.get('ip_pattern')}")
        if rule.get("mac_address"):
            parts.append(f"MAC {rule.get('mac_pattern_type')}={rule.get('mac_address')}")
        return " AND ".join(parts) if parts else "<empty>"

    @staticmethod
    def rule_to_dict(rule: TerminalExclusion) -> dict[str, Any]:
        return {
            "ip_pattern": rule.ip_pattern,
            "ip_pattern_type": rule.ip_pattern_type,
            "mac_address": rule.mac_address,
            "mac_pattern_type": rule.mac_pattern_type,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def list_rules(self, is_active: bool | None = None) -> list[TerminalExclusion]:
        stmt = select(TerminalExclusion).order_by(
            TerminalExclusion.created_at.desc(), TerminalExclusion.id.desc()
        )
        if is_active is not None:
            stmt = stmt.where(TerminalExclusion.is_active == is_active)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: int) -> TerminalExclusion | None:
        result = await self.db.execute(
            select(TerminalExclusion).where(TerminalExclusion.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def load_active_rules(self) -> list[dict[str, Any]]:
        """Load all active rules once; callers reuse the list for matching."""
        result = await self.db.execute(
            select(TerminalExclusion).where(TerminalExclusion.is_active == True)  # noqa: E712
        )
        return [self.rule_to_dict(rule) for rule in result.scalars().all()]

    async def _find_duplicate(
        self,
        values: dict[str, str | None],
        exclude_id: int | None = None,
    ) -> TerminalExclusion | None:
        stmt = select(TerminalExclusion).where(
            _column_equals(TerminalExclusion.ip_pattern, values["ip_pattern"]),
            _column_equals(TerminalExclusion.ip_pattern_type, values["ip_pattern_type"]),
            _column_equals(TerminalExclusion.mac_address, values["mac_address"]),
            _column_equals(TerminalExclusion.mac_pattern_type, values["mac_pattern_type"]),
        )
        if exclude_id is not None:
            stmt = stmt.where(TerminalExclusion.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_rule(
        self,
        data: TerminalExclusionCreate,
        username: str,
    ) -> tuple[TerminalExclusion, ExclusionImpact, ExclusionUnblockResult | None]:
        values = self.validate_and_normalize(
            data.ip_type, data.ip_value, data.mac_type, data.mac_value
        )
        if await self._find_duplicate(values):
            raise ValueError("An identical exclusion rule already exists")

        rule = TerminalExclusion(
            **values,
            comments=data.comments.strip(),
            is_active=True,
            created_by=username,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        impact, unblock = await self.purge_matching(
            self.rule_to_dict(rule),
            unblock_blocked=data.unblock_blocked,
            actor=username,
        )
        logger.info(
            "Created terminal exclusion rule id=%s (matched=%s, purged=%s, "
            "retained=%s, unblock_requested=%s, unblocked=%s, failed=%s) by %s",
            rule.id, impact.matched, impact.purgeable, impact.retained,
            data.unblock_blocked, unblock.unblocked if unblock else 0,
            unblock.failed if unblock else 0, username,
        )
        return rule, impact, unblock

    async def update_rule(
        self,
        rule_id: int,
        data: TerminalExclusionUpdate,
    ) -> tuple[TerminalExclusion | None, ExclusionImpact | None]:
        rule = await self.get_rule(rule_id)
        if not rule:
            return None, None

        update_data = data.model_dump(exclude_unset=True)
        conditions_changed = any(
            key in update_data
            for key in ("ip_type", "ip_value", "mac_type", "mac_value")
        )
        was_active = rule.is_active

        if conditions_changed:
            values = self.validate_and_normalize(
                update_data.get("ip_type", rule.ip_pattern_type),
                update_data.get("ip_value", rule.ip_pattern),
                update_data.get("mac_type", rule.mac_pattern_type),
                update_data.get("mac_value", rule.mac_address),
            )
            if await self._find_duplicate(values, exclude_id=rule.id):
                raise ValueError("An identical exclusion rule already exists")
            for key, value in values.items():
                setattr(rule, key, value)

        if "comments" in update_data and update_data["comments"] is not None:
            comments = update_data["comments"].strip()
            if not comments:
                raise ValueError("Comments cannot be empty")
            rule.comments = comments
        if "is_active" in update_data and update_data["is_active"] is not None:
            rule.is_active = update_data["is_active"]

        await self.db.commit()
        await self.db.refresh(rule)

        impact = None
        if rule.is_active and (conditions_changed or not was_active):
            impact, _ = await self.purge_matching(self.rule_to_dict(rule))
        if conditions_changed or not rule.is_active:
            # 条件收窄或被停用时，旧的保留行可能不再命中，标记需要回收。
            await self.clear_stale_exclusion_flags()
        return rule, impact

    async def delete_rule(self, rule_id: int) -> bool:
        rule = await self.get_rule(rule_id)
        if not rule:
            return False
        await self.db.delete(rule)
        await self.db.commit()
        await self.clear_stale_exclusion_flags()
        logger.info("Deleted terminal exclusion rule id=%s", rule_id)
        return True

    async def toggle_rule(
        self,
        rule_id: int,
        unblock_blocked: bool = False,
        actor: str = "system",
    ) -> tuple[TerminalExclusion | None, ExclusionImpact | None, ExclusionUnblockResult | None]:
        rule = await self.get_rule(rule_id)
        if not rule:
            return None, None, None
        rule.is_active = not rule.is_active
        await self.db.commit()
        await self.db.refresh(rule)
        impact: ExclusionImpact | None = None
        unblock: ExclusionUnblockResult | None = None
        if rule.is_active:
            impact, unblock = await self.purge_matching(
                self.rule_to_dict(rule),
                unblock_blocked=unblock_blocked,
                actor=actor,
            )
        else:
            # 停用后该规则不再覆盖任何终端，回收其留在库中的排除标记。
            await self.clear_stale_exclusion_flags()
        return rule, impact, unblock

    # ------------------------------------------------------------------
    # Impact evaluation / retroactive cleanup
    # ------------------------------------------------------------------
    async def load_active_blacklist_ips(self) -> set[str]:
        """Active blacklist IPs, using the same definition as dashboard stats."""
        now = datetime.now(UTC)
        stmt = select(Blacklist.ip_address).where(
            (Blacklist.auto_unblocked == False)  # noqa: E712
            & (Blacklist.unblocked_at.is_(None))
            & or_(
                Blacklist.expires_at >= now,
                Blacklist.expires_at.is_(None),
            )
            & Blacklist.ip_address.is_not(None)
        )
        result = await self.db.execute(stmt)
        return {row[0] for row in result.all() if row[0]}

    @staticmethod
    def can_purge(terminal: Terminal, active_blacklist_ips: set[str]) -> bool:
        """Blocked terminals are kept so firewall state / blacklist stay consistent."""
        if terminal.status == "blocked":
            return False
        return (terminal.ip_address or "") not in active_blacklist_ips

    async def preview_rule(self, data: TerminalExclusionPreview) -> ExclusionImpact:
        values = self.validate_and_normalize(
            data.ip_type, data.ip_value, data.mac_type, data.mac_value
        )
        impact, _, _, _ = await self._evaluate(values)
        return impact

    async def purge_matching(
        self,
        rule: dict[str, Any],
        unblock_blocked: bool = False,
        actor: str = "system",
    ) -> tuple[ExclusionImpact, ExclusionUnblockResult | None]:
        impact, terminal_ids, retained_ids, blocked_terminals = await self._evaluate(
            rule, collect_ids=True
        )

        unblock: ExclusionUnblockResult | None = None
        unblocked_pairs: list[tuple[str, str]] = []
        if unblock_blocked:
            if blocked_terminals:
                unblock, unblocked_ids, unblocked_pairs = await self._unblock_blocked_terminals(
                    blocked_terminals, actor
                )
                if unblocked_ids:
                    # 解封成功的终端彻底退出终端库与统计。
                    terminal_ids.extend(unblocked_ids)
                    retained_ids = [tid for tid in retained_ids if tid not in set(unblocked_ids)]
                    impact.retained = max(0, impact.retained - len(unblocked_ids))
            else:
                unblock = ExclusionUnblockResult(requested=True)

        for start in range(0, len(terminal_ids), _DELETE_CHUNK_SIZE):
            chunk = terminal_ids[start:start + _DELETE_CHUNK_SIZE]
            await self.db.execute(
                delete(Terminal)
                .where(Terminal.id.in_(chunk))
                .execution_options(synchronize_session=False)
            )
        if retained_ids:
            # 保留行仍在 terminals 表中，但必须打标以便统计口径排除它们。
            await self.db.execute(
                update(Terminal)
                .where(Terminal.id.in_(retained_ids))
                .values(excluded_by_rule=True)
                .execution_options(synchronize_session="fetch")
            )
        if terminal_ids or retained_ids:
            await self.db.commit()
        logger.info(
            "Terminal exclusion purge: matched=%s purged=%s retained=%s "
            "unblock_requested=%s unblocked=%s unblock_failed=%s unblock_skipped=%s",
            impact.matched, impact.purgeable, impact.retained,
            unblock_blocked, unblock.unblocked if unblock else 0,
            unblock.failed if unblock else 0, unblock.skipped if unblock else 0,
        )

        if unblocked_pairs:
            from app.services.event_emitter import emit_terminal_unblocked

            for ip, mac in unblocked_pairs:
                await emit_terminal_unblocked(ip, mac, actor)

        return impact, unblock

    async def _unblock_blocked_terminals(
        self,
        terminals: list[Terminal],
        actor: str,
    ) -> tuple[ExclusionUnblockResult, list[int], list[tuple[str, str]]]:
        """Unblock excluded terminals that are currently blocked.

        A terminal is only treated as unblocked when every firewall resolved for
        its active blacklist entries reports success; otherwise it is kept in
        the database (still blocked) so statistics and firewall state stay
        consistent.
        """
        # Local import to avoid a module-level cycle:
        # compliance_service -> terminal_exclusion_service.
        from app.services.compliance_service import ComplianceService

        compliance = ComplianceService(self.db)
        result = ExclusionUnblockResult(requested=True)
        unblocked_ids: list[int] = []
        unblocked_pairs: list[tuple[str, str]] = []
        now = datetime.now(UTC)

        for terminal in terminals:
            ip_address = terminal.ip_address or ""
            mac_address = terminal.mac_address or ""
            label = f"{ip_address}/{mac_address}"
            logger.info(
                "Exclusion unblock begin: terminal_id=%s ip=%s mac=%s status=%s actor=%s",
                terminal.id, ip_address, mac_address, terminal.status, actor,
            )

            stmt = select(Blacklist).where(
                (Blacklist.auto_unblocked == False)  # noqa: E712
                & (Blacklist.unblocked_at.is_(None))
                & or_(
                    Blacklist.expires_at >= now,
                    Blacklist.expires_at.is_(None),
                )
            )
            ip_or_mac = [Blacklist.ip_address == ip_address]
            if terminal.mac_address_normalized:
                ip_or_mac.append(
                    Blacklist.mac_address_normalized == terminal.mac_address_normalized
                )
            stmt = stmt.where(or_(*ip_or_mac))
            entries = list((await self.db.execute(stmt)).scalars().all())

            if not entries:
                result.skipped += 1
                result.errors.append(
                    f"{label}: no active blacklist entry, firewall block cannot be located"
                )
                logger.info(
                    "Exclusion unblock skipped: terminal_id=%s ip=%s mac=%s "
                    "reason=no_active_blacklist_entry",
                    terminal.id, ip_address, mac_address,
                )
                continue

            logger.info(
                "Exclusion unblock blacklist entries resolved: terminal_id=%s ip=%s "
                "count=%s entries=%s",
                terminal.id, ip_address, len(entries),
                [
                    {
                        "id": entry.id,
                        "ip": entry.ip_address,
                        "firewall_tag": entry.firewall_tag,
                        "source_tag": entry.source_tag,
                    }
                    for entry in entries
                ],
            )

            all_success = True
            firewalls_resolved = False
            succeeded_entries: list[Blacklist] = []
            terminal_errors: list[str] = []

            for entry in entries:
                blocked_ip = entry.ip_address or ip_address
                firewall_tags: list[str] = []
                if entry.firewall_tag:
                    firewall_tags = [entry.firewall_tag]
                elif entry.source_tag:
                    firewall_tags = await compliance._get_bound_firewall_tags(entry.source_tag)

                if not firewall_tags:
                    all_success = False
                    terminal_errors.append(
                        f"{blocked_ip}: no firewall binding for blacklist entry {entry.id}"
                    )
                    logger.info(
                        "Exclusion unblock entry skipped: terminal_id=%s blacklist_id=%s "
                        "ip=%s reason=no_firewall_binding (firewall_tag=%s, source_tag=%s)",
                        terminal.id, entry.id, blocked_ip,
                        entry.firewall_tag, entry.source_tag,
                    )
                    continue

                firewalls_resolved = True
                entry_success = True
                for firewall_tag in firewall_tags:
                    try:
                        success = await compliance._unblock_on_firewall(
                            blocked_ip,
                            firewall_tag,
                            terminal.id,
                            mac_address,
                            actor=actor,
                        )
                    except Exception as exc:  # firewall call must not break the rule
                        success = False
                        terminal_errors.append(
                            f"{blocked_ip} @ {firewall_tag}: {exc}"
                        )
                    logger.info(
                        "Exclusion unblock firewall result: terminal_id=%s blacklist_id=%s "
                        "ip=%s firewall=%s success=%s",
                        terminal.id, entry.id, blocked_ip, firewall_tag, success,
                    )
                    if not success:
                        entry_success = False
                        all_success = False
                        if not any(
                            blocked_ip in msg and firewall_tag in msg
                            for msg in terminal_errors
                        ):
                            terminal_errors.append(
                                f"{blocked_ip} @ {firewall_tag}: unblock failed"
                            )

                if entry_success:
                    succeeded_entries.append(entry)

            # Successful entries keep an audit trail even when the terminal is
            # only partially unblocked.
            reason = "excluded_by_rule" if all_success else "excluded_by_rule（部分成功）"
            for entry in succeeded_entries:
                entry.auto_unblocked = True
                entry.unblocked_at = now
                entry.unblock_reason = reason
                entry.last_operation_type = "unblock"
                entry.last_operation_status = "success"
                entry.last_operation_at = now

            if all_success:
                result.unblocked += 1
                unblocked_ids.append(terminal.id)
                unblocked_pairs.append((ip_address, mac_address))
                logger.info(
                    "Exclusion unblock ALL_SUCCESS: terminal_id=%s ip=%s mac=%s "
                    "entries=%s -> terminal will be deleted",
                    terminal.id, ip_address, mac_address,
                    [entry.id for entry in succeeded_entries],
                )
            elif not firewalls_resolved:
                result.skipped += 1
                result.errors.extend(terminal_errors)
                logger.info(
                    "Exclusion unblock SKIPPED: terminal_id=%s ip=%s mac=%s "
                    "reason=no_firewall_binding errors=%s -> terminal retained",
                    terminal.id, ip_address, mac_address, "; ".join(terminal_errors),
                )
            else:
                result.failed += 1
                result.errors.extend(terminal_errors)
                logger.info(
                    "Exclusion unblock PARTIAL/FAILED: terminal_id=%s ip=%s mac=%s "
                    "succeeded_entries=%s failed_entries=%s errors=%s "
                    "-> terminal retained and excluded_by_rule=True",
                    terminal.id, ip_address, mac_address,
                    [entry.id for entry in succeeded_entries],
                    len(entries) - len(succeeded_entries),
                    "; ".join(terminal_errors),
                )

        logger.info(
            "Exclusion unblock finished: terminals=%s unblocked=%s failed=%s skipped=%s",
            len(terminals), result.unblocked, result.failed, result.skipped,
        )

        if result.errors:
            logger.warning(
                "Terminal exclusion unblock: requested=%s unblocked=%s failed=%s skipped=%s errors=%s",
                len(terminals), result.unblocked, result.failed, result.skipped,
                "; ".join(result.errors),
            )
        return result, unblocked_ids, unblocked_pairs

    async def clear_stale_exclusion_flags(self) -> int:
        """Unset ``excluded_by_rule`` for rows that no longer match any active rule.

        Called after a rule is deleted, disabled or narrowed so retained rows
        return to the statistics once the rule stops covering them.
        """
        rules = await self.load_active_rules()
        result = await self.db.execute(
            select(Terminal).where(Terminal.excluded_by_rule == True)  # noqa: E712
        )
        cleared = 0
        for terminal in result.scalars().all():
            if not self.matches_any(
                rules, terminal.ip_address or "", terminal.mac_address or ""
            ):
                terminal.excluded_by_rule = False
                cleared += 1
        if cleared:
            await self.db.commit()
            logger.info(
                "Terminal exclusion flags refreshed: cleared=%s (active_rules=%s)",
                cleared,
                len(rules),
            )
        return cleared

    async def _evaluate(
        self,
        rule: dict[str, Any],
        collect_ids: bool = False,
    ) -> tuple[ExclusionImpact, list[int], list[int], list[Terminal]]:
        blacklist_ips = await self.load_active_blacklist_ips()
        result = await self.db.execute(select(Terminal))
        terminals = result.scalars().all()

        matched = 0
        purgeable = 0
        retained = 0
        blocked = 0
        samples: list[ExclusionSample] = []
        terminal_ids: list[int] = []
        retained_ids: list[int] = []
        blocked_terminals: list[Terminal] = []

        for terminal in terminals:
            if not self.matches_rule(
                rule, terminal.ip_address or "", terminal.mac_address or ""
            ):
                continue
            matched += 1

            reason: str | None = None
            if terminal.status == "blocked":
                reason = "blocked"
                blocked += 1
                if collect_ids:
                    blocked_terminals.append(terminal)
            elif (terminal.ip_address or "") in blacklist_ips:
                reason = "active_blacklist"

            if reason:
                retained += 1
                if collect_ids:
                    retained_ids.append(terminal.id)
            else:
                purgeable += 1
                if collect_ids:
                    terminal_ids.append(terminal.id)

            if len(samples) < _SAMPLE_LIMIT:
                samples.append(
                    ExclusionSample(
                        ip_address=terminal.ip_address or "",
                        mac_address=terminal.mac_address or "",
                        status=terminal.status or "",
                        reason=reason or "purge",
                    )
                )

        return (
            ExclusionImpact(
                matched=matched,
                purgeable=purgeable,
                retained=retained,
                blocked=blocked,
                samples=samples,
            ),
            terminal_ids,
            retained_ids,
            blocked_terminals,
        )
