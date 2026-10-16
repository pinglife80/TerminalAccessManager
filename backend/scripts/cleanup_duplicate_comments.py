"""数据订正脚本：清理 terminals.comments 中历史遗留的重复 Auto-* 注释。

背景：
compliance_service 早期在补封 / 自动封锁 / 自动解封路径中，注释追加无去重，
导致同一终端被反复追加相同语义的注释：
- 「Auto-blocked by TAM on firewall [hq]」（防火墙「已存在」被误判为「新封锁」）
- 「Auto-unblocked by TAM from firewall [hq]」（封锁↔解封振荡循环）

本脚本对每台终端：
- 仅保留第一条 Auto-blocked 注释；
- 对 Auto-unblocked 注释按「防火墙集合（排序）」去重，忽略 (failed on: ...) 后缀，
  仅保留每个集合的第一条；
- 同时保留 Whitelist 等其它注释内容不被改动。

用法（缺省为 dry-run，只预览不写库）：
    # 在容器内执行（DB host 使用 docker 内网名 db）
    docker exec -it tam_backend python scripts/cleanup_duplicate_comments.py
    docker exec -it tam_backend python scripts/cleanup_duplicate_comments.py --apply
"""
import argparse
import asyncio
import re

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.terminal import Terminal

# 匹配 Auto-blocked（on firewall）
AUTO_BLOCK_PATTERN = re.compile(r"^Auto-blocked by TAM on firewall \[.*\]$")
# 匹配 Auto-unblocked（from firewall），捕获防火墙标签，忽略可选的 (failed on: ...) 后缀
AUTO_UNBLOCK_PATTERN = re.compile(r"^Auto-unblocked by TAM from firewall \[(.*)\](?: \(failed on:.*\))?$")


def dedupe_comments(comments: str) -> tuple[str, int]:
    """返回 (去重后的 comments, 被删除的重复 Auto-* 条数)。"""
    if not comments:
        return comments, 0

    segments = [s.strip() for s in comments.split(";")]
    segments = [s for s in segments if s]  # 去掉空段

    seen_auto_block = False
    seen_unblock_tags: set[tuple[str, ...]] = set()
    kept: list[str] = []
    removed = 0
    for seg in segments:
        if AUTO_BLOCK_PATTERN.match(seg):
            if not seen_auto_block:
                kept.append(seg)
                seen_auto_block = True
            else:
                removed += 1
            continue

        m = AUTO_UNBLOCK_PATTERN.match(seg)
        if m:
            tags = tuple(sorted(t.strip() for t in m.group(1).split(",") if t.strip()))
            if tags not in seen_unblock_tags:
                kept.append(seg)
                seen_unblock_tags.add(tags)
            else:
                removed += 1
            continue

        kept.append(seg)

    return "; ".join(kept), removed


async def main() -> None:
    parser = argparse.ArgumentParser(description="清理 terminals.comments 重复 Auto-* 注释")
    parser.add_argument("--apply", action="store_true", help="实际写库；缺省为 dry-run 只预览")
    args = parser.parse_args()

    async with async_session_factory() as db:
        result = await db.execute(
            select(Terminal).where(Terminal.comments.isnot(None))
        )
        terminals = result.scalars().all()

        total_terminals = len(terminals)
        affected_terminals = 0
        total_removed = 0
        sample_logs: list[str] = []

        for t in terminals:
            new_comments, removed = dedupe_comments(t.comments)
            if removed == 0:
                continue
            affected_terminals += 1
            total_removed += removed
            sample_logs.append(
                f"  IP={t.ip_address} MAC={t.mac_address}: 删除 {removed} 条重复 Auto-* 注释"
            )
            if args.apply:
                t.comments = new_comments

        print("=" * 60)
        print(f"模式: {'APPLY（已写库）' if args.apply else 'DRY-RUN（仅预览，未写库）'}")
        print(f"扫描终端总数: {total_terminals}")
        print(f"受影响终端数: {affected_terminals}")
        print(f"删除重复注释条数: {total_removed}")
        print("=" * 60)
        for line in sample_logs[:100]:
            print(line)
        if len(sample_logs) > 100:
            print(f"  ... 其余 {len(sample_logs) - 100} 条已省略")

        if args.apply:
            await db.commit()
            print("\n已提交变更到数据库。")
        else:
            print("\n未写库。确认无误后，使用 --apply 再次运行以实际订正数据。")


if __name__ == "__main__":
    asyncio.run(main())