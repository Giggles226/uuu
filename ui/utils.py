"""UI 工具函数 — 蓝紫磨砂玻璃主题。

设计基调：
  - 主色：indigo #6366F1 / violet #8B5CF6 / purple #A855F7
  - 强调：cyan-violet #C4B5FD
  - 背景：深紫黑 #0B0820 → #1A0B2E 渐变
  - 磨砂：半透明白 + 大圆角 + 柔和发光描边
  - 圆角：基础 24，胶囊 28
"""
from __future__ import annotations

import flet as ft


# ─── 主题色板 ───

# 蓝紫系
INDIGO_500 = "#6366F1"
VIOLET_500 = "#8B5CF6"
PURPLE_500 = "#A855F7"
VIOLET_300 = "#C4B5FD"
VIOLET_200 = "#DDD6FE"
INDIGO_700 = "#4338CA"

# 文字
TEXT_PRIMARY = "#F3F0FF"     # 近白偏紫
TEXT_SECONDARY = "#A8A4C7"   # 紫灰
TEXT_MUTED = "#6B6788"       # 暗紫灰

# 状态
SUCCESS = "#34D399"          # 翠绿
WARNING = "#FBBF24"          # 琥珀
DANGER = "#F87171"           # 浅红
INFO = "#60A5FA"             # 蓝

# 玻璃效果
GLASS_TINT = "#FFFFFF"        # 玻璃基色（用 opacity 控制）
GLASS_TINT_STRONG = "#C4B5FD" # 紫光
GLASS_BORDER = "#FFFFFF"      # 描边基色
GLASS_BORDER_OPACITY = 0.10


# ─── 磨砂玻璃容器 ───

def glass_card(
    content: ft.Control,
    *,
    padding: int = 24,
    radius: int = 28,
    tint: str = GLASS_TINT,
    tint_opacity: float = 0.06,
    border_opacity: float = 0.12,
    glow: bool = True,
) -> ft.Container:
    """半透明磨砂玻璃卡片（大圆角 + 柔和发光描边）。"""
    container = ft.Container(
        content=content,
        padding=padding,
        border_radius=radius,
        bgcolor=ft.Colors.with_opacity(tint_opacity, tint),
        border=ft.Border.all(1, ft.Colors.with_opacity(border_opacity, GLASS_BORDER)),
    )
    if glow:
        container.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=24,
            color=ft.Colors.with_opacity(0.18, VIOLET_500),
            offset=ft.Offset(0, 8),
        )
    return container


def soft_badge(content: ft.Control, *, radius: int = 16, padding: int = 12) -> ft.Container:
    """胶囊形小徽章。"""
    return ft.Container(
        content=content,
        border_radius=radius,
        padding=padding,
        bgcolor=ft.Colors.with_opacity(0.10, GLASS_TINT),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.10, GLASS_BORDER)),
    )


# ─── 状态徽章 ───

_STATUS_PALETTE: dict[str, tuple[str, str, str]] = {
    # key: (bg_tint, fg_text, label)
    "active":         (SUCCESS,  "#064E3B", "运行中"),
    "quota_exhausted":(DANGER,   "#7F1D1D", "额度耗尽"),
    "error":          (DANGER,   "#7F1D1D", "错误"),
    "paused":         (WARNING,  "#78350F", "已暂停"),
    "eliminated":     (DANGER,   "#7F1D1D", "已淘汰"),
}


def status_badge(status: str) -> ft.Container:
    """彩色小标签。"""
    bg, fg, label = _STATUS_PALETTE.get(status, _STATUS_PALETTE["active"])
    return ft.Container(
        content=ft.Text(
            label,
            size=11,
            color=fg,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=ft.Colors.with_opacity(0.18, bg),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, bg)),
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


# ─── 渐变背景 ───

def gradient_background() -> ft.Container:
    """深紫黑渐变背景。"""
    return ft.Container(
        expand=True,
        gradient=ft.RadialGradient(
            center=ft.Alignment(0, -0.3),
            radius=1.4,
            colors=[
                ft.Colors.with_opacity(1.0, "#1A0B2E"),
                ft.Colors.with_opacity(1.0, "#0B0820"),
                ft.Colors.with_opacity(1.0, "#050310"),
            ],
            stops=[0.0, 0.5, 1.0],
        ),
    )


# ─── 大标题 ───

def section_title(icon: ft.Icon, text: str, *, color: str = VIOLET_300) -> ft.Container:
    """带图标的版块标题。"""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=icon,
                    padding=8,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.12, VIOLET_500),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.20, VIOLET_300)),
                ),
                ft.Text(
                    text,
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_PRIMARY,
                ),
            ],
            spacing=12,
        ),
        padding=ft.Padding.symmetric(vertical=4),
    )


# ─── 图标工厂 ───

def violet_icon(name: str, *, size: int = 18, color: str = VIOLET_300) -> ft.Icon:
    return ft.Icon(name=name, size=size, color=color)
