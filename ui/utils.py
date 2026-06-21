"""UI 工具函数。"""
from __future__ import annotations

import flet as ft


def status_badge(status: str) -> ft.Container:
    palette = {
        "active": (ft.Colors.GREEN_100, ft.Colors.GREEN_900, "运行中"),
        "quota_exhausted": (ft.Colors.RED_100, ft.Colors.RED_900, "额度耗尽"),
        "error": (ft.Colors.RED_100, ft.Colors.RED_900, "错误"),
        "paused": (ft.Colors.AMBER_100, ft.Colors.AMBER_900, "已暂停"),
        "eliminated": (ft.Colors.RED_200, ft.Colors.RED_900, "已淘汰"),
    }
    bg, fg, label = palette.get(status, palette["active"])
    return ft.Container(
        content=ft.Text(label, size=11, color=fg, weight=ft.FontWeight.BOLD),
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=10,
    )


def glass_card(content: ft.Control, padding: int = 16) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=14,
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
    )
