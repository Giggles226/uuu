"""模型 + API Key 配置面板 — 蓝紫磨砂玻璃大留白风格。"""
from __future__ import annotations

import flet as ft

from arena.models import (
    AIConfig, ApiKeyConfig, ApiType, API_TYPE_LABELS,
    create_empty_ai_config,
)
from arena.llm.router import DEFAULT_ENDPOINTS
from arena.state import ArenaState
from .utils import (
    DANGER, GLASS_BORDER, GLASS_TINT, INDIGO_500, INFO, SUCCESS, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, VIOLET_300, VIOLET_500, WARNING,
    glass_card, section_title, status_badge,
)


# 大留白
SPACING_LG = 24
SPACING_MD = 20
SPACING_SM = 16
SPACING_XS = 12
RADIUS_CARD = 28
RADIUS_PILL = 24
RADIUS_BUBBLE = 20


def api_type_options(include_custom: bool = True) -> list[ft.dropdown.Option]:
    types_ = [t for t in ApiType if include_custom or t != ApiType.CUSTOM]
    return [ft.dropdown.Option(key=t.value, text=API_TYPE_LABELS[t]) for t in types_]


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


def _dropdown_style() -> dict:
    return dict(
        border_radius=RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.05, GLASS_TINT),
        border_color=ft.Colors.with_opacity(0.18, GLASS_BORDER),
        focused_border_color=VIOLET_300,
        text_style=ft.TextStyle(color=TEXT_PRIMARY, size=14),
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        content_padding=ft.Padding.symmetric(horizontal=18, vertical=12),
    )


def _dialog_title(text: str) -> ft.Text:
    return ft.Text(text, size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)


def _dialog_container(content: ft.Control, *, width: int = 460) -> ft.Container:
    return ft.Container(
        content=content,
        padding=SPACING_MD,
        border_radius=RADIUS_CARD,
        bgcolor="#1A0B2E",
        border=ft.Border.all(1, ft.Colors.with_opacity(0.20, VIOLET_300)),
        width=width,
    )


def _primary_button(label: str, on_click, *, icon: str | None = None) -> ft.ElevatedButton:
    btn = ft.ElevatedButton(
        label,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=TEXT_PRIMARY,
            bgcolor=ft.Colors.with_opacity(0.22, VIOLET_500),
            shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
            padding=ft.Padding.symmetric(horizontal=22, vertical=14),
        ),
    )
    return btn


def _ghost_button(label: str, on_click) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        label,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=TEXT_SECONDARY,
            bgcolor=ft.Colors.TRANSPARENT,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
        ),
    )


