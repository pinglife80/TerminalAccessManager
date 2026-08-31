"""手动触发一次防火墙对账，验证分页修复后 gap 能否收敛。只读诊断用的临时脚本。"""
import asyncio
import json

from app.core.database import async_session_factory
from app.core.security import get_redis_client
from app.services.firewall_reconciliation_service import FirewallReconciliationService


async def main() -> None:
    async with async_session_factory() as db:
        svc = FirewallReconciliationService(db)
        results = await svc.reconcile()

        print("===== 对账结果 =====")
        print(f"firewall_ip_count     = {results.get('firewall_ip_count')}")
        print(f"db_entry_count        = {results.get('db_entry_count')}")
        print(f"missing_in_db(防火墙有DB无) = {len(results.get('missing_in_db', []))}")
        print(f"missing_in_firewall(DB有防火墙无) = {len(results.get('missing_in_firewall', []))}")
        print(f"created_in_db         = {results.get('created_in_db')}")
        print(f"reblocked_on_firewall = {results.get('reblocked_on_firewall')}")
        print(f"firewall_errors       = {results.get('firewall_errors')}")

        # 刷新 reconcile:latest 缓存
        try:
            from datetime import datetime, UTC
            redis_client = await get_redis_client()
            payload = {
                "firewall_ip_count": results.get("firewall_ip_count", 0),
                "db_entry_count": results.get("db_entry_count", 0),
                "firewall_errors": results.get("firewall_errors", []),
                "synced_at": datetime.now(UTC).isoformat(),
            }
            await redis_client.setex("reconcile:latest", 3600, json.dumps(payload))
            print("已刷新 reconcile:latest 缓存")
        except Exception as e:
            print(f"刷新缓存失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())