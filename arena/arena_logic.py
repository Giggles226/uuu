"""竞技场主循环 — 编排各阶段（阅读规则 → 私人对话 → 淘汰判定 → 公共发言 → 回合结束）。"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from . import judge as judge_mod
from .compression import compress_rounds
from .models import (
    AIConfig, ChatMessage, GamePhase, GameStatus, ModelStatus,
    PublicMessage, RoundRecord, gen_msg_id,
)
from .snapshot import create_snapshot, pause_game
from .state import ArenaState


PHASE_LABELS: dict[GamePhase, str] = {
    GamePhase.IDLE: "待开始",
    GamePhase.JUDGE_READING_RULES: "📖 裁判正在阅读规则...",
    GamePhase.PRIVATE_CONVERSATIONS: "💬 裁判正在与模型进行私人对话...",
    GamePhase.JUDGE_DELIBERATION: "⚖️ 裁判正在做出淘汰判定...",
    GamePhase.PUBLIC_ANNOUNCEMENT: "📢 裁判正在公开宣布结果...",
    GamePhase.ROUND_END: "✅ 本轮结束",
    GamePhase.PAUSED: "⏸️ 已暂停",
    GamePhase.GAME_OVER: "🏁 游戏结束",
}


class ArenaRunner:
    """单实例驱动器。负责一轮的状态机推进。"""

    def __init__(self, state: ArenaState):
        self.state = state
        self._is_running = False
        self._round_processed = False
        self._eliminated_before_round: list[str] = []

    def is_running(self) -> bool:
        return self._is_running

    def get_phase_label(self) -> str:
        return PHASE_LABELS.get(self.state.phase, str(self.state.phase))

    def start_round(self) -> bool:
        if self._is_running:
            return False
        ok = self.state.start_round()
        if not ok:
            return False
        self._round_processed = False
        self._eliminated_before_round = list(self.state.eliminated_models)
        return True

    async def tick(self) -> None:
        """主推进函数 — 由 UI 在 async 任务里循环调用。"""
        if self.state.status != GameStatus.LOADING:
            return
        if self._is_running:
            return

        self._is_running = True
        try:
            survivors = self.state.get_survivors()
            if len(survivors) < 2 and self.state.phase not in (
                GamePhase.ROUND_END, GamePhase.GAME_OVER,
            ):
                self.state.set_phase(GamePhase.ROUND_END)
                self.state.set_status(GameStatus.FINISHED)
                return

            if self.state.phase == GamePhase.JUDGE_READING_RULES:
                await asyncio.sleep(0.5)
                self.state.set_phase(GamePhase.PRIVATE_CONVERSATIONS)
                self.state.init_private_chats([s.id for s in survivors])
                return

            if self.state.phase == GamePhase.PRIVATE_CONVERSATIONS:
                await self._run_private_conversations(survivors)
                return

            if self.state.phase == GamePhase.JUDGE_DELIBERATION:
                await self._run_deliberation(survivors)
                return

            if self.state.phase == GamePhase.PUBLIC_ANNOUNCEMENT:
                await self._run_public_announcement(survivors)
                return

            if self.state.phase == GamePhase.ROUND_END:
                await self._finalize_round(survivors)
                return

        except Exception as e:  # noqa: BLE001
            self.state.set_status(GameStatus.IDLE)
            self.state.set_phase(GamePhase.IDLE)
            self.state.set_error(str(e))
        finally:
            self._is_running = False

    # ─── 私人对话阶段 ───

    async def _run_private_conversations(self, survivors: list[AIConfig]) -> None:
        chats = self.state.private_chats
        all_done = all((not c.is_active) for c in chats)
        if all_done:
            self.state.set_phase(GamePhase.JUDGE_DELIBERATION)
            return

        next_survivor: Optional[AIConfig] = None
        for s in survivors:
            chat = next((c for c in chats if c.competitor_id == s.id), None)
            if chat and chat.is_active:
                next_survivor = s
                break

        if next_survivor is None:
            self.state.set_phase(GamePhase.JUDGE_DELIBERATION)
            return

        self.state.set_current_conversation_id(next_survivor.id)
        chat = next(c for c in chats if c.competitor_id == next_survivor.id)
        existing: list[ChatMessage] = chat.messages
        turn_index = sum(1 for m in existing if m.role == "judge")
        max_turns = self.state.game_rule.max_private_turns or 3

        result = await judge_mod.judge_agent_private_chat(
            self.state.judge_model,
            next_survivor,
            self.state.game_rule,
            self.state.question,
            existing,
            turn_index,
            self.state,
        )

        now = int(time.time() * 1000)
        self.state.add_private_message(
            next_survivor.id,
            ChatMessage(
                id=gen_msg_id(), role="judge",
                content=result["judge_message"], timestamp=now,
            ),
        )
        self.state.add_private_message(
            next_survivor.id,
            ChatMessage(
                id=gen_msg_id(), role="competitor",
                content=result["competitor_response"], timestamp=now + 1,
            ),
        )

        if result["should_eliminate"]:
            self.state.eliminate_models(
                [next_survivor.id],
                {next_survivor.id: result["eliminate_reason"] or "裁判判定淘汰"},
            )

        if (
            result["is_conversation_end"]
            or result["should_eliminate"]
            or turn_index + 1 >= max_turns
        ):
            self.state.set_conversation_active(next_survivor.id, False)

        self.state.set_current_conversation_id(None)
        await asyncio.sleep(0.3)

    # ─── 淘汰判定阶段 ───

    async def _run_deliberation(self, survivors: list[AIConfig]) -> None:
        chat_summaries = []
        for chat in self.state.private_chats:
            comp = next((c for c in self.state.competitors if c.id == chat.competitor_id), None)
            chat_summaries.append({
                "competitor_id": chat.competitor_id,
                "competitor_name": comp.name if comp else chat.competitor_id,
                "messages": [{"role": m.role, "content": m.content} for m in chat.messages],
            })

        result = await judge_mod.judge_agent_deliberate(
            self.state.judge_model,
            self.state.game_rule,
            survivors,
            list(self.state.eliminated_models),
            chat_summaries,
            self.state.question,
            self.state.round,
            self.state,
        )

        if result["eliminated_this_round"]:
            self.state.eliminate_models(
                result["eliminated_this_round"],
                result["elimination_reasons"],
            )

        self.state.set_judge_comment(result["deliberation_comment"])
        self.state.set_phase(GamePhase.PUBLIC_ANNOUNCEMENT)

    # ─── 公共发言阶段 ───

    async def _run_public_announcement(self, survivors: list[AIConfig]) -> None:
        eliminated_this_round = [
            mid for mid in self.state.eliminated_models
            if mid not in self._eliminated_before_round
        ]
        announcement = await judge_mod.judge_agent_public_announce(
            self.state.judge_model,
            self.state.game_rule,
            survivors,
            list(self.state.competitors),
            list(self.state.eliminated_models),
            eliminated_this_round,
            dict(self.state.elimination_reasons),
            self.state.question,
            self.state.round,
            self.state,
        )

        msg = judge_mod.make_public_announcement(self.state.judge_model, announcement)
        self.state.add_public_message(msg)
        self.state.set_phase(GamePhase.ROUND_END)

    # ─── 回合收尾 ───

    async def _finalize_round(self, _survivors: list[AIConfig]) -> None:
        if self._round_processed:
            return
        self._round_processed = True

        # 检查活跃选手数量，<= 1 自动结束
        survivors = self.state.get_survivors()

        # 无论是否 GAME_OVER，都先记录这一轮（修复 M3：之前剩 1 人时直接 return 导致本轮问答丢失）
        record = RoundRecord(
            round=self.state.round,
            question=self.state.question,
            rule_reminder=judge_mod.build_rule_prompt(self.state.game_rule, self.state.question),
            private_chats=list(self.state.private_chats),
            public_messages=list(self.state.public_messages),
            eliminated_this_round=[
                mid for mid in self.state.eliminated_models
                if mid not in self._eliminated_before_round
            ],
            answers=dict(self.state.answers),
            scores=dict(self.state.scores),
            judge_comment=self.state.judge_comment,
            timestamp=int(time.time() * 1000),
        )
        self.state.add_round_record(record)

        if len(survivors) < 2:
            self.state.set_status(GameStatus.FINISHED)
            self.state.set_phase(GamePhase.GAME_OVER)
            return

        # 给存活选手每人 10 分
        new_scores = {s.id: 10 for s in survivors}
        self.state.set_scores(new_scores)
        self.state.set_status(GameStatus.FINISHED)
        self.state.set_phase(GamePhase.ROUND_END)
