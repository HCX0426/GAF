"""sync_workbuddy_skills.py — .skills/skills/ → .workbuddy/skills/ 单向镜像.

背景: WorkBuddy 只扫描 ``.workbuddy/skills/``, 且本机 junction 全部受阻,
无法像 .trae/.opencode 那样只留一份权威文件 — 只能实体拷贝 (cp -r)。
本脚本把拷贝过程脚本化, 防止 "改了 .skills 忘了同步 WorkBuddy" 的漂移。

行为
----
- 默认: 单向镜像 (创建缺失 + 覆盖内容不一致的文件), 只增不删;
  目标侧多出的目录 (如 WorkBuddy 专属 gaf-architecture-review) 保持不动并汇报。
- --check: 只报告漂移, 不写盘; 有漂移时退出码 1 (供钩子/CI 使用)。
- --prune: 在镜像基础上删除目标侧的多余文件/目录 (受保护名单除外)。

用法
----
    python scripts/sync_workbuddy_skills.py            # 应用镜像
    python scripts/sync_workbuddy_skills.py --check    # 仅检测漂移
    python scripts/sync_workbuddy_skills.py --prune    # 镜像 + 清理多余

退出码
------
    0 - 无漂移或已成功同步
    1 - (--check) 存在漂移
    2 - 环境错误 (源/目标根目录缺失)
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / ".skills" / "skills"
DEST = REPO_ROOT / ".workbuddy" / "skills"

# 目标侧受保护目录: 不属于 .skills/skills/ 权威源、随 prune 保留的本地专属技能。
PROTECTED_DIRS = {"gaf-architecture-review"}


def tree_files(root: Path) -> dict[str, Path]:
    """返回 root 下全部文件的 {posix 相对路径: 绝对路径}。"""
    return {
        p.relative_to(root).as_posix(): p
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_drift(
    src: dict[str, Path], dst: dict[str, Path]
) -> tuple[list[str], list[str], list[str]]:
    """返回 (created, updated, deleted) — 均为 posix 相对路径列表。"""
    created = sorted(set(src) - set(dst))
    updated = sorted(
        key
        for key in set(src) & set(dst)
        if hash_file(src[key]) != hash_file(dst[key])
    )
    deleted = sorted(set(dst) - set(src))
    return created, updated, deleted


def apply_mirror(
    src: dict[str, Path],
    dst: dict[str, Path],
    created: list[str],
    updated: list[str],
) -> int:
    count = 0
    for rel in created + updated:
        target = dst[rel] if rel in dst else DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src[rel], target)
        count += 1
    return count


def prune_stale(
    deleted: list[str], dst: dict[str, Path]
) -> tuple[int, list[str]]:
    """删除目标侧多余文件 (受保护目录内除外), 返回 (删除数, 保留的保护目录)。"""
    removed = 0
    kept_protected: set[str] = set()
    for rel in deleted:
        top = rel.split("/", 1)[0]
        if top in PROTECTED_DIRS:
            kept_protected.add(top)
            continue
        (DEST / rel).unlink()
        removed += 1
    # 清理因删除而变空的目录 (受保护目录除外)。
    for dirpath in sorted(
        (p for p in DEST.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        top = dirpath.relative_to(DEST).parts[0]
        if top in PROTECTED_DIRS:
            continue
        if not any(dirpath.iterdir()):
            dirpath.rmdir()
    return removed, sorted(kept_protected)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=".skills/skills -> .workbuddy/skills 单向镜像",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只报告漂移, 不写盘; 有漂移时退出码 1",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="镜像后删除目标侧多余文件/目录 (PROTECTED_DIRS 除外)",
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"[sync] 源目录不存在: {SOURCE}")
        return 2
    DEST.mkdir(parents=True, exist_ok=True)

    created, updated, deleted = compute_drift(
        tree_files(SOURCE), tree_files(DEST)
    )
    # 受保护目录 (WorkBuddy 专属技能) 不属于权威源, 其文件天然 "在源中不存在",
    # 不算漂移 — 从 deleted 中剔除并单独汇报。
    stale = [
        rel
        for rel in deleted
        if rel.split("/", 1)[0] not in PROTECTED_DIRS
    ]
    protected_extra = sorted(
        {rel.split("/", 1)[0] for rel in deleted} & PROTECTED_DIRS
    )

    if args.check:
        if created or updated or stale:
            print(
                f"[sync] drift: created={len(created)} "
                f"updated={len(updated)} deleted={len(stale)}"
            )
            for label, items in (
                ("created", created),
                ("updated", updated),
                ("deleted", stale),
            ):
                for rel in items:
                    print(f"  [{label}] {rel}")
            return 1
        extra_note = (
            f" (protected extra: {', '.join(protected_extra)})"
            if protected_extra
            else ""
        )
        print(f"[sync] OK: .workbuddy/skills 与 .skills/skills 一致{extra_note}")
        return 0

    written = apply_mirror(
        tree_files(SOURCE), tree_files(DEST), created, updated
    )
    removed = 0
    if args.prune and stale:
        removed, kept = prune_stale(stale, tree_files(DEST))
        if kept:
            print(f"[sync] 保留受保护目录: {', '.join(kept)}")
    if protected_extra:
        print(f"[sync] 保留受保护目录: {', '.join(protected_extra)}")
    print(
        f"[sync] done: created={len(created)} updated={len(updated)} "
        f"removed={removed} (written={written})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
