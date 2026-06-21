"""Flet 应用入口。

打包为 APK：
    flet build apk

桌面开发：
    python main.py

或在 Flet 应用中：
    flet run main.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import flet as ft

from arena import __version__
from arena.state import ArenaState
from arena.storage import Storage
from ui.arena_view import build_arena_view

logger = logging.getLogger("uuu")


def _resolve_storage_path(page: ft.Page) -> str:
    """选择合适的存储目录。

    - Flet 运行时（桌面 / Android / iOS / Web）：`ft.app_storage_path()` 由 Flet 管理
    - 退路：cwd/storage（开发期手动 `python main.py` 时）
    """
    try:
        return str(ft.app_storage_path())
    except Exception as e:  # noqa: BLE001
        logger.warning("ft.app_storage_path() 不可用，回退到 cwd/storage: %s", e)
        return str(Path.cwd() / "storage")


def main(page: ft.Page):
    page.title = f"AI 酒馆竞技场 v{__version__}"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 14
    page.vertical_alignment = ft.MainAxisAlignment.START

    base = _resolve_storage_path(page)
    storage = Storage(base)
    state = ArenaState()
    state.bind_storage(storage)

    view = build_arena_view(page, state)
    page.add(view)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    # 桌面启动
    ft.app(target=main)
