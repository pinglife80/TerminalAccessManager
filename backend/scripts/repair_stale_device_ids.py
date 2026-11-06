import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

# Allow running as a plain script (`python scripts/repair_stale_device_ids.py`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session_factory  # noqa: E402
from app.services.compliance_service import ComplianceService  # noqa: E402


async def repair_stale_device_ids(apply: bool) -> None:
    """Clear terminal device_id values that no longer match the device registry."""
    async with async_session_factory() as db:
        print("=== Stale device_id Repair ===")
        print(f"Start time: {datetime.now(UTC)}")
        print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")

        service = ComplianceService(db)
        result = await service.repair_stale_device_ids(apply=apply)

        if result["aborted"]:
            print(f"\nAborted: {result['aborted']}")
            return

        print(f"\nScanned terminals with device_id: {result['scanned']}")
        print(f"Stale associations: {result['repaired']}")

        for item in result["details"]:
            print(
                f"  id={item['id']} {item['ip_address']} {item['mac_address']} "
                f"device_id {item['old_device_id']} -> {item['current_device_id']} "
                f"offline_reset={item['offline_reset']}"
            )

        if not result["details"]:
            print("\nNothing to repair.")
        elif apply:
            print(f"\nApplied {result['repaired']} repairs.")
        else:
            print("\nDry-run only. Re-run with --apply to persist changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair stale terminal device_id associations (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the repairs (default: dry-run, no writes).",
    )
    args = parser.parse_args()
    asyncio.run(repair_stale_device_ids(args.apply))


if __name__ == "__main__":
    main()
