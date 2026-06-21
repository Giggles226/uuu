"""主竞技场视图 — 蓝紫磨砂玻璃大留白风格。"""
from __future__ import annotations

import asyncio
import logging
import time

import flet as ft

from arena.arena_logic import ArenaRunner, PHASE_LABELS
from arena.models import GameStatus
from arena.snapshot import resume_game
from arena.state import ArenaState
from .config_panel import build_config_panel
from .rule_editor import build_rule_editor
from .snapshot_panel import build_snapshot_panel
from .utils import (
    DANGER, GLASS_BORDER, GLASS_TINT, INDIGO_500, INFO, SUCCESS, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, VIOLET_300, VIOLET_500, WARNING,
    glass_card, gradient_background, section_title, status_badge,
)

logger = logging.getLogger("uuu.arena_view")


# 大留白：块级 24/20/16，行内 12/8
SPACING_LG = 24
SPACING_MD = 20
SPACING_SM = 16
SPACING_XS = 12
RADIUS_CARD = 28
RADIUS_PILL = 24
RADIUS_BUBBLE = 20


def build_arena_view(page: ft.Page, state: ArenaState) -> ft.Control:
    """返回主页根控件。"""

    runner = ArenaRunner(state)

    # ─── 各区域 ref（先定义，refresh 闭包安全） ───
    phase_indicator = glass_card(
        ft.Row([], spacing=12),
        padding=18,
        radius=24,
        tint=VIOLET_500,
        tint_opacity=0.10,
        border_opacity=0.22,
    )
    phase_indicator.visible = False

    survivors_block = ft.Column(spacing=12)
    eliminated_block = ft.Column(spacing=12)
    public_block = ft.Column(spacing=10)
    judge_block = ft.Container()
    scoreboard_block = ft.Column(spacing=8)
    control_block = ft.Container()
    start_button = ft.ElevatedButton()
    paused_banner = glass_card(
        ft.Row([
            ft.Icon(ft.Icons.PAUSE, color=WARNING, size=22),
            ft.Text("游戏已暂停", weight=ft.FontWeight.BOLD, size=15, color=TEXT_PRIMARY),
        ], spacing=12),
        padding=16,
        radius=20,
        tint=WARNING,
        tint_opacity=0.12,
        border_opacity=0.28,
    )
    paused_banner.visible = False
    err_banner = glass_card(
        ft.Text("", color="#FECACA", size=13),
        padding=14,
        radius=18,
        tint=DANGER,
        tint_opacity=0.12,
        border_opacity=0.28,
    )
    err_banner.visible = False

    # ─── refresh ───

    def refresh():
        # 阶段指示器
        if state.status not in (GameStatus.IDLE, GameStatus.PAUSED):
            phase_indicator.visible = True
            phase_indicator.content = ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.BOLT, color=VIOLET_300, size=18),
                    padding=8,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.18, VIOLET_500),
                ),
                ft.Text(
                    PHASE_LABELS.get(state.phase, ""),
                    weight=ft.FontWeight.BOLD,
                    size=15,
                    color=TEXT_PRIMARY,
                ),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Text(
                        f"轮次 {state.round + 1}/{state.game_rule.max_rounds}",
                        size=12,
                        color=TEXT_SECONDARY,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                    border_radius=14,
                    bgcolor=ft.Colors.with_opacity(0.08, GLASS_TINT),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.10, GLASS_BORDER)),
                ),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            phase_indicator.visible = False

        paused_banner.visible = state.status == GameStatus.PAUSED

        # 存活选手
        survivors = state.get_survivors()
        survivors_block.controls.clear()
        survivors_block.controls.append(_section_header(
            "存活选手", f"{len(survivors)}", ft.Icons.CIRCLE, SUCCESS,
        ))
        for comp in survivors:
            chat = next((c for c in state.private_chats if c.competitor_id == comp.id), None)
            survivors_block.controls.append(_build_competitor_card(comp, chat, state))

        # 淘汰选手
        eliminated = state.get_eliminated()
        eliminated_block.controls.clear()
        if eliminated:
            eliminated_block.controls.append(_section_header(
                "已淘汰", f"{len(eliminated)} · 已禁言", ft.Icons.CANCEL, DANGER,
            ))
            for comp in eliminated:
                chat = next((c for c in state.private_chats if c.competitor_id == comp.id), None)
                reason = state.elimination_reasons.get(comp.id, "被淘汰")
                eliminated_block.controls.append(_build_eliminated_card(comp, chat, reason))

        # 公共发言
        public_block.controls.clear()
        if state.public_messages:
            public_block.controls.append(_section_header(
                "公共发言", "", ft.Icons.CAMPAIGN, VIOLET_300,
            ))
            for msg in state.public_messages[-20:]:
                public_block.controls.append(_build_public_bubble(msg))

        # 裁判点评
        if state.judge_comment:
            judge_block.content = glass_card(
                ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Icon(ft.Icons.GAVEL, color=VIOLET_300, size=18),
                            padding=8,
                            border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.18, VIOLET_500),
                        ),
                        ft.Text("裁判点评", weight=ft.FontWeight.BOLD, size=15, color=TEXT_PRIMARY),
                    ], spacing=12),
                    ft.Container(height=4),
                    ft.Container(
                        content=ft.Text(state.judge_comment, size=13, color=TEXT_PRIMARY),
                        padding=ft.Padding.all(14),
                        border_radius=RADIUS_BUBBLE,
                        bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
                    ),
                ], spacing=8),
            )
        else:
            judge_block.content = ft.Container()

        # 积分榜
        all_players = list(state.competitors)
        if state.judge_model:
            all_players = [state.judge_model] + all_players
        sorted_players = sorted(
            all_players, key=lambda c: -state.total_scores.get(c.id, 0)
        )
        scoreboard_block.controls.clear()
        scoreboard_block.controls.append(_section_header(
            "积分榜", "", ft.Icons.EMOJI_EVENTS, VIOLET_300,
        ))
        for i, p in enumerate(sorted_players[:10]):
            score = state.total_scores.get(p.id, 0)
            medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else f"{i+1}"))
            scoreboard_block.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(medal, size=18, width=32, color=TEXT_SECONDARY),
                        ft.Text(p.icon, size=18),
                        ft.Text(p.name, size=13, expand=True, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Container(
                            content=ft.Text(f"{score} 分", color=VIOLET_300, size=12, weight=ft.FontWeight.BOLD),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            border_radius=14,
                            bgcolor=ft.Colors.with_opacity(0.10, VIOLET_500),
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.20, VIOLET_300)),
                        ),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    border_radius=18,
                    bgcolor=ft.Colors.with_opacity(0.03, GLASS_TINT),
                )
            )

        # 错误提示
        if state.error:
            err_banner.content = ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER, color=DANGER, size=18),
                ft.Text(f"⚠️ {state.error}", color="#FECACA", size=13, expand=True),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            err_banner.visible = True
        else:
            err_banner.visible = False

        # 控制按钮
        if state.status == GameStatus.IDLE:
            start_button.disabled = False
            start_button.text = "开始游戏"
            start_button.icon = ft.Icons.PLAY_ARROW
            start_button.on_click = lambda _: on_start()
        elif state.status == GameStatus.LOADING:
            start_button.disabled = True
            start_button.text = "游戏中..."
            start_button.icon = ft.Icons.HOURGLASS_EMPTY
        elif state.status == GameStatus.PAUSED:
            start_button.disabled = False
            start_button.text = "恢复游戏"
            start_button.icon = ft.Icons.PLAY_ARROW
            start_button.on_click = lambda _: on_resume()
        elif state.status == GameStatus.FINISHED:
            start_button.disabled = False
            start_button.text = "下一轮" if state.phase.value == "round_end" else "重新开始"
            start_button.icon = ft.Icons.SKIP_NEXT if state.phase.value == "round_end" else ft.Icons.REFRESH
            if state.phase.value == "round_end":
                start_button.on_click = lambda _: on_next_round()
            else:
                start_button.on_click = lambda _: on_reset()

        page.update()

    # ─── 回调 ───

    def on_start():
        if runner.start_round():
            page.run_task(_drive_loop)

    def on_next_round():
        state.next_round()

    def on_reset():
        state.reset_game()

    def on_resume():
        snap = resume_game(state)
        if snap:
            page.open(ft.SnackBar(ft.Text("已从最新快照恢复"), duration=2000))

    async def _drive_loop():
        try:
            while state.status == GameStatus.LOADING:
                await runner.tick()
                if state.status == GameStatus.PAUSED:
                    page.open(ft.SnackBar(
                        ft.Text("游戏已自动暂停（可能有模型额度耗尽）"),
                        duration=4000,
                    ))
                    break
                await asyncio.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            logger.exception("game loop crashed")
            state.set_error(str(e))

    # ─── 顶部标题 ───
    header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text("🍺", size=30),
                    padding=ft.Padding.all(12),
                    border_radius=20,
                    bgcolor=ft.Colors.with_opacity(0.12, VIOLET_500),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.22, VIOLET_300)),
                ),
                ft.Column([
                    ft.Text("AI 酒馆竞技场", size=28, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text("生存博弈 · 裁判 Agent · 私人对话淘汰制", size=12, color=TEXT_SECONDARY),
                ], spacing=2),
            ],
            spacing=16,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(vertical=SPACING_MD),
    )

    # ─── 问题输入 + 启动按钮 ───
    question_field = ft.TextField(
        label="本轮问题",
        hint_text="例如：如果只能保留一个能力，你会保留什么？",
        multiline=True,
        min_lines=1,
        max_lines=4,
        on_change=lambda e: state.set_question(e.control.value or ""),
        border_radius=RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.05, GLASS_TINT),
        border_color=ft.Colors.with_opacity(0.18, GLASS_BORDER),
        focused_border_color=VIOLET_300,
        text_style=ft.TextStyle(color=TEXT_PRIMARY, size=14),
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        hint_style=ft.TextStyle(color=TEXT_MUTED),
        cursor_color=VIOLET_300,
        content_padding=ft.Padding.symmetric(horizontal=18, vertical=14),
    )

    control_block.content = ft.Column([
        ft.Row([
            question_field,
            ft.Container(width=SPACING_XS),
            _gradient_button(start_button),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=0)
    start_button.disabled = True
    start_button.text = "开始游戏"
    start_button.style = ft.ButtonStyle(
        color=TEXT_PRIMARY,
        bgcolor=ft.Colors.with_opacity(0.16, VIOLET_500),
        shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
        padding=ft.Padding.symmetric(horizontal=24, vertical=18),
    )

    # ─── 配置 / 规则 / 快照 ───
    config_panel = build_config_panel(page, state, on_change=refresh)
    rule_editor = build_rule_editor(state, on_save=refresh)
    snapshot_panel = build_snapshot_panel(state, on_change=refresh)

    # ─── 顶部状态区 ───
    top_block = ft.Column([
        phase_indicator,
        paused_banner,
        err_banner,
    ], spacing=12)

    # ─── 主游戏区域 ───
    main_block = ft.Column([
        ft.ResponsiveRow([
            ft.Column(
                [glass_card(ft.Column([survivors_block, eliminated_block], spacing=SPACING_MD),
                            padding=SPACING_MD)],
                col={"sm": 12, "md": 7},
            ),
            ft.Column([
                glass_card(public_block, padding=SPACING_MD),
                judge_block,
                glass_card(scoreboard_block, padding=SPACING_MD),
            ], spacing=SPACING_MD, col={"sm": 12, "md": 5}),
        ], run_spacing=SPACING_MD),
    ], spacing=SPACING_MD)

    # 注册刷新回调
    state.on_change(refresh)

    # 整体布局（用 Stack 让渐变背景铺满 + 滚动内容）
    content = ft.Column([
        header,
        top_block,
        config_panel,
        rule_editor,
        snapshot_panel,
        control_block,
        main_block,
    ], spacing=SPACING_LG, scroll=ft.ScrollMode.AUTO, expand=True)

    root = ft.Container(
        content=content,
        expand=True,
        padding=ft.Padding.all(SPACING_LG),
    )

    # 渐变背景 + 滚动内容
    final = ft.Stack(
        controls=[gradient_background(), root],
        expand=True,
    )

    refresh()
    return final


# ─── 内部组件 ───

def _fmt_time(ts: int) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts / 1000))


def _gradient_button(button: ft.ElevatedButton) -> ft.Container:
    """包装按钮为渐变高亮样式（用 Container.shadow 实现发光感）。"""
    return ft.Container(
        content=button,
        border_radius=RADIUS_PILL,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.40, VIOLET_500),
            offset=ft.Offset(0, 6),
        ),
    )


