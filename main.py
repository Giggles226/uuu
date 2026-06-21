"""Flet 应用入口。

打包为 APK：
    flet build apk

桌面开发：
    python main.py

或在 Flet 应用中：
    flet run main.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import flet as ft

from arena import __version__
from arena.state import ArenaState
from arena.storage import Storage
from ui.arena_view import build_arena_view


def main(page: ft.Page):
    page.title = f"AI 酒馆竞技场 v{__version__}"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 14
    page.vertical_alignment = ft.MainAxisAlignment.START

    # 存储路径：优先使用 Flet 应用私有目录（Android），桌面端用 cwd/storage
    if page.session and hasattr(page, 'session_id'):
        # 在 Flet 打包环境中
        try:
            base = ft.app_storage_path()
        except Exception:
            base = str(Path.cwd() / "storage")
    else:
        base = str(Path.cwd() / "storage")

    storage = Storage(base)
    state = ArenaState()
    state.bind_storage(storage)

    view = build_arena_view(page, state)
    page.add(view)


if __name__ == "__main__":
    # 桌面启动
    ft.app(target=main)
