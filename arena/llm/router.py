"""统一路由：根据 AIConfig.api_type 选择合适的 Adapter 并执行调用。

上层只需要：
    from arena.llm import router
    resp = router.call(config, system, user)
"""

from __future__ import annotations

from typing import Optional

from .base import (
    BaseAdapter,
    OpenAICompatAdapter,
    AnthropicAdapter,
    GeminiAdapter,
    BaiduAdapter,
    HunyuanAdapter,
    ZhipuAdapter,
    StepFunAdapter,
    CustomAdapter,
    ProviderError,
    UniversalRequest,
    UniversalResponse,
    UniversalMessage,
)
from ..models import AIConfig, ApiType, ModelStatus
from ..storage import Storage


# ─── 默认端点（与原 apiKeyManager 保持一致） ───

DEFAULT_ENDPOINTS: dict[ApiType, str] = {
    ApiType.OPENAI: "https://api.openai.com/v1/chat/completions",
    ApiType.ANTHROPIC: "https://api.anthropic.com/v1/messages",
    ApiType.GOOGLE: "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ApiType.VOLCENGINE: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    ApiType.BAIDU: "https://qianfan.baidubce.com/v2/chat/completions",
    ApiType.ALIBABA: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    ApiType.HUNYUAN: "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
    ApiType.MOONSHOT: "https://api.moonshot.cn/v1/chat/completions",
    ApiType.ZHIPU: "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    ApiType.STEPFUN: "https://api.stepfun.com/v1/chat/completions",
}


def get_default_endpoint(api_type: ApiType) -> str:
    return DEFAULT_ENDPOINTS.get(api_type, "")


# ─── 适配器注册表 ───

ADAPTERS: dict[ApiType, BaseAdapter] = {
    ApiType.OPENAI: OpenAICompatAdapter(),
    ApiType.ANTHROPIC: AnthropicAdapter(),
    ApiType.GOOGLE: GeminiAdapter(),
    ApiType.VOLCENGINE: OpenAICompatAdapter(),  # 豆包走 OpenAI 协议
    ApiType.BAIDU: BaiduAdapter(),
    ApiType.ALIBABA: OpenAICompatAdapter(),      # 通义兼容模式走 OpenAI
    ApiType.HUNYUAN: HunyuanAdapter(),
    ApiType.MOONSHOT: OpenAICompatAdapter(),     # Moonshot 走 OpenAI
    ApiType.ZHIPU: ZhipuAdapter(),
    ApiType.STEPFUN: StepFunAdapter(),
    ApiType.CUSTOM: CustomAdapter(),
}


def get_adapter(api_type: ApiType) -> BaseAdapter:
    return ADAPTERS.get(api_type) or CustomAdapter()


# ─── 凭证解析（与原 apiKeyManager 行为一致） ───

def resolve_credentials(
    config: AIConfig,
    storage: Optional[Storage] = None,
) -> tuple[str, str]:
    """返回 (api_key, endpoint)。优先使用全局配置，回退到模型自带。"""
    if config.api_type == ApiType.CUSTOM:
        return config.api_key, config.endpoint

    if storage is not None:
        g = storage.get_api_key(config.api_type)
        if g:
            api_key = g.api_key.strip() or config.api_key
            endpoint = (
                g.endpoint.strip()
                or config.endpoint
                or DEFAULT_ENDPOINTS.get(config.api_type, "")
            )
            return api_key, endpoint

    return config.api_key, config.endpoint or DEFAULT_ENDPOINTS.get(config.api_type, "")


# ─── 高层调用 API ───

def call_chat(
    config: AIConfig,
    system_prompt: str,
    user_prompt: str,
    storage: Optional[Storage] = None,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> UniversalResponse:
    """同步调用单个模型。返回归一化响应。"""
    api_key, endpoint = resolve_credentials(config, storage)
    if not api_key:
        raise ProviderError(
            status=0,
            body=f"未配置 {config.api_type.value} 的 API Key",
        )

    messages: list[UniversalMessage] = []
    if system_prompt:
        messages.append(UniversalMessage("system", system_prompt))
    messages.append(UniversalMessage("user", user_prompt))

    req = UniversalRequest(
        model=config.model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    adapter = get_adapter(config.api_type)
    return adapter.call(api_key, endpoint, req, timeout=timeout)


async def acall_chat(
    config: AIConfig,
    system_prompt: str,
    user_prompt: str,
    storage: Optional[Storage] = None,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> UniversalResponse:
    """异步调用单个模型。"""
    api_key, endpoint = resolve_credentials(config, storage)
    if not api_key:
        raise ProviderError(
            status=0,
            body=f"未配置 {config.api_type.value} 的 API Key",
        )

    messages: list[UniversalMessage] = []
    if system_prompt:
        messages.append(UniversalMessage("system", system_prompt))
    messages.append(UniversalMessage("user", user_prompt))

    req = UniversalRequest(
        model=config.model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    adapter = get_adapter(config.api_type)
    return await adapter.acall(api_key, endpoint, req, timeout=timeout)


def is_quota_error(err: ProviderError) -> bool:
    return err.is_quota
