"""竞技场状态机（对应原 arenaStore.ts）。

为兼容 Flet 的响应式机制，状态以 dataclass 形式持有，
并通过 `ArenaState.notify()` 触发 Page.update()。
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .models import (
    AIConfig, ChatMessage, GamePhase, GameRule, GameSnapshot,
    GameStatus, ModelStatus, PrivateChat, PublicMessage, RoundRecord,
    create_default_rule, gen_id, pick_color, pick_icon, ApiType,
)
from .storage import Storage


MAX_COMPETITORS = 24


@dataclass
class ArenaState:
    """竞技场运行时状态。"""

    status: GameStatus = GameStatus.IDLE
    phase: GamePhase = GamePhase.IDLE
    round: int = 0
    game_rule: GameRule = field(default_factory=create_default_rule)
    question: str = ""
    competitors: list[AIConfig] = field(default_factory=list)
    judge_model: Optional[AIConfig] = None
    answers: dict[str, str] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    judge_comment: str = ""
    total_scores: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    round_history: list[RoundRecord] = field(default_factory=list)
    private_chats: list[PrivateChat] = field(default_factory=list)
    public_messages: list[PublicMessage] = field(default_factory=list)
    eliminated_models: list[str] = field(default_factory=list)
    current_conversation_id: Optional[str] = None
    elimination_reasons: dict[str, str] = field(default_factory=dict)

    # ─── 通知回调（由 Flet page 注册） ───
    _on_change: Optional[Callable[[], None]] = None
    storage: Optional[Storage] = None

    # ─── 通知机制 ───

    def bind_storage(self, storage: Storage) -> None:
        self.storage = storage
        self._hydrate()

    def _hydrate(self) -> None:
        """从存储中恢复数据。"""
        if self.storage is None:
            return
        self.competitors = self.storage.load_competitors()
        self.judge_model = self.storage.load_judge()
        rule = self.storage.load_rule()
        if rule:
            self.game_rule = rule
        self.round_history = self.storage.load_rounds()
        self.total_scores = self.storage.load_scores()
        aria = self.storage.load_arena_state()
        if aria:
            self.eliminated_models = list(aria.get("eliminated_models", []))
            self.elimination_reasons = dict(aria.get("elimination_reasons", {}))
            if "round" in aria:
                self.round = int(aria["round"])

    def on_change(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    def notify(self) -> None:
        if self._on_change:
            self._on_change()

    # ─── 持久化辅助 ───

    def _save_persistent(self) -> None:
        if not self.storage:
            return
        self.storage.save_competitors(self.competitors)
        self.storage.save_judge(self.judge_model)
        self.storage.save_rule(self.game_rule)
        self.storage.save_rounds(self.round_history)
        self.storage.save_scores(self.total_scores)
        self.storage.save_arena_state({
            "eliminated_models": self.eliminated_models,
            "elimination_reasons": self.elimination_reasons,
            "round": self.round,
        })

    # ─── 基础 setter ───

    def set_status(self, status: GameStatus) -> None:
        self.status = status
        self.notify()

    def set_phase(self, phase: GamePhase) -> None:
        self.phase = phase
        self.notify()

    def set_question(self, q: str) -> None:
        self.question = q
        self.notify()

    def set_error(self, e: Optional[str]) -> None:
        self.error = e
        self.notify()

    def set_judge_comment(self, c: str) -> None:
        self.judge_comment = c
        self.notify()

    def set_rule(self, rule: GameRule) -> None:
        self.game_rule = rule
        if self.storage:
            self.storage.save_rule(rule)
        self.notify()

    # ─── 选手管理 ───

    def add_competitor(self, draft: AIConfig) -> AIConfig:
        if len(self.competitors) >= MAX_COMPETITORS:
            return draft
        # 去重：同 (api_type, model_name) 不重复添加
        if any(
            c.api_type == draft.api_type and c.model_name == draft.model_name
            for c in self.competitors
        ):
            return draft
        idx = len(self.competitors)
        c = AIConfig(
            id=gen_id(),
            name=draft.name,
            api_type=draft.api_type,
            endpoint=draft.endpoint,
            api_key=draft.api_key,
            model_name=draft.model_name,
            color=draft.color or pick_color(idx),
            icon=draft.icon or pick_icon(idx),
            run_status=ModelStatus.ACTIVE,
        )
        self.competitors.append(c)
        self._save_persistent()
        self.notify()
        return c

    def remove_competitor(self, cid: str) -> None:
        self.competitors = [c for c in self.competitors if c.id != cid]
        if self.judge_model and self.judge_model.id == cid:
            self.judge_model = None
        self._save_persistent()
        self.notify()

    def update_competitor(self, cid: str, updates: dict) -> None:
        for i, c in enumerate(self.competitors):
            if c.id == cid:
                for k, v in updates.items():
                    setattr(self.competitors[i], k, v)
                break
        if self.judge_model and self.judge_model.id == cid:
            for k, v in updates.items():
                setattr(self.judge_model, k, v)
        self._save_persistent()
        self.notify()

    def set_judge_model(self, comp: AIConfig) -> None:
        """把一个现有的 competitor 提升为裁判。"""
        if comp.id not in [c.id for c in self.competitors]:
            return
        self.judge_model = copy.deepcopy(comp)
        self.judge_model.run_status = ModelStatus.ACTIVE
        self.competitors = [c for c in self.competitors if c.id != comp.id]
        self._save_persistent()
        self.notify()

    def clear_judge(self) -> None:
        if self.judge_model:
            # 恢复为普通选手
            self.competitors.append(self.judge_model)
        self.judge_model = None
        self._save_persistent()
        self.notify()

    # ─── 模型状态 ───

    def update_model_status(self, mid: str, status: ModelStatus, error: Optional[str] = None) -> None:
        # 修复 M8：未命中 mid 时不再盲目写盘 + notify，避免无谓 I/O 和 UI 闪屏
        found = False
        for c in self.competitors:
            if c.id == mid:
                c.run_status = status
                c.last_error = error
                found = True
                break
        if self.judge_model and self.judge_model.id == mid:
            self.judge_model.run_status = status
            self.judge_model.last_error = error
            found = True
        if not found:
            return
        self._save_persistent()
        self.notify()

    # ─── 私人对话 ───

    def init_private_chats(self, competitor_ids: list[str]) -> None:
        self.private_chats = [
            PrivateChat(competitor_id=cid, messages=[], is_active=True)
            for cid in competitor_ids
        ]
        self.notify()

    def add_private_message(self, cid: str, message: ChatMessage) -> None:
        for chat in self.private_chats:
            if chat.competitor_id == cid:
                chat.messages.append(message)
                break
        self.notify()

    def set_conversation_active(self, cid: str, active: bool) -> None:
        for chat in self.private_chats:
            if chat.competitor_id == cid:
                chat.is_active = active
                break
        self.notify()

    def set_current_conversation_id(self, cid: Optional[str]) -> None:
        self.current_conversation_id = cid
        self.notify()

    # ─── 淘汰 ───

    def eliminate_models(self, ids: list[str], reasons: dict[str, str]) -> None:
        for mid in ids:
            if mid not in self.eliminated_models:
                self.eliminated_models.append(mid)
        self.elimination_reasons.update(reasons)
        for c in self.competitors:
            if c.id in ids:
                c.run_status = ModelStatus.ELIMINATED
        for chat in self.private_chats:
            if chat.competitor_id in ids:
                chat.is_active = False
        self._save_persistent()
        self.notify()

    # ─── 公共发言 ───

    def add_public_message(self, msg: PublicMessage) -> None:
        self.public_messages.append(msg)
        self.notify()

    def clear_public_messages(self) -> None:
        self.public_messages = []
        self.notify()

    # ─── 回合记录 ───

    def add_round_record(self, record: RoundRecord) -> None:
        self.round_history.append(record)
        if self.storage:
            self.storage.save_rounds(self.round_history)
        self.notify()

    def set_scores(self, scores: dict[str, int]) -> None:
        for mid, s in scores.items():
            self.total_scores[mid] = self.total_scores.get(mid, 0) + s
        self.scores = dict(scores)
        if self.storage:
            self.storage.save_scores(self.total_scores)
        self.notify()

    # ─── 回合开始 / 推进 ───

    def start_round(self) -> bool:
        # 暂停状态下必须先恢复，不能直接开始新的一轮
        if self.status == GameStatus.PAUSED:
            self.error = "游戏已暂停，请先恢复"
            self.notify()
            return False
        survivors = self.get_survivors()
        if len(survivors) < 2:
            self.error = "至少需要 2 个存活参赛模型"
            self.notify()
            return False
        if not self.judge_model or self.judge_model.run_status != ModelStatus.ACTIVE:
            self.error = "请先设置活跃的裁判模型"
            self.notify()
            return False
        if not self.question.strip():
            self.error = "请输入本轮问题"
            self.notify()
            return False
        if self.round >= self.game_rule.max_rounds:
            self.error = "已达到最大轮次"
            self.notify()
            return False
        self.status = GameStatus.LOADING
        self.phase = GamePhase.JUDGE_READING_RULES
        self.answers = {}
        self.scores = {}
        self.judge_comment = ""
        self.error = None
        self.private_chats = []
        self.public_messages = []
        self.current_conversation_id = None
        self.notify()
        return True

    def next_round(self) -> None:
        survivors = self.get_survivors()
        if len(survivors) <= 1:
            self.status = GameStatus.FINISHED
            self.phase = GamePhase.GAME_OVER
        elif self.round + 1 >= self.game_rule.max_rounds:
            self.status = GameStatus.FINISHED
            self.phase = GamePhase.GAME_OVER
            self.round += 1
        else:
            self.round += 1
            self.status = GameStatus.IDLE
            self.phase = GamePhase.IDLE
            self.question = ""
            self.private_chats = []
            self.public_messages = []
        self.notify()

    def reset_game(self) -> None:
        self.status = GameStatus.IDLE
        self.phase = GamePhase.IDLE
        self.round = 0
        self.question = ""
        self.answers = {}
        self.scores = {}
        self.judge_comment = ""
        self.total_scores = {}
        self.round_history = []
        self.error = None
        self.private_chats = []
        self.public_messages = []
        self.eliminated_models = []
        self.current_conversation_id = None
        self.elimination_reasons = {}
        if self.storage:
            self.storage.save_scores({})
            self.storage.save_rounds([])
        self.notify()

    # ─── 查询辅助 ───

    def get_survivors(self) -> list[AIConfig]:
        return [
            c for c in self.competitors
            if c.run_status == ModelStatus.ACTIVE
            and c.id not in self.eliminated_models
        ]

    def get_eliminated(self) -> list[AIConfig]:
        return [
            c for c in self.competitors
            if c.run_status == ModelStatus.ELIMINATED or c.id in self.eliminated_models
        ]
