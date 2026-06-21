"""主竞技场视图 — 组合所有面板。"""
from __future__ import annotations

import asyncio

import flet as ft

from arena.arena_logic import ArenaRunner, PHASE_LABELS
from arena.models import GameStatus
from arena.snapshot import resume_game
from arena.state import ArenaState
from .config_panel import build_config_panel
from .rule_editor import build_rule_editor
from .snapshot_panel import build_snapshot_panel
from .utils import glass_card, status_badge


def build_arena_view(page: ft.Page, state: ArenaState) -> ft.Control:
    """返回主页根控件（Column）。"""

    runner = ArenaRunner(state)

    # ─── 各区域 ref ───
    phase_indicator = ft.Container(visible=False)
    survivors_block = ft.Column(spacing=8)
    eliminated_block = ft.Column(spacing=8)
    public_block = ft.Column(spacing=6)
    judge_block = ft.Container()
    scoreboard_block = ft.Column(spacing=4)
    control_block = ft.Container()
    start_button = ft.ElevatedButton()

    def refresh():
        # 阶段指示器
        if state.status not in (GameStatus.IDLE, GameStatus.PAUSED):
            phase_indicator.visible = True
            phase_indicator.content = ft.Container(
                content=ft.Row([
                    ft.Text(PHASE_LABELS.get(state.phase, ""), weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER),
                    ft.Container(expand=True),
                    ft.Text(
                        f"轮次 {state.round + 1}/{state.game_rule.max_rounds}",
                        size=12, color=ft.Colors.GREY,
                    ),
                ]),
                padding=ft.Padding.all(10),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.AMBER),
            )
        else:
            phase_indicator.visible = False

        # 暂停提示
        paused_banner.visible = state.status == GameStatus.PAUSED

        # 存活选手
        survivors = state.get_survivors()
        survivors_block.controls = [
            ft.Text(f"🟢 存活 ({len(survivors)})", weight=ft.FontWeight.BOLD, size=14)
        ] if survivors else []
        for comp in survivors:
            chat = next((c for c in state.private_chats if c.competitor_id == comp.id), None)
            survivors_block.controls.append(_build_competitor_card(comp, chat, state))

        # 淘汰选手
        eliminated = state.get_eliminated()
        eliminated_block.controls = []
        if eliminated:
            eliminated_block.controls.append(
                ft.Text(f"🔴 已淘汰 ({len(eliminated)}) · 已禁言", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.RED_400)
            )
            for comp in eliminated:
                chat = next((c for c in state.private_chats if c.competitor_id == comp.id), None)
                reason = state.elimination_reasons.get(comp.id, "被淘汰")
                eliminated_block.controls.append(_build_eliminated_card(comp, chat, reason))

        # 公共发言
        public_block.controls = []
        if state.public_messages:
            public_block.controls.append(
                ft.Text("📢 公共发言", weight=ft.FontWeight.BOLD, size=13)
            )
            for msg in state.public_messages[-20:]:
                public_block.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text(msg.sender_icon or "👑", size=14),
                                ft.Text(msg.sender_name, weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.AMBER),
                                ft.Text(_fmt_time(msg.timestamp), size=10, color=ft.Colors.GREY),
                            ], spacing=6),
                            ft.Text(msg.content, size=12),
                        ], spacing=4),
                        padding=ft.Padding.all(10),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.AMBER)),
                        border_radius=8,
                    )
                )

        # 裁判点评
        if state.judge_comment:
            judge_block.content = glass_card(
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.GAVEL, color=ft.Colors.AMBER),
                            ft.Text("裁判点评", weight=ft.FontWeight.BOLD)]),
                    ft.Text(state.judge_comment, size=12),
                ], spacing=6),
            )
        else:
            judge_block.content = ft.Container()

        # 积分榜
        all_players = state.competitors
        if state.judge_model:
            all_players = [state.judge_model] + all_players
        sorted_players = sorted(
            all_players, key=lambda c: -state.total_scores.get(c.id, 0)
        )
        scoreboard_block.controls = [ft.Text("🏆 积分榜", weight=ft.FontWeight.BOLD, size=13)]
        for i, p in enumerate(sorted_players[:10]):
            score = state.total_scores.get(p.id, 0)
            scoreboard_block.controls.append(
                ft.Row([
                    ft.Text(f"{i+1}.", width=24, color=ft.Colors.GREY),
                    ft.Text(p.icon, size=14),
                    ft.Text(p.name, size=12, expand=True, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{score}分", color=ft.Colors.AMBER, size=12, weight=ft.FontWeight.BOLD),
                ], spacing=4)
            )

        # 错误提示
        if state.error:
            err_banner.content = ft.Text(f"⚠️ {state.error}", color=ft.Colors.RED_300, size=12)
            err_banner.visible = True
        else:
            err_banner.visible = False

        # 控制按钮
        if state.status == GameStatus.IDLE:
            start_button.disabled = False
            start_button.text = "🚀 开始游戏"
            start_button.icon = ft.Icons.PLAY_ARROW
            start_button.on_click = lambda _: on_start()
        elif state.status == GameStatus.LOADING:
            start_button.disabled = True
            start_button.text = "⏳ 游戏中..."
            start_button.icon = ft.Icons.HOURGLASS_EMPTY
        elif state.status == GameStatus.PAUSED:
            start_button.disabled = False
            start_button.text = "▶ 恢复游戏"
            start_button.icon = ft.Icons.PLAY_ARROW
            start_button.on_click = lambda _: on_resume()
        elif state.status == GameStatus.FINISHED:
            start_button.disabled = False
            start_button.text = "➡ 下一轮" if state.phase.value == "round_end" else "🔄 重新开始"
            start_button.icon = ft.Icons.SKIP_NEXT if state.phase.value == "round_end" else ft.Icons.REFRESH
            if state.phase.value == "round_end":
                start_button.on_click = lambda _: on_next_round()
            else:
                start_button.on_click = lambda _: on_reset()

        page.update()

    # ─── 回调 ───

    def on_start():
        if runner.start_round():
            # 启动 asyncio 循环
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
        content=ft.Column([
            ft.Text("🍺 AI 酒馆竞技场", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER),
            ft.Text("生存博弈 · 裁判 Agent · 私人对话淘汰制", size=12, color=ft.Colors.GREY),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
        padding=ft.Padding.symmetric(vertical=10),
    )

    # ─── 阶段指示器 ───
    paused_banner = ft.Container(
        visible=False,
        content=ft.Row([
            ft.Icon(ft.Icons.PAUSE, color=ft.Colors.AMBER),
            ft.Text("游戏已暂停", weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER),
        ]),
        padding=ft.Padding.all(10),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.AMBER)),
        border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.AMBER),
    )

    err_banner = ft.Container(visible=False, padding=ft.Padding.all(8))

    # ─── 问题输入 + 启动按钮 ───
    question_field = ft.TextField(
        label="本轮问题",
        hint_text="例如：如果只能保留一个能力，你会保留什么？",
        multiline=True,
        min_lines=1,
        max_lines=4,
        on_change=lambda e: state.set_question(e.control.value or ""),
    )

    control_block.content = ft.Row([
        question_field,
        start_button,
    ], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.END)
    # 默认禁用
    start_button.disabled = True
    start_button.text = "🚀 开始游戏"

    # ─── 配置面板 / 规则 / 快照 ───
    config_panel = build_config_panel(page, state, on_change=refresh)
    rule_editor = build_rule_editor(state, on_save=refresh)
    snapshot_panel = build_snapshot_panel(state, on_change=refresh)

    # ─── 顶部状态 ───
    top_block = ft.Column([
        phase_indicator,
        paused_banner,
        err_banner,
    ], spacing=8)

    # ─── 主游戏区域 ───
    main_block = ft.Column([
        ft.ResponsiveRow([
            ft.Column([ft.Container(content=ft.Column([survivors_block, eliminated_block], spacing=10))], col={"sm": 12, "md": 7}),
            ft.Column([
                ft.Container(content=public_block),
                ft.Container(content=judge_block),
                ft.Container(content=ft.Column([scoreboard_block], spacing=4)),
            ], col={"sm": 12, "md": 5}),
        ]),
    ], spacing=10)

    # 注册刷新回调
    state.on_change(refresh)

    # 整体布局
    root = ft.Column([
        header,
        top_block,
        config_panel,
        rule_editor,
        snapshot_panel,
        control_block,
        main_block,
    ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    refresh()
    return root


# ─── 内部 ───

def _fmt_time(ts: int) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts / 1000))