def _section_header(text: str, count: str, icon_name: str, accent: str) -> ft.Container:
    """版块小标题（图标 + 文字 + 数量）。"""
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(icon_name, color=accent, size=16),
                padding=6,
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.18, accent),
            ),
            ft.Text(text, weight=ft.FontWeight.BOLD, size=14, color=TEXT_PRIMARY),
            ft.Container(expand=True),
            ft.Text(count, size=12, color=TEXT_SECONDARY),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=6),
    )


def _build_competitor_card(comp, chat, state) -> ft.Control:
    is_conversing = state.current_conversation_id == comp.id
    is_loading = is_conversing and state.status == GameStatus.LOADING

    # 私人对话展开
    chat_msgs: list[ft.Control] = []
    if chat and chat.messages:
        for m in chat.messages:
            is_judge = m.role == "judge"
            bubble_color = VIOLET_500 if is_judge else INDIGO_500
            chat_msgs.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(
                            "⚖️ 裁判" if is_judge else f"{comp.icon} {comp.name}",
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            color=VIOLET_300 if is_judge else INFO,
                        ),
                        ft.Text(m.content, size=12, color=TEXT_PRIMARY),
                    ], spacing=3),
                    padding=ft.Padding.all(12),
                    border_radius=RADIUS_BUBBLE,
                    bgcolor=ft.Colors.with_opacity(0.08 if is_judge else 0.05, bubble_color),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.14, bubble_color)),
                )
            )

    header = ft.Row([
        ft.Container(
            content=ft.Text(comp.icon, size=24),
            padding=10,
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.12, VIOLET_500),
        ),
        ft.Column([
            ft.Row([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=14, color=TEXT_PRIMARY),
                status_badge(comp.run_status.value),
            ], spacing=8),
            ft.Text(comp.model_name, size=11, color=TEXT_SECONDARY),
        ], spacing=4, expand=True),
    ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    body = ft.Column([header, *chat_msgs], spacing=10)

    if is_loading:
        body.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.ProgressRing(width=16, height=16, color=VIOLET_300, stroke_width=2),
                    ft.Text("等待回复...", size=12, color=TEXT_SECONDARY),
                ], spacing=10),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
            )
        )

    border_color = VIOLET_500 if is_conversing else GLASS_BORDER
    border_w = 2 if is_conversing else 1
    border_op = 0.55 if is_conversing else 0.10

    return ft.Container(
        content=body,
        padding=ft.Padding.all(16),
        border_radius=22,
        bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
        border=ft.Border.all(border_w, ft.Colors.with_opacity(border_op, border_color)),
    )


