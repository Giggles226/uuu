"""游戏规则编辑器。"""
from __future__ import annotations

import flet as ft

from arena.models import GameRule, create_default_rule
from .utils import glass_card


def build_rule_editor(state, on_save) -> ft.Control:
    rule = state.game_rule
    name = ft.TextField(label="规则名", value=rule.name)
    desc = ft.TextField(label="简介", value=rule.description, multiline=True, min_lines=1, max_lines=2)
    rules = ft.TextField(
        label="比赛规则（每轮注入）",
        value=rule.rules,
        multiline=True, min_lines=4, max_lines=10,
    )
    judge_criteria = ft.TextField(
        label="裁判评分 / 淘汰标准",
        value=rule.judge_criteria,
        multiline=True, min_lines=4, max_lines=10,
    )
    max_rounds = ft.TextField(
        label="最大轮次", value=str(rule.max_rounds),
        input_filter=ft.NumbersOnlyInputFilter(),
        width=120,
    )
    max_turns = ft.TextField(
        label="每轮私人对话最大回合数", value=str(rule.max_private_turns),
        input_filter=ft.NumbersOnlyInputFilter(),
        width=180,
    )
    round_tpl = ft.TextField(
        label="每轮问题模板（{rules} {question} 占位符）",
        value=rule.round_prompt_template,
        multiline=True, min_lines=2, max_lines=4,
    )
    elim_rules = ft.TextField(
        label="裁判 Agent 提示词",
        value=rule.elimination_rules,
        multiline=True, min_lines=2, max_lines=6,
    )

    save_btn = ft.ElevatedButton(
        "保存规则",
        icon=ft.Icons.SAVE,
        on_click=lambda _: _save(
            state, on_save, name, desc, rules, judge_criteria,
            max_rounds, max_turns, round_tpl, elim_rules,
        ),
    )
    reset_btn = ft.OutlinedButton(
        "重置为默认",
        icon=ft.Icons.RESTART_ALT,
        on_click=lambda _: _reset(state, on_save),
    )

    return glass_card(
        ft.Column(
            controls=[
                ft.Row([ft.Icon(ft.Icons.RULE), ft.Text("游戏规则", weight=ft.FontWeight.BOLD)]),
                name, desc, rules, judge_criteria,
                ft.Row([max_rounds, max_turns]),
                round_tpl, elim_rules,
                ft.Row([save_btn, reset_btn], alignment=ft.MainAxisAlignment.END),
            ],
            spacing=8,
        )
    )


def _save(state, on_save, name, desc, rules, judge_criteria, max_rounds, max_turns, round_tpl, elim_rules):
    new_rule = GameRule(
        id=state.game_rule.id,
        name=name.value or "未命名",
        description=desc.value or "",
        rules=rules.value or "",
        judge_criteria=judge_criteria.value or "",
        max_rounds=int(max_rounds.value or 5),
        max_private_turns=int(max_turns.value or 3),
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