def build_config_panel(page: ft.Page, state: ArenaState, on_change) -> ft.Control:

    root = ft.Column(spacing=SPACING_MD)

    api_keys_block = ft.Column(spacing=10)
    judge_block = ft.Container(visible=False)
    competitor_block = ft.Column(spacing=10)

    edit_dialog = ft.Ref[ft.AlertDialog]()
    api_dialog = ft.Ref[ft.AlertDialog]()
    mgr_dialog = ft.Ref[ft.AlertDialog]()

    form_state: dict = {"editing": None, "view": "add"}

    def safe_refresh():
        try:
            refresh()
        except Exception as e:  # noqa: BLE001
            print(f"[config_panel] refresh error: {e}")

    def refresh():
        # 1) API Keys
        configs = state.storage.load_api_keys() if state.storage else []
        api_keys_block.controls.clear()
        if configs:
            for c in configs:
                api_keys_block.controls.append(_build_api_key_row(page, c))
        else:
            api_keys_block.controls.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.KEY_OFF, color=TEXT_MUTED, size=16),
                    ft.Text("尚未配置任何 API Key", color=TEXT_SECONDARY, size=13),
                ], spacing=10),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=18,
                bgcolor=ft.Colors.with_opacity(0.03, GLASS_TINT),
            ))

        # 2) Judge
        if state.judge_model:
            judge_block.visible = True
            judge_block.content = _build_judge_card(state, safe_refresh)
        else:
            judge_block.visible = False

        # 3) Competitors
        competitor_block.controls.clear()
        if state.competitors:
            for comp in state.competitors:
                competitor_block.controls.append(_build_competitor_row(comp, state, safe_refresh))
        else:
            competitor_block.controls.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SMART_TOY, color=TEXT_MUTED, size=16),
                    ft.Text("尚未添加模型", color=TEXT_SECONDARY, size=13),
                ], spacing=10),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=18,
                bgcolor=ft.Colors.with_opacity(0.03, GLASS_TINT),
            ))

        # 4) 标题数量
        comp_title.value = f"参赛模型 ({len(state.competitors)}/24)"
        try:
            comp_title.update()
        except RuntimeError:
            pass

        # 5) 外部回调
        if on_change:
            on_change()

        page.update()

    # ─── 模型编辑表单 ───
    name_f = ft.TextField(label="显示名称", hint_text="例如: GPT-4o", **_text_field_style())
    api_type_f = ft.Dropdown(
        label="API 类型",
        options=api_type_options(),
        value=ApiType.OPENAI.value,
        on_select=lambda e: _update_endpoint_hint(),
        **_dropdown_style(),
    )
    endpoint_f = ft.TextField(label="API 地址（留空使用默认）", **_text_field_style())
    model_f = ft.TextField(label="模型名称", hint_text="例如: gpt-4o", **_text_field_style())
    key_f = ft.TextField(label="API Key（留空用全局）", password=True, can_reveal_password=True, **_text_field_style())
    icon_f = ft.TextField(label="图标", value="🤖", width=100, **_text_field_style())
    color_f = ft.TextField(label="颜色", value="#8B5CF6", width=140, **_text_field_style())

    def _update_endpoint_hint():
        at = ApiType(api_type_f.value)
        endpoint_f.hint_text = DEFAULT_ENDPOINTS.get(at, "")
        if endpoint_f.page:
            endpoint_f.update()

    edit_dlg = ft.AlertDialog(
        ref=edit_dialog,
        title=_dialog_title("添加模型"),
        content=_dialog_container(
            ft.Column(
                controls=[name_f, api_type_f, endpoint_f, model_f, key_f,
                          ft.Row([icon_f, color_f], spacing=12)],
                tight=True, spacing=14,
            ),
        ),
        actions=[
            _ghost_button("取消", lambda _: _close_dlg(edit_dialog)),
            _primary_button("保存", lambda _: _save_model(), icon=ft.Icons.SAVE),
        ],
        bgcolor="#1A0B2E",
    )

    def _open_add_model():
        form_state["editing"] = None
        form_state["view"] = "add"
        edit_dialog.current.title = _dialog_title("添加参赛模型")
        name_f.value = ""
        api_type_f.value = ApiType.OPENAI.value
        endpoint_f.value = ""
        model_f.value = "gpt-4o"
        key_f.value = ""
        icon_f.value = "🤖"
        color_f.value = "#8B5CF6"
        _update_endpoint_hint()
        edit_dialog.current.open = True
        page.update()

    def _open_edit_model(comp: AIConfig):
        form_state["editing"] = comp
        form_state["view"] = "edit"
        edit_dialog.current.title = _dialog_title("编辑模型")
        name_f.value = comp.name
        api_type_f.value = comp.api_type.value
        endpoint_f.value = comp.endpoint
        model_f.value = comp.model_name
        key_f.value = comp.api_key
        icon_f.value = comp.icon
        color_f.value = comp.color
        _update_endpoint_hint()
        edit_dialog.current.open = True
        page.update()

    def _save_model():
        if not name_f.value or not model_f.value:
            return
        draft = AIConfig(
            id=form_state["editing"].id if form_state["editing"] else "",
            name=name_f.value,
            api_type=ApiType(api_type_f.value),
            endpoint=endpoint_f.value or "",
            api_key=key_f.value or "",
            model_name=model_f.value,
            icon=icon_f.value or "🤖",
            color=color_f.value or "#8B5CF6",
        )
        if form_state["view"] == "edit":
            state.update_competitor(form_state["editing"].id, {
                "name": draft.name, "api_type": draft.api_type,
                "endpoint": draft.endpoint, "api_key": draft.api_key,
                "model_name": draft.model_name, "icon": draft.icon, "color": draft.color,
            })
        else:
            state.add_competitor(draft)
        _close_dlg(edit_dialog)
        safe_refresh()

    def _close_dlg(ref):
        ref.current.open = False
        page.update()

    page.overlay.append(edit_dlg)

    # ─── API Key 设置对话框 ───
    api_type_ak = ft.Dropdown(
        label="API 类型",
        options=api_type_options(include_custom=False),
        value=ApiType.OPENAI.value,
        on_select=lambda e: _update_ak_endpoint_hint(),
        **_dropdown_style(),
    )
    ak_key = ft.TextField(label="API Key", password=True, can_reveal_password=True, **_text_field_style())
    ak_endpoint = ft.TextField(label="自定义端点（可选）", **_text_field_style())

    def _update_ak_endpoint_hint():
        at = ApiType(api_type_ak.value)
        ak_endpoint.hint_text = DEFAULT_ENDPOINTS.get(at, "")
        if ak_endpoint.page:
            ak_endpoint.update()

    def _open_api_dialog(at: ApiType | None = None):
        if at:
            existing = state.storage.get_api_key(at) if state.storage else None
            api_type_ak.value = at.value
            api_type_ak.disabled = True
            ak_key.value = existing.api_key if existing else ""
            ak_endpoint.value = existing.endpoint if existing and existing.endpoint else ""
        else:
            api_type_ak.disabled = False
            ak_key.value = ""
            ak_endpoint.value = ""
        _update_ak_endpoint_hint()
        api_dialog.current.open = True
        page.update()

    def _save_api_key():
        if not ak_key.value:
            return
        cfg = ApiKeyConfig(
            api_type=ApiType(api_type_ak.value),
            api_key=ak_key.value,
            endpoint=ak_endpoint.value or "",
        )
        if state.storage:
            state.storage.upsert_api_key(cfg)
        _close_dlg(api_dialog)
        if mgr_dialog.current and mgr_dialog.current.open:
            mgr_dialog.current.open = False
            page.update()
        safe_refresh()

    api_dlg = ft.AlertDialog(
        ref=api_dialog,
        title=_dialog_title("设置 API Key"),
        content=_dialog_container(
            ft.Column([api_type_ak, ak_key, ak_endpoint], tight=True, spacing=14),
        ),
        actions=[
            _ghost_button("取消", lambda _: _close_dlg(api_dialog)),
            _primary_button("保存", lambda _: _save_api_key(), icon=ft.Icons.SAVE),
        ],
        bgcolor="#1A0B2E",
    )
    page.overlay.append(api_dlg)

    # ─── API Key 管理对话框 ───
    def _build_api_manager_content() -> ft.Control:
        configs = state.storage.load_api_keys() if state.storage else []
        rows = []
        for at in [t for t in ApiType if t != ApiType.CUSTOM]:
            existing = next((c for c in configs if c.api_type == at), None)
            has = existing and existing.api_key
            rows.append(
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.CHECK_CIRCLE if has else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                color=SUCCESS if has else TEXT_MUTED,
                                size=18,
                            ),
                            padding=6,
                            border_radius=10,
                            bgcolor=ft.Colors.with_opacity(0.14, SUCCESS if has else GLASS_TINT),
                        ),
                        ft.Text(API_TYPE_LABELS[at], size=14, weight=ft.FontWeight.BOLD, expand=True, color=TEXT_PRIMARY),
                        _ghost_button("编辑" if has else "设置",
                                      lambda _, a=at: _open_api_dialog(a)),
                        _ghost_button("清除", lambda _, a=at: _delete_ak(a)),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    border_radius=18,
                    bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.10, GLASS_BORDER)),
                )
            )
        return ft.Container(
            content=ft.Column(controls=rows, scroll=ft.ScrollMode.AUTO, spacing=10),
            width=480, height=520,
        )

    mgr_dlg = ft.AlertDialog(
        ref=mgr_dialog,
        title=_dialog_title("管理全局 API Key"),
        content=_build_api_manager_content(),
        actions=[_primary_button("完成", lambda _: _close_dlg(mgr_dialog), icon=ft.Icons.CHECK)],
        bgcolor="#1A0B2E",
    )
    page.overlay.append(mgr_dlg)

    def _open_api_manager():
        mgr_dialog.current.content = _build_api_manager_content()
        mgr_dialog.current.open = True
        page.update()

    def _delete_ak(at: ApiType):
        if state.storage:
            state.storage.delete_api_key(at)
        safe_refresh()
        _open_api_manager()

    # ─── 组装 ───
    api_section = ft.Column([
        ft.Row([
            section_title(ft.Icon(ft.Icons.KEY, color=VIOLET_300, size=18), "全局 API Key"),
            ft.Container(expand=True),
            ft.ElevatedButton(
                "管理",
                icon=ft.Icons.SETTINGS,
                on_click=lambda _: _open_api_manager(),
                style=ft.ButtonStyle(
                    color=VIOLET_300,
                    bgcolor=ft.Colors.with_opacity(0.10, VIOLET_500),
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
                    padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                ),
            ),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        api_keys_block,
    ], spacing=14)

    comp_title = ft.Text(f"参赛模型 ({len(state.competitors)}/24)", weight=ft.FontWeight.BOLD, size=18, color=TEXT_PRIMARY)
    competitor_section = ft.Column([
        ft.Row([
            section_title(ft.Icon(ft.Icons.SMART_TOY, color=VIOLET_300, size=18), "参赛模型"),
            ft.Container(expand=True),
            ft.Container(
                content=ft.ElevatedButton(
                    "添加",
                    icon=ft.Icons.ADD,
                    on_click=lambda _: _open_add_model(),
                    style=ft.ButtonStyle(
                        color=TEXT_PRIMARY,
                        bgcolor=ft.Colors.with_opacity(0.20, VIOLET_500),
                        shape=ft.RoundedRectangleBorder(radius=RADIUS_PILL),
                        padding=ft.Padding.symmetric(horizontal=22, vertical=14),
                    ),
                ),
                border_radius=RADIUS_PILL,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=16,
                    color=ft.Colors.with_opacity(0.35, VIOLET_500),
                    offset=ft.Offset(0, 4),
                ),
            ),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        competitor_block,
    ], spacing=14)

    root.controls = [
        glass_card(api_section, padding=SPACING_MD, radius=RADIUS_CARD),
        judge_block,
        glass_card(competitor_section, padding=SPACING_MD, radius=RADIUS_CARD),
    ]

    state.on_change(safe_refresh)
    refresh()
    return root


# ─── 内部辅助 ───

def _build_api_key_row(page, cfg: ApiKeyConfig) -> ft.Control:
    label = API_TYPE_LABELS.get(cfg.api_type, cfg.api_type.value)
    has = bool(cfg.api_key.strip())
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(
                    ft.Icons.LOCK_OPEN if has else ft.Icons.LOCK,
                    size=16,
                    color=SUCCESS if has else TEXT_MUTED,
                ),
                padding=8,
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.14, SUCCESS if has else GLASS_TINT),
            ),
            ft.Text(label, size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ft.Container(expand=True),
            ft.Container(
                content=ft.Text("已配置" if has else "未配置", size=11, color=SUCCESS if has else TEXT_MUTED, weight=ft.FontWeight.BOLD),
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.10, SUCCESS if has else GLASS_TINT),
            ),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        border_radius=18,
        bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, GLASS_BORDER)),
    )


