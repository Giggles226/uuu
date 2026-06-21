"""快照 — 对应原 arenaStore 的 createSnapshot / restoreSnapshot / pauseGame / resumeGame。"""
from __future__ import annotations

import copy
import time
from typing import Optional

from .models import (
    AIConfig, GameSnapshot, GameStatus, ModelStatus, gen_snap_id,
)
from .state import ArenaState
from .compression import compress_rounds
from .storage import Storage


def create_snapshot(state: ArenaState, label: str) -> GameSnapshot:
    snap = GameSnapshot(
        id=gen_snap_id(),
        created_at=int(time.time() * 1000),
        label=label,
        competitors=copy.deepcopy(state.competitors),
        judge_model=copy.deepcopy(state.judge_model) if state.judge_model else None,
        game_rule=copy.deepcopy(state.game_rule),
        rounds=copy.deepcopy(state.round_history),
        total_scores=dict(state.total_scores),
        current_round=state.round,
        compressed_summary=compress_rounds(state.round_history),
        paused_model_id=None,
        paused_reason="",
        eliminated_models=list(state.eliminated_models),
    )
    if state.storage:
        state.storage.add_snapshot(snap)
    return snap


def pause_game(state: ArenaState, paused_model_id: str, reason: str) -> GameSnapshot:
    """自动暂停：先保存快照，然后标记状态。"""
    snap = GameSnapshot(
        id=gen_snap_id(),
        created_at=int(time.time() * 1000),
        label=f"自动暂停 - {time.strftime('%H:%M:%S')}",
        competitors=copy.deepcopy(state.competitors),
        judge_model=copy.deepcopy(state.judge_model) if state.judge_model else None,
        game_rule=copy.deepcopy(state.game_rule),
        rounds=copy.deepcopy(state.round_history),
        total_scores=dict(state.total_scores),
        current_round=state.round,
        compressed_summary=compress_rounds(state.round_history),
        paused_model_id=paused_model_id,
        paused_reason=reason,
        eliminated_models=list(state.eliminated_models),
    )
    if state.storage:
        state.storage.add_snapshot(snap)
    state.status = GameStatus.PAUSED
    state.phase = state.phase  # 保留当前 phase
    state.error = reason
    state.notify()
    return snap


def restore_snapshot(state: ArenaState, snap: GameSnapshot) -> None:
    """从快照恢复。"""
    state.competitors = copy.deepcopy(snap.competitors)
    state.judge_model = copy.deepcopy(snap.judge_model) if snap.judge_model else None
    state.game_rule = copy.deepcopy(snap.game_rule)
    state.round_history = copy.deepcopy(snap.rounds)
    state.total_scores = dict(snap.total_scores)
    state.round = snap.current_round
    state.status = GameStatus.IDLE
    state.phase = state.phase.__class__.IDLE if hasattr(state.phase, '__class__') else state.phase
    state.question = ""
    state.answers = {}
    state.scores = {}
    state.judge_comment = ""
    state.error = None
    state.private_chats = []
    state.public_messages = []
    state.eliminated_models = list(snap.eliminated_models)
    state.current_conversation_id = None
    state.elimination_reasons = {}
    state._save_persistent()
    state.notify()


def resume_game(state: ArenaState) -> Optional[GameSnapshot]:
    """从最新快照恢复。"""
    if not state.storage:
        return None
    snaps = state.storage.load_snapshots()
    if not snaps:
        return None
    latest = snaps[-1]
    # 把所有 runStatus 重置为 active
    state.competitors = [
        AIConfig(
            id=c.id, name=c.name, api_type=c.api_type, endpoint=c.endpoint,
            api_key=c.api_key, model_name=c.model_name, color=c.color,
            icon=c.icon, run_status=ModelStatus.ACTIVE, last_error=None,
        )
        for c in latest.competitors
    ]
    if latest.judge_model:
        j = latest.judge_model
        state.judge_model = AIConfig(
            id=j.id, name=j.name, api_type=j.api_type, endpoint=j.endpoint,
            api_key=j.api_key, model_name=j.model_name, color=j.color,
            icon=j.icon, run_status=ModelStatus.ACTIVE, last_error=None,
        )
    else:
        state.judge_model = None
    state.game_rule = copy.deepcopy(latest.game_rule)
    state.round_history = copy.deepcopy(latest.rounds)
    state.total_scores = dict(latest.total_scores)
    state.round = latest.current_round
    state.status = GameStatus.IDLE
    state.phase = state.phase.__class__.IDLE if hasattr(state.phase, '__class__') else state.phase
    state.question = ""
    state.answers = {}
    state.scores = {}
    state.judge_comment = ""
    state.error = None
    state.private_chats = []
    state.public_messages = []
    state.eliminated_models = list(latest.eliminated_models)
    state.current_conversation_id = None
    state.elimination_reasons = {}
    state._save_persistent()
    state.notify()
    return latest
