import asyncio
from datetime import datetime, UTC
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.blacklist import Blacklist


async def cleanup_duplicates():
    """Clean up duplicate blacklist entries for the same IP+MAC combination."""
    async with async_session_factory() as db:
        print("=== Blacklist Duplicate Cleanup ===")
        print(f"Start time: {datetime.now(UTC)}")

        duplicate_count = await find_and_remove_duplicates(db)
        
        print(f"\nCleanup completed. Removed {duplicate_count} duplicate entries.")


async def find_and_remove_duplicates(db: AsyncSession) -> int:
    """Find and remove duplicate blacklist entries, keeping only the most recent one."""
    removed_count = 0

    stmt = select(
        Blacklist.ip_address,
        Blacklist.mac_address_normalized,
        func.count(Blacklist.id).label('count'),
        func.max(Blacklist.id).label('latest_id'),
    ).where(
        Blacklist.unblocked_at.is_(None)
    ).group_by(
        Blacklist.ip_address,
        Blacklist.mac_address_normalized
    ).having(
        func.count(Blacklist.id) > 1
    )

    result = await db.execute(stmt)
    duplicates = result.all()

    print(f"\nFound {len(duplicates)} IP+MAC combinations with duplicates")

    for ip, mac_norm, count, latest_id in duplicates:
        print(f"\n  IP: {ip}, MAC: {mac_norm}")
        print(f"  Total entries: {count}, keeping latest (ID: {latest_id})")

        delete_stmt = delete(Blacklist).where(
            Blacklist.ip_address == ip,
            Blacklist.mac_address_normalized == mac_norm,
            Blacklist.unblocked_at.is_(None),
            Blacklist.id != latest_id
        )

        delete_result = await db.execute(delete_stmt)
        removed = delete_result.rowcount
        removed_count += removed
        print(f"  Removed {removed} duplicate entries")

    await db.commit()
    return removed_count


if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())