"""快照 — 对应原 arenaStore 的 createSnapshot / restoreSnapshot / pauseGame / resumeGame。"""
from __future__ import annotations

import copy
import time
from typing import Optional

from .models import (
    AIConfig, GameSnapshot, GamePhase, GameStatus, ModelStatus, gen_snap_id,
)
from .state import ArenaState
from .compression import compress_rounds


def _build_snapshot(
    state: ArenaState,
    label: str,
    paused_model_id: Optional[str] = None,
    paused_reason: str = "",
) -> GameSnapshot:
    """构造一个完整的快照（内部工具）。"""
    return GameSnapshot(
        id=gen_snap_id(),
        created_at=int(time.time() * 1000),
        label=label,
        competitors=copy.deepcopy(state.competitors),
        judge_model=copy.deepcopy(state.judge_model) if state.judge_model else None,
        game_rule=copy.deepcopy(state.game_rule),
        rounds=copy.deepcopy(state.round_history),
        total_scores=dict(state.total_scores),
        current_round=state.round,
        # 注意：compressed_summary 是创建时刻的快照。之后如果又新增轮次，
        # 不会自动更新。如果要拿最新摘要，请在恢复前重新创建快照。
        compressed_summary=compress_rounds(state.round_history),
        paused_model_id=paused_model_id,
        paused_reason=paused_reason,
        eliminated_models=list(state.eliminated_models),
    )


def create_snapshot(state: ArenaState, label: str) -> GameSnapshot:
    snap = _build_snapshot(state, label)
    if state.storage:
        state.storage.add_snapshot(snap)
    return snap


def pause_game(state: ArenaState, paused_model_id: str, reason: str) -> GameSnapshot:
    """自动暂停：先保存快照，然后标记状态。"""
    snap = _build_snapshot(
        state,
        label=f"自动暂停 - {time.strftime('%H:%M:%S')}",
        paused_model_id=paused_model_id,
        paused_reason=reason,
    )
    if state.storage:
        state.storage.add_snapshot(snap)
    state.status = GameStatus.PAUSED
    # 保留当前 phase
    state.error = reason
    state.notify()
    return snap


def _restore_from_snap(
    state: ArenaState,
    snap: GameSnapshot,
    reset_reasons: bool,
    reset_run_status: bool,
) -> None:
    """从快照恢复内部实现。"""
    if reset_run_status:
        state.competitors = [
            AIConfig(
                id=c.id, name=c.name, api_type=c.api_type, endpoint=c.endpoint,
                api_key=c.api_key, model_name=c.model_name, color=c.color,
                icon=c.icon, run_status=ModelStatus.ACTIVE, last_error=None,
            )
            for c in snap.competitors
        ]
        if snap.judge_model:
            j = snap.judge_model
            state.judge_model = AIConfig(
                id=j.id, name=j.name, api_type=j.api_type, endpoint=j.endpoint,
                api_key=j.api_key, model_name=j.model_name, color=j.color,
                icon=j.icon, run_status=ModelStatus.ACTIVE, last_error=None,
            )
        else:
            state.judge_model = None
    else:
        state.competitors = copy.deepcopy(snap.competitors)
        state.judge_model = copy.deepcopy(snap.judge_model) if snap.judge_model else None

    state.game_rule = copy.deepcopy(snap.game_rule)
    state.round_history = copy.deepcopy(snap.rounds)
    state.total_scores = dict(snap.total_scores)
    state.round = snap.current_round
    state.status = GameStatus.IDLE
    state.phase = GamePhase.IDLE
    state.question = ""
    state.answers = {}
    state.scores = {}
    state.judge_comment = ""
    state.error = None
    state.private_chats = []
    state.public_messages = []
    state.eliminated_models = list(snap.eliminated_models)
    state.current_conversation_id = None
    # 关键修复：恢复时保留快照里的淘汰原因（之前会被错误地重置为 {}）
    if reset_reasons:
        state.elimination_reasons = {}
    else:
        # 仅复制跟 eliminated_models 对应的原因
        state.elimination_reasons = {
            mid: state.elimination_reasons.get(mid, "被淘汰")
            for mid in snap.eliminated_models
        }
    state._save_persistent()
    state.notify()


def restore_snapshot(state: ArenaState, snap: GameSnapshot) -> None:
    """从快照恢复。"""
    _restore_from_snap(state, snap, reset_reasons=True, reset_run_status=False)


def resume_game(state: ArenaState) -> Optional[GameSnapshot]:
    """从最新快照恢复（重置所有 run_status 为 active）。"""
    if not state.storage:
        return None
    snaps = state.storage.load_snapshots()
    if not snaps:
        return None
    latest = snaps[-1]
    _restore_from_snap(state, latest, reset_reasons=False, reset_run_status=True)
    return latest
