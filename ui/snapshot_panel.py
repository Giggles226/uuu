"""快照面板 — 管理保存的快照。"""
from __future__ import annotations

import flet as ft

from arena.snapshot import create_snapshot, restore_snapshot
from .utils import glass_card


def build_snapshot_panel(state, on_change) -> ft.Control:
    snaps = state.storage.load_snapshots() if state.storage else []

    def make_snap():
        if not state.competitors and not state.round_history:
            return
        create_snapshot(state, f"手动保存 - {len(snaps) + 1}")
        if on_change:
            on_change()

    header = ft.Row(
        controls=[
            ft.Icon(ft.Icons.SAVE),
            ft.Text(f"快照 ({len(snaps)})", weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.OutlinedButton(
                "保存当前",
                icon=ft.Icons.ADD,
                on_click=lambda _: make_snap(),
            ),
        ]
    )

    rows = []
    for s in reversed(snaps[-20:]):
        rows.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.BOOKMARK, color=ft.Colors.AMBER),
                        ft.Column(
                            controls=[
                                ft.Text(s.label, weight=ft.FontWeight.BOLD, size=12),
                                ft.Text(
                                    f"轮次 {s.current_round} · {len(s.competitors)} 选手 · {len(s.rounds)} 回合",
                                    size=10, color=ft.Colors.GREY,
                                ),
                            ],
                            spacing=2, expand=True,
                        ),
                        ft.IconButton(
                            ft.Icons.PLAY_ARROW,
                            icon_color=ft.Colors.GREEN,
                            tooltip="恢复",
                            on_click=lambda _, sid=s.id: _restore(state, sid, on_change),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            icon_color=ft.Colors.RED_400,
                            tooltip="删除",
                            on_click=lambda _, sid=s.id: _delete(state, sid, on_change),
                        ),
                    ],
                ),
                padding=ft.Padding.all(8),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
                border_radius=8,
            )
        )

    if not rows:
        rows.append(ft.Text("暂无快照", color=ft.Colors.GREY, size=12))

    return glass_card(
        ft.Column(controls=[header, *rows], spacing=8)
    )


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
