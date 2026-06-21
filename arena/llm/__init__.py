"""LLM 统一协议层 — 入口。

调用方（竞技场 / 裁判）只需：
    from arena.llm import router
    resp = router.call_chat(config, system, user, storage)
"""

from . import base
from . import router
from .base import (
    BaseAdapter,
    ProviderError,
    UniversalMessage,
    UniversalRequest,
    UniversalResponse,
    looks_like_quota_error,
)
from .router import (
    DEFAULT_ENDPOINTS,
    get_adapter,
    get_default_endpoint,
    resolve_credentials,
    call_chat,
    acall_chat,
    is_quota_error,
)

__all__ = [
    "BaseAdapter",
    "ProviderError",
    "UniversalMessage",
    "UniversalRequest",
    "UniversalResponse",
    "looks_like_quota_error",
    "DEFAULT_ENDPOINTS",
    "get_adapter",
    "get_default_endpoint",
    "resolve_credentials",
    "call_chat",
    "acall_chat",
    "is_quota_error",
    "router",
    "base",
]
