"""上下文压缩 — 把历史回合压成摘要，在恢复后注入。"""
from __future__ import annotations

from .models import RoundRecord


def compress_rounds(rounds: list[RoundRecord]) -> str:
    if not rounds:
        return ""
    parts: list[str] = []
    for r in rounds:
        elim = "、".join(r.eliminated_this_round) if r.eliminated_this_round else "无淘汰"
        scores_str = "\n".join(f"  {mid}: {s}分" for mid, s in r.scores.items())
        parts.append(
            f"[第{r.round + 1}轮] 问题: {r.question[:80]}...\n"
            f"淘汰: {elim}\n"
            f"裁判点评: {r.judge_comment[:100]}...\n"
            f"分数:\n{scores_str}"
        )
    return "\n---\n".join(parts)


def build_restore_context(compressed: str, last_round: RoundRecord | None) -> str:
    """构造恢复提示。"""
    parts: list[str] = []
    if compressed:
        parts.append("【历史回合摘要】\n" + compressed)
    if last_round:
        parts.append(
            f"\n【上一轮回顾】\n问题: {last_round.question}\n"
            f"裁判点评: {last_round.judge_comment}"
        )
    parts.append("\n请继续遵守比赛规则，参加下一轮。")
    return "\n".join(parts)