def _build_eliminated_card(comp, chat, reason: str) -> ft.Control:
    body = ft.Column([
        ft.Row([
            ft.Container(
                content=ft.Text(comp.icon, size=24, color=TEXT_MUTED),
                padding=10,
                border_radius=16,
                bgcolor=ft.Colors.with_opacity(0.06, DANGER),
            ),
            ft.Column([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=14, color=TEXT_MUTED),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=DANGER, size=12),
                        ft.Text(reason, size=11, color="#FCA5A5"),
                    ], spacing=6),
                ),
            ], spacing=4, expand=True),
            status_badge("eliminated"),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=8)
    return ft.Container(
        content=body,
        padding=ft.Padding.all(14),
        border_radius=20,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.20, DANGER)),
        bgcolor=ft.Colors.with_opacity(0.05, DANGER),
        opacity=0.85,
    )


def _build_public_bubble(msg) -> ft.Control:
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Text(msg.sender_icon or "👑", size=16),
                    padding=6,
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.18, VIOLET_500),
                ),
                ft.Text(msg.sender_name, weight=ft.FontWeight.BOLD, size=12, color=VIOLET_300),
                ft.Container(expand=True),
                ft.Text(_fmt_time(msg.timestamp), size=10, color=TEXT_MUTED),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                content=ft.Text(msg.content, size=12, color=TEXT_PRIMARY),
                padding=ft.Padding.all(12),
                border_radius=RADIUS_BUBBLE,
                bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
            ),
        ], spacing=8),
    )
