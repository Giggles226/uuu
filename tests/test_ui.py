"""UI smoke test — 验证所有 UI 构建函数能用 mock page 调用而不抛错。"""
from __future__ import annotations

import sys
import tempfile
import shutil
from unittest.mock import MagicMock

# 必须在 import flet 之前先给 Flet 一个 fake page（避免需要 display）
import flet as ft


class FakePage:
    """模拟 Flet Page，供 UI 构建函数调用所需的最少 API。"""

    def __init__(self):
        self.overlay = []
        self.controls = []
        self._update_count = 0

    def update(self):
        self._update_count += 1


def test_imports():
    """所有 UI 模块能完整导入。"""
    from ui import arena_view, config_panel, rule_editor, snapshot_panel, utils
    print("✓ test_imports")


def test_config_panel_builds():
    """build_config_panel 应能用 mock page 构建且不抛错。"""
    from arena.models import ApiType, AIConfig, pick_color, pick_icon
    from arena.state import ArenaState
    from arena.storage import Storage
    from ui.config_panel import build_config_panel

    tmp = tempfile.mkdtemp()
    try:
        page = FakePage()
        storage = Storage(tmp)
        state = ArenaState()
        state.bind_storage(storage)

        # 预填一个选手，确保 UI 渲染
        state.add_competitor(AIConfig(
            id="", name="Test", api_type=ApiType.OPENAI,
            endpoint="", api_key="", model_name="gpt-4o",
            color=pick_color(0), icon=pick_icon(0),
        ))

        refresh_count = {"n": 0}
        def on_change():
            refresh_count["n"] += 1

        panel = build_config_panel(page, state, on_change)
        assert panel is not None
        # overlay 里应该至少有 edit_dlg + api_dlg + mgr_dlg 三个 dialog
        assert len(page.overlay) >= 3, f"应注册到 overlay 的 dialog 数不足: {len(page.overlay)}"
        # 至少调用过一次 on_change
        assert refresh_count["n"] >= 1, "on_change 回调未被触发"
        # 至少调用过一次 page.update
        assert page._update_count >= 1
        print(f"✓ test_config_panel_builds (overlay={len(page.overlay)}, updates={page._update_count}, on_change={refresh_count['n']})")
    finally:
        shutil.rmtree(tmp)


def test_rule_editor_builds():
    from arena.state import ArenaState
    from arena.storage import Storage
    from ui.rule_editor import build_rule_editor

    tmp = tempfile.mkdtemp()
    try:
        page = FakePage()
        storage = Storage(tmp)
        state = ArenaState()
        state.bind_storage(storage)

        editor = build_rule_editor(state, on_save=lambda: None)
        assert editor is not None
        print("✓ test_rule_editor_builds")
    finally:
        shutil.rmtree(tmp)


def test_snapshot_panel_builds():
    from arena.state import ArenaState
    from arena.storage import Storage
    from ui.snapshot_panel import build_snapshot_panel

    tmp = tempfile.mkdtemp()
    try:
        page = FakePage()
        storage = Storage(tmp)
        state = ArenaState()
        state.bind_storage(storage)

        panel = build_snapshot_panel(state, on_change=lambda: None)
        assert panel is not None
        print("✓ test_snapshot_panel_builds")
    finally:
        shutil.rmtree(tmp)


def test_arena_view_builds():
    from arena.state import ArenaState
    from arena.storage import Storage
    from ui.arena_view import build_arena_view

    tmp = tempfile.mkdtemp()
    try:
        page = FakePage()
        storage = Storage(tmp)
        state = ArenaState()
        state.bind_storage(storage)

        view = build_arena_view(page, state)
        assert view is not None
        print("✓ test_arena_view_builds")
    finally:
        shutil.rmtree(tmp)


def test_on_change_propagation():
    """修复 #2：选手增删应触发 on_change 回调（UI 才会刷新）。"""
    from arena.models import AIConfig, ApiType, pick_color, pick_icon
    from arena.state import ArenaState
    from arena.storage import Storage
    from ui.config_panel import build_config_panel

    tmp = tempfile.mkdtemp()
    try:
        page = FakePage()
        storage = Storage(tmp)
        state = ArenaState()
        state.bind_storage(storage)

        refresh_count = {"n": 0}
        def on_change():
            refresh_count["n"] += 1

        build_config_panel(page, state, on_change)
        before = refresh_count["n"]

        # 添加选手 → 应触发 on_change
        state.add_competitor(AIConfig(
            id="", name="X", api_type=ApiType.OPENAI,
            endpoint="", api_key="", model_name="x1",
            color=pick_color(0), icon=pick_icon(0),
        ))
        after_add = refresh_count["n"]
        assert after_add > before, "添加选手后 on_change 未被触发"

        # 删除选手 → 也应触发
        cid = state.competitors[0].id
        state.remove_competitor(cid)
        after_remove = refresh_count["n"]
        assert after_remove > after_add, "删除选手后 on_change 未被触发"
        print(f"✓ test_on_change_propagation (add={after_add-before}, remove={after_remove-after_add})")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    test_imports()
    test_config_panel_builds()
    test_rule_editor_builds()
    test_snapshot_panel_builds()
    test_arena_view_builds()
    test_on_change_propagation()
    print()
    print("=== ALL UI SMOKE TESTS PASSED ===")