def _build_competitor_card(comp, chat, state) -> ft.Control:
    is_conversing = state.current_conversation_id == comp.id
    is_loading = is_conversing and state.status == GameStatus.LOADING

    # 私人对话展开
    chat_msgs: list[ft.Control] = []
    if chat and chat.messages:
        for m in chat.messages:
            chat_msgs.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(
                            "⚖️ 裁判" if m.role == "judge" else f"{comp.icon} {comp.name}",
                            size=10, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.AMBER if m.role == "judge" else ft.Colors.BLUE,
                        ),
                        ft.Text(m.content, size=11),
                    ], spacing=2),
                    padding=ft.Padding.all(6),
                    border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                )
            )

    header = ft.Row([
        ft.Text(comp.icon, size=22),
        ft.Column([
            ft.Row([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=13),
                status_badge(comp.run_status.value),
            ], spacing=6),
            ft.Text(comp.model_name, size=10, color=ft.Colors.GREY),
        ], spacing=2, expand=True),
    ])

    body = ft.Column([header, *chat_msgs], spacing=6)

    if is_loading:
        body.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.ProgressRing(width=14, height=14),
                    ft.Text("等待回复...", size=11, color=ft.Colors.GREY),
                ], spacing=8),
            )
        )

    return ft.Container(
        content=body,
        padding=ft.Padding.all(10),
        border=ft.Border.all(
            2 if is_conversing else 1,
            ft.Colors.AMBER if is_conversing else ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        ),
        border_radius=10,
    )


def _build_eliminated_card(comp, chat, reason: str) -> ft.Control:
    body = ft.Column([
        ft.Row([
            ft.Text(comp.icon, size=22, color=ft.Colors.GREY),
            ft.Column([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.GREY),
                ft.Text(reason, size=10, color=ft.Colors.RED_300),
            ], spacing=2, expand=True),
            status_badge("eliminated"),
        ]),
    ], spacing=4)
    return ft.Container(
        content=body,
        padding=ft.Padding.all(8),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.RED)),
        border_radius=8,
        opacity=0.6,
    )
