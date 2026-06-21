"""JSON 持久化层（替代原 localStorage）。

在 Android 上 Flet 运行时，使用 `app_storage_path`（应用私有目录）作为根。
桌面端使用用户目录。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from .models import (
    AIConfig, ApiKeyConfig, GameRule, GameSnapshot, RoundRecord,
    ApiType,
)

logger = logging.getLogger(__name__)


class Storage:
    """统一的 JSON 存储管理器。

    线程安全：所有读写通过自带的 `RLock` 串行化。
    """

    def __init__(self, base_dir: str | Path):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.api_keys_file = self.base / "api_keys.json"
        self.competitors_file = self.base / "competitors.json"
        self.judge_file = self.base / "judge_model.json"
        self.rule_file = self.base / "game_rule.json"
        self.arena_state_file = self.base / "arena_state.json"
        self.snapshots_file = self.base / "snapshots.json"
        self.rounds_file = self.base / "rounds.json"
        self.scores_file = self.base / "total_scores.json"
        # 简单锁：保护所有 JSON 写入的原子性
        self._lock = threading.RLock()

    # ─── 通用读写 ───

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取 JSON 失败 %s: %s — 返回默认值", path, e)
                return default

    def _write_json(self, path: Path, data: Any) -> None:
        with self._lock:
            tmp = path.with_suffix(path.suffix + ".tmp")
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                tmp.replace(path)
                # Linux/Android 上收紧文件权限（仅所有者可读写）
                self._restrict_perm(path)
            except OSError as e:
                logger.error("写入 JSON 失败 %s: %s", path, e)
                raise

    @staticmethod
    def _restrict_perm(path: Path) -> None:
        """在 Unix 系（Linux/macOS/Android）上设置 0600 权限。Windows 跳过。"""
        if os.name != "posix":
            return
        try:
            os.chmod(path, 0o600)
        except OSError as e:
            logger.debug("设置 0600 权限失败 %s: %s", path, e)

    # ─── API Keys ───

    def load_api_keys(self) -> list[ApiKeyConfig]:
        data = self._read_json(self.api_keys_file, [])
        return [ApiKeyConfig.from_dict(d) for d in data]

    def save_api_keys(self, keys: list[ApiKeyConfig]) -> None:
        self._write_json(self.api_keys_file, [k.to_dict() for k in keys])

    def get_api_key(self, api_type: ApiType) -> ApiKeyConfig | None:
        for k in self.load_api_keys():
            if k.api_type == api_type:
                return k
        return None

    def upsert_api_key(self, key: ApiKeyConfig) -> None:
        keys = self.load_api_keys()
        for i, k in enumerate(keys):
            if k.api_type == key.api_type:
                keys[i] = key
                break
        else:
            keys.append(key)
        self.save_api_keys(keys)

    def delete_api_key(self, api_type: ApiType) -> None:
        keys = [k for k in self.load_api_keys() if k.api_type != api_type]
        self.save_api_keys(keys)

    # ─── Competitors / Judge ───

    def load_competitors(self) -> list[AIConfig]:
        data = self._read_json(self.competitors_file, [])
        return [AIConfig.from_dict(d) for d in data]

    def save_competitors(self, items: list[AIConfig]) -> None:
        self._write_json(self.competitors_file, [c.to_dict() for c in items])

    def load_judge(self) -> AIConfig | None:
        d = self._read_json(self.judge_file, None)
        return AIConfig.from_dict(d) if d else None

    def save_judge(self, judge: AIConfig | None) -> None:
        self._write_json(self.judge_file, judge.to_dict() if judge else None)

    # ─── Rule ───

    def load_rule(self) -> GameRule | None:
        d = self._read_json(self.rule_file, None)
        return GameRule.from_dict(d) if d else None

    def save_rule(self, rule: GameRule) -> None:
        self._write_json(self.rule_file, rule.to_dict())

    # ─── Arena 状态（每轮临时数据） ───

    def load_arena_state(self) -> dict:
        return self._read_json(self.arena_state_file, {})

    def save_arena_state(self, state: dict) -> None:
        self._write_json(self.arena_state_file, state)

    # ─── Rounds / Scores ───

    def load_rounds(self) -> list[RoundRecord]:
        data = self._read_json(self.rounds_file, [])
        return [RoundRecord.from_dict(d) for d in data]

    def save_rounds(self, rounds: list[RoundRecord]) -> None:
        self._write_json(self.rounds_file, [r.to_dict() for r in rounds])

    def load_scores(self) -> dict[str, int]:
        return self._read_json(self.scores_file, {})

    def save_scores(self, scores: dict[str, int]) -> None:
        self._write_json(self.scores_file, scores)

    # ─── Snapshots ───

    def load_snapshots(self) -> list[GameSnapshot]:
        data = self._read_json(self.snapshots_file, [])
        return [GameSnapshot.from_dict(d) for d in data]

    def save_snapshots(self, snaps: list[GameSnapshot]) -> None:
        self._write_json(self.snapshots_file, [s.to_dict() for s in snaps])

    def add_snapshot(self, snap: GameSnapshot) -> None:
        snaps = self.load_snapshots()
        snaps.append(snap)
        self.save_snapshots(snaps)

    def delete_snapshot(self, snap_id: str) -> None:
        snaps = [s for s in self.load_snapshots() if s.id != snap_id]
        self.save_snapshots(snaps)

