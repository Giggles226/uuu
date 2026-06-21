"""快照面板 — 蓝紫磨砂玻璃大留白风格。"""
from __future__ import annotations

import flet as ft

from arena.snapshot import create_snapshot, restore_snapshot
from .utils import (
    DANGER, GLASS_BORDER, GLASS_TINT, INDIGO_500, INFO, SUCCESS, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, VIOLET_300, VIOLET_500, WARNING,
    glass_card, section_title,
)


SPACING_MD = 20
RADIUS_CARD = 28
RADIUS_PILL = 24
RADIUS_BUBBLE = 20


def build_snapshot_panel(state, on_change) -> ft.Control:
    snaps = state.storage.load_snapshots() if state.storage else []

    def make_snap():
        if not state.competitors and not state.round_history:
            return
        # 每次重新读取，避免闭包过期（修复 M1：之前用旧的 len(snaps) 导致标签重复）
        current_snaps = state.storage.load_snapshots() if state.storage else []
        create_snapshot(state, f"手动保存 - {len(current_snaps) + 1}")
        if on_change:
            on_change()

    header = ft.Row(
        controls=[
            section_title(ft.Icon(ft.Icons.BOOKMARK, color=VIOLET_300, size=18), "快照"),
            ft.Container(expand=True),
            ft.ElevatedButton(
                "保存当前",
                icon=ft.Icons.ADD,
                on_click=lambda _: make_snap(),
                style=ft.ButtonStyle(
                    color=TEXT_PRIMARY,
                    bgcolor=ft.Colors.with_opacity(0.22, VIOLET_500),
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
                    padding=ft.Padding.symmetric(horizontal=20, vertical=14),
                ),
            ),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    rows = []
    for s in reversed(snaps[-20:]):
        rows.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(ft.Icons.BOOKMARK, color=VIOLET_300, size=18),
                            padding=8,
                            border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.14, VIOLET_500),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(s.label, weight=ft.FontWeight.BOLD, size=14, color=TEXT_PRIMARY),
                                ft.Text(
                                    f"轮次 {s.current_round} · {len(s.competitors)} 选手 · {len(s.rounds)} 回合",
                                    size=11, color=TEXT_SECONDARY,
                                ),
                            ],
                            spacing=3, expand=True,
                        ),
                        ft.IconButton(
                            ft.Icons.PLAY_ARROW, icon_color=SUCCESS,
                            tooltip="恢复",
                            on_click=lambda _, sid=s.id: _restore(state, sid, on_change),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE, icon_color=DANGER,
                            tooltip="删除",
                            on_click=lambda _, sid=s.id: _delete(state, sid, on_change),
                        ),
                    ],
                    spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.10, GLASS_BORDER)),
            )
        )

    if not rows:
        rows.append(ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.BOOKMARK_BORDER, color=TEXT_MUTED, size=16),
                ft.Text("暂无快照", color=TEXT_SECONDARY, size=13),
            ], spacing=10),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.03, GLASS_TINT),
        ))

    body = ft.Column(controls=[header, *rows], spacing=12)
    return glass_card(body, padding=SPACING_MD, radius=RADIUS_CARD)


def _restore(state, snap_id, on_change):
    snaps = state.storage.load_snapshots() if state.storage else []
    for s in snaps:
        if s.id == snap_id:
            restore_snapshot(state, s)
            if on_change:
                on_change()
            return


def _delete(state, snap_id, on_change):
    if state.storage:
        state.storage.delete_snapshot(snap_id)
    if on_change:
        on_change()
