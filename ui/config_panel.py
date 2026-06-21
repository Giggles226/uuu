"""模型 + API Key 配置面板（简化版，使用 ft.Ref 管理更新）。"""
from __future__ import annotations

import flet as ft

from arena.models import (
    AIConfig, ApiKeyConfig, ApiType, API_TYPE_LABELS,
    create_empty_ai_config,
)
from arena.llm.router import DEFAULT_ENDPOINTS
from arena.state import ArenaState
from .utils import status_badge


def api_type_options(include_custom: bool = True) -> list[ft.dropdown.Option]:
    types_ = [t for t in ApiType if include_custom or t != ApiType.CUSTOM]
    return [ft.dropdown.Option(key=t.value, text=API_TYPE_LABELS[t]) for t in types_]


def build_config_panel(page: ft.Page, state: ArenaState, on_change) -> ft.Control:
    """构造一个会随 state 变化的配置面板容器。"""

    root = ft.Column(spacing=14)

    api_keys_block = ft.Column(spacing=6)
    judge_block = ft.Container(visible=False)
    competitor_block = ft.Column(spacing=6)

    edit_dialog = ft.Ref[ft.AlertDialog]()
    api_dialog = ft.Ref[ft.AlertDialog]()
    mgr_dialog = ft.Ref[ft.AlertDialog]()

    form_state: dict = {"editing": None, "view": "add"}

    def safe_refresh():
        """统一 refresh 入口，try/except 防止 callback 报错挂掉 UI。"""
        try:
            refresh()
        except Exception as e:  # noqa: BLE001
            print(f"[config_panel] refresh error: {e}")

    def refresh():
        # 1) API Keys
        configs = state.storage.load_api_keys() if state.storage else []
        api_keys_block.controls = [_build_api_key_row(page, c) for c in configs] or [
            ft.Text("尚未配置任何 API Key", color=ft.Colors.GREY, size=12)
        ]

        # 2) Judge
        if state.judge_model:
            judge_block.visible = True
            judge_block.content = _build_judge_card(state, safe_refresh)
        else:
            judge_block.visible = False

        # 3) Competitors
        competitor_block.controls = [
            _build_competitor_row(comp, state, safe_refresh) for comp in state.competitors
        ] or [ft.Text("尚未添加模型", color=ft.Colors.GREY, size=12)]

        # 4) 标题数量（显式 update，避免依赖 page.update 隐式触发）
        comp_title.value = f"参赛模型 ({len(state.competitors)}/24)"
        try:
            comp_title.update()
        except RuntimeError:
            # 尚未挂到 page 上
            pass

        # 5) 外部回调
        if on_change:
            on_change()

        page.update()

    # ─── 模型编辑表单 ───
    name_f = ft.TextField(label="显示名称", hint_text="例如: GPT-4o")
    api_type_f = ft.Dropdown(
        label="API 类型",
        options=api_type_options(),
        value=ApiType.OPENAI.value,
        on_select=lambda e: _update_endpoint_hint(),
    )
    endpoint_f = ft.TextField(label="API 地址（留空使用默认）")
    model_f = ft.TextField(label="模型名称", hint_text="例如: gpt-4o")
    key_f = ft.TextField(label="API Key（留空用全局）", password=True, can_reveal_password=True)
    icon_f = ft.TextField(label="图标", value="🤖", width=100)
    color_f = ft.TextField(label="颜色", value="#3B82F6", width=120)

    def _update_endpoint_hint():
        at = ApiType(api_type_f.value)
        endpoint_f.hint_text = DEFAULT_ENDPOINTS.get(at, "")
        if endpoint_f.page:
            endpoint_f.update()

    edit_dlg = ft.AlertDialog(
        ref=edit_dialog,
        title=ft.Text("添加模型"),
        content=ft.Container(
            content=ft.Column(
                controls=[name_f, api_type_f, endpoint_f, model_f, key_f,
                          ft.Row([icon_f, color_f])],
                tight=True, spacing=8, width=360,
            ),
        ),
        actions=[
            ft.TextButton("取消", on_click=lambda _: _close_dlg(edit_dialog)),
            ft.ElevatedButton("保存", on_click=lambda _: _save_model()),
        ],
    )

    def _open_add_model():
        form_state["editing"] = None
        form_state["view"] = "add"
        edit_dialog.current.title = ft.Text("添加参赛模型")
        name_f.value = ""
        api_type_f.value = ApiType.OPENAI.value
        endpoint_f.value = ""
        model_f.value = "gpt-4o"
        key_f.value = ""
        icon_f.value = "🤖"
        color_f.value = "#3B82F6"
        _update_endpoint_hint()
        edit_dialog.current.open = True
        page.update()

    def _open_edit_model(comp: AIConfig):
        form_state["editing"] = comp
        form_state["view"] = "edit"
        edit_dialog.current.title = ft.Text("编辑模型")
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
            color=color_f.value or "#3B82F6",
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

    # 一次性挂到 overlay，后续复用（修复泄漏：之前每次都 append 新 dialog）
    page.overlay.append(edit_dlg)

    # ─── API Key 设置对话框 ───
    api_type_ak = ft.Dropdown(
        label="API 类型",
        options=api_type_options(include_custom=False),
        value=ApiType.OPENAI.value,
        on_select=lambda e: _update_ak_endpoint_hint(),
    )
    ak_key = ft.TextField(label="API Key", password=True, can_reveal_password=True)
    ak_endpoint = ft.TextField(label="自定义端点（可选）")

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
        # 关闭可能打开的管理面板，避免重复叠加
        if mgr_dialog.current and mgr_dialog.current.open:
            mgr_dialog.current.open = False
            page.update()
        safe_refresh()

    api_dlg = ft.AlertDialog(
        ref=api_dialog,
        title=ft.Text("设置 API Key"),
        content=ft.Container(
            content=ft.Column([api_type_ak, ak_key, ak_endpoint], tight=True, spacing=8, width=360),
        ),
        actions=[
            ft.TextButton("取消", on_click=lambda _: _close_dlg(api_dialog)),
            ft.ElevatedButton("保存", on_click=lambda _: _save_api_key()),
        ],
    )
    page.overlay.append(api_dlg)

    # ─── API Key 管理对话框（也用同一个 ref 复用） ───
    def _build_api_manager_content() -> ft.Control:
        configs = state.storage.load_api_keys() if state.storage else []
        rows = []
        for at in [t for t in ApiType if t != ApiType.CUSTOM]:
            existing = next((c for c in configs if c.api_type == at), None)
            has = existing and existing.api_key
            rows.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if has else ft.Icons.RADIO_BUTTON_UNCHECKED,
                            color=ft.Colors.GREEN if has else ft.Colors.GREY,
                            size=18,
                        ),
                        ft.Text(API_TYPE_LABELS[at], size=13, weight=ft.FontWeight.BOLD, expand=True),
                        ft.OutlinedButton(
                            "编辑" if has else "设置",
                            on_click=lambda _, a=at: _open_api_dialog(a),
                        ),
                        ft.OutlinedButton(
                            "清除",
                            disabled=not has,
                            on_click=lambda _, a=at: _delete_ak(a),
                        ),
                    ]),
                    padding=ft.Padding.all(8),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
                    border_radius=8,
                )
            )
        return ft.Container(
            content=ft.Column(controls=rows, scroll=ft.ScrollMode.AUTO, spacing=6),
            width=400, height=500,
        )

    # 创建一个带 ref 的持久 dialog，append 到 overlay 一次
    mgr_dlg = ft.AlertDialog(
        ref=mgr_dialog,
        title=ft.Text("管理全局 API Key"),
        content=_build_api_manager_content(),
        actions=[ft.TextButton("完成", on_click=lambda _: _close_dlg(mgr_dialog))],
    )
    page.overlay.append(mgr_dlg)

    def _open_api_manager():
        # 只更新内容并打开（dialog 已经在 overlay 里，不会泄漏）
        mgr_dialog.current.content = _build_api_manager_content()
        mgr_dialog.current.open = True
        page.update()

    def _delete_ak(at: ApiType):
        if state.storage:
            state.storage.delete_api_key(at)
        safe_refresh()
        # 重新打开管理面板以反映更改
        _open_api_manager()

    # ─── 组装 ───
    api_section = ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.KEY, color=ft.Colors.AMBER),
            ft.Text("全局 API Key", weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.OutlinedButton("管理", icon=ft.Icons.SETTINGS, on_click=lambda _: _open_api_manager()),
        ]),
        api_keys_block,
    ], spacing=6)

    comp_title = ft.Text(f"参赛模型 ({len(state.competitors)}/24)", weight=ft.FontWeight.BOLD)
    competitor_section = ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.SMART_TOY, color=ft.Colors.BLUE),
            comp_title,
            ft.Container(expand=True),
            ft.ElevatedButton("+ 添加", icon=ft.Icons.ADD, on_click=lambda _: _open_add_model()),
        ]),
        competitor_block,
    ], spacing=6)

    root.controls = [api_section, ft.Divider(height=20), judge_block, competitor_section]

    # 注册刷新回调（state 变化时也刷新本面板）
    state.on_change(safe_refresh)

    # 初次刷新
    refresh()
    return root