def _build_competitor_row(comp: AIConfig, state: ArenaState, on_refresh) -> ft.Control:
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Text(comp.icon, size=22),
                padding=10,
                border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.14, VIOLET_500),
            ),
            ft.Column([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=14, color=TEXT_PRIMARY),
                ft.Text(comp.model_name, size=11, color=TEXT_SECONDARY),
            ], spacing=3, expand=True),
            status_badge(comp.run_status.value),
            ft.IconButton(
                ft.Icons.WORKSPACE_PREMIUM, icon_color=VIOLET_300,
                tooltip="设为裁判",
                on_click=lambda _, c=comp: (state.set_judge_model(c), on_refresh()),
            ),
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE, icon_color=DANGER,
                tooltip="删除",
                on_click=lambda _, cid=comp.id: (state.remove_competitor(cid), on_refresh()),
            ),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        border_radius=20,
        bgcolor=ft.Colors.with_opacity(0.04, GLASS_TINT),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.10, GLASS_BORDER)),
    )


def _build_judge_card(state: ArenaState, on_refresh) -> ft.Control:
    j = state.judge_model
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Text(j.icon, size=26),
                padding=12,
                border_radius=18,
                bgcolor=ft.Colors.with_opacity(0.18, VIOLET_500),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.30, VIOLET_300)),
            ),
            ft.Column([
                ft.Container(
                    content=ft.Text("👑 裁判模型", size=11, color=VIOLET_300, weight=ft.FontWeight.BOLD),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.10, VIOLET_500),
                ),
                ft.Text(j.name, weight=ft.FontWeight.BOLD, size=15, color=TEXT_PRIMARY),
                ft.Text(j.model_name, size=11, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            status_badge(j.run_status.value),
            ft.IconButton(
                ft.Icons.CLOSE, icon_color=DANGER,
                tooltip="取消裁判",
                on_click=lambda _: (state.clear_judge(), on_refresh()),
            ),
        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=ft.Colors.with_opacity(0.08, VIOLET_500),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.30, VIOLET_300)),
        border_radius=22,
        padding=ft.Padding.all(16),
    )
