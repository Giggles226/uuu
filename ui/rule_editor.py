"""游戏规则编辑器 — 蓝紫磨砂玻璃大留白风格。"""
from __future__ import annotations

import flet as ft

from arena.models import GameRule, create_default_rule
from .utils import (
    DANGER, GLASS_BORDER, GLASS_TINT, INDIGO_500, INFO, SUCCESS, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, VIOLET_300, VIOLET_500, WARNING,
    glass_card, section_title, status_badge,
)


SPACING_MD = 20
SPACING_SM = 16
SPACING_XS = 12
RADIUS_CARD = 28
RADIUS_PILL = 24


def _text_field_style() -> dict:
    return dict(
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


def build_rule_editor(state, on_save) -> ft.Control:
    rule = state.game_rule
    name = ft.TextField(label="规则名", value=rule.name, **_text_field_style())
    desc = ft.TextField(
        label="简介", value=rule.description,
        multiline=True, min_lines=1, max_lines=2, **_text_field_style(),
    )
    rules = ft.TextField(
        label="比赛规则（每轮注入）", value=rule.rules,
        multiline=True, min_lines=4, max_lines=10, **_text_field_style(),
    )
    judge_criteria = ft.TextField(
        label="裁判评分 / 淘汰标准", value=rule.judge_criteria,
        multiline=True, min_lines=4, max_lines=10, **_text_field_style(),
    )
    max_rounds = ft.TextField(
        label="最大轮次", value=str(rule.max_rounds),
        input_filter=ft.NumbersOnlyInputFilter(), width=140, **_text_field_style(),
    )
    max_turns = ft.TextField(
        label="每轮对话回合", value=str(rule.max_private_turns),
        input_filter=ft.NumbersOnlyInputFilter(), width=180, **_text_field_style(),
    )
    round_tpl = ft.TextField(
        label="每轮问题模板（{rules} {question} 占位符）",
        value=rule.round_prompt_template,
        multiline=True, min_lines=2, max_lines=4, **_text_field_style(),
    )
    elim_rules = ft.TextField(
        label="裁判 Agent 提示词", value=rule.elimination_rules,
        multiline=True, min_lines=2, max_lines=6, **_text_field_style(),
    )

    save_btn = ft.ElevatedButton(
        "保存规则",
        icon=ft.Icons.SAVE,
        on_click=lambda _: _save(
            state, on_save, name, desc, rules, judge_criteria,
            max_rounds, max_turns, round_tpl, elim_rules,
        ),
        style=ft.ButtonStyle(
            color=TEXT_PRIMARY,
            bgcolor=ft.Colors.with_opacity(0.22, VIOLET_500),
            shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
            padding=ft.Padding.symmetric(horizontal=22, vertical=14),
        ),
    )
    reset_btn = ft.ElevatedButton(
        "重置为默认",
        icon=ft.Icons.RESTART_ALT,
        on_click=lambda _: _reset(state, on_save),
        style=ft.ButtonStyle(
            color=TEXT_SECONDARY,
            bgcolor=ft.Colors.TRANSPARENT,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
        ),
    )

    body = ft.Column(
        controls=[
            section_title(ft.Icon(ft.Icons.RULE, color=VIOLET_300, size=18), "游戏规则"),
            name, desc,
            rules, judge_criteria,
            ft.Row([max_rounds, max_turns], spacing=12),
            round_tpl, elim_rules,
            ft.Row([save_btn, reset_btn], alignment=ft.MainAxisAlignment.END, spacing=12),
        ],
        spacing=14,
    )

    return glass_card(body, padding=SPACING_MD, radius=RADIUS_CARD)


def _save(state, on_save, name, desc, rules, judge_criteria, max_rounds, max_turns, round_tpl, elim_rules):
    new_rule = GameRule(
        id=state.game_rule.id,
        name=name.value or "未命名",
        description=desc.value or "",
        rules=rules.value or "",
        judge_criteria=judge_criteria.value or "",
        max_rounds=max(1, int(max_rounds.value or 5)),
        max_private_turns=max(1, int(max_turns.value or 3)),
        round_prompt_template=round_tpl.value or state.game_rule.round_prompt_template,
        elimination_rules=elim_rules.value or "",
    )
    state.set_rule(new_rule)
    if on_save:
        on_save()


def _reset(state, on_save):
    state.set_rule(create_default_rule())
    if on_save:
        on_save()