# ─── 内部辅助 ───

def _build_api_key_row(page, cfg: ApiKeyConfig) -> ft.Control:
    label = API_TYPE_LABELS.get(cfg.api_type, cfg.api_type.value)
    has = bool(cfg.api_key.strip())
    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.LOCK_OPEN if has else ft.Icons.LOCK,
                size=16,
                color=ft.Colors.GREEN if has else ft.Colors.GREY,
            ),
            ft.Text(label, size=12, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.Text("已配置" if has else "未配置", size=11, color=ft.Colors.GREEN if has else ft.Colors.GREY),
        ],
    )


def _build_competitor_row(comp: AIConfig, state: ArenaState, on_refresh) -> ft.Control:
    return ft.Container(
        content=ft.Row([
            ft.Text(comp.icon, size=22),
            ft.Column([
                ft.Text(comp.name, weight=ft.FontWeight.BOLD, size=13),
                ft.Text(comp.model_name, size=11, color=ft.Colors.GREY),
            ], spacing=2, expand=True),
            status_badge(comp.run_status.value),
            ft.IconButton(
                ft.Icons.WORKSPACE_PREMIUM, icon_color=ft.Colors.AMBER,
                tooltip="设为裁判",
                on_click=lambda _, c=comp: (state.set_judge_model(c), on_refresh()),
            ),
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400,
                tooltip="删除",
                on_click=lambda _, cid=comp.id: (state.remove_competitor(cid), on_refresh()),
            ),
        ]),
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
        border_radius=8,
    )


def _build_judge_card(state: ArenaState, on_refresh) -> ft.Control:
    j = state.judge_model
    return ft.Container(
        content=ft.Row([
            ft.Text(j.icon, size=26),
            ft.Column([
                ft.Text("👑 裁判模型", size=11, color=ft.Colors.AMBER),
                ft.Text(j.name, weight=ft.FontWeight.BOLD),
                ft.Text(j.model_name, size=11, color=ft.Colors.GREY),
            ], spacing=2, expand=True),
            status_badge(j.run_status.value),
            ft.IconButton(
                ft.Icons.CLOSE, icon_color=ft.Colors.RED_400,
                tooltip="取消裁判",
                on_click=lambda _: (state.clear_judge(), on_refresh()),
            ),
        ]),
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.AMBER),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.AMBER)),
        border_radius=10,
        padding=ft.Padding.all(10),
    )
