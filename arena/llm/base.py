"""统一 LLM 协议层 — 核心抽象。

设计目标：把"不同厂商的私有 API 协议"在本地归一化为一套
`UniversalRequest` / `UniversalResponse`，并在请求 / 响应时由各 ProviderAdapter
做前向（归一化 -> 厂商协议）和反向（厂商协议 -> 归一化）翻译。

调用方（裁判 / 竞技场）只跟 `UniversalRequest` / `UniversalResponse` 打交道，
完全不知道底下是 OpenAI、Anthropic 还是文心一言。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..models import ApiType, ModelStatus


# ─── 归一化数据结构 ───

@dataclass
class UniversalMessage:
    role: str          # "system" | "user" | "assistant"
    content: str


@dataclass
class UniversalRequest:
    """所有厂商的请求最终都先归一化成这个结构。"""
    model: str
    messages: list[UniversalMessage]
    temperature: float = 0.7
    max_tokens: int = 4096
    # 透传给厂商的特殊字段（不同厂商支持不同，例如 Anthropic 的 top_k、Vertex 的 safety_settings）
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class UniversalResponse:
    """所有厂商的响应都先反归一化成这个结构再交给上层。"""
    content: str
    usage: Optional[dict[str, int]] = None
    raw: Optional[dict[str, Any]] = None  # 保留厂商原始响应，便于调试


@dataclass
class ProviderError(Exception):
    """统一的厂商异常。"""

    status: int
    body: str
    is_quota: bool = False

    def __str__(self) -> str:
        return f"[{self.status}] {self.body[:300]}"


# ─── 额度耗尽关键字（中英文） ───
# 收紧正则：避免把一般 4xx 误判为额度问题。关键词要"明确语义"，
# 不再用宽泛的 "quota / balance / exceeded / rate" 等。

QUOTA_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 明确额度类
    ("insufficient_quota", re.compile(r"insufficient[_\s-]?quota", re.I)),
    ("insufficient_balance", re.compile(r"insufficient[_\s-]?balance", re.I)),
    ("quota_exceeded", re.compile(r"quota[_\s-]?exceeded", re.I)),
    ("billing_hard_limit", re.compile(r"billing[_\s-]?hard[_\s-]?limit", re.I)),
    ("billing_not_active", re.compile(r"billing[_\s-]?(?:not[_\s-]?active|disabled|issue)", re.I)),
    ("resource_exhausted", re.compile(r"resource[_\s-]?exhausted", re.I)),
    ("rate_limit_exceeded", re.compile(r"rate[_\s-]?limit[_\s-]?exceeded", re.I)),
    ("spending_limit", re.compile(r"spending[_\s-]?limit", re.I)),
    ("payment_required", re.compile(r"payment[_\s-]?required", re.I)),
    # 中文
    ("余额不足", re.compile(r"余额不足|额度不足|欠费|已欠费|账户余额不足|超限|超出限制|超额度", re.I)),
    # Anthropic 特有
    ("anthropic_quota", re.compile(r"you[_\s-]?(?:exceeded|hit).{0,30}?(?:quota|usage|tokens|requests)", re.I)),
]


def looks_like_quota_error(status: int, body: str) -> bool:
    """判断响应是否表示"额度耗尽"或"计费问题"。

    - HTTP 402/429 → 视为额度/限流问题
    - HTTP 200/201/4xx 其它：需要看 body 关键字
    """
    if status in (402, 429):
        return True
    # body 必须是错误响应里的 JSON 文本才检查（避免误把正常消息里的 "balance" 之类的词算上）
    if status < 400:
        return False
    for _, pat in QUOTA_PATTERNS:
        if pat.search(body):
            return True
    return False


# ─── 适配器基类 ───

class BaseAdapter:
    """所有厂商适配器继承此类。"""

    api_type: ApiType = ApiType.CUSTOM
    default_endpoint: str = ""
    # 厂商是否支持 `{model}` 占位符（如 Google Gemini）
    uses_model_placeholder: bool = False

    def build_headers(self, api_key: str) -> dict[str, str]:
        """构造 HTTP 头。"""
        return {"Content-Type": "application/json"}

    def resolve_endpoint(self, endpoint: str, model: str) -> str:
        """处理 `{model}` 占位符等。"""
        if self.uses_model_placeholder:
            return endpoint.replace("{model}", model)
        return endpoint

    # ── 前向：归一化 -> 厂商私有 payload ──

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        raise NotImplementedError

    # ── 反向：厂商私有 payload -> 归一化 ──

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        raise NotImplementedError

    # ── HTTP 调用 ──

    def call(
        self,
        api_key: str,
        endpoint: str,
        req: UniversalRequest,
        timeout: float = 120.0,
    ) -> UniversalResponse:
        url = self.resolve_endpoint(endpoint or self.default_endpoint, req.model)
        headers = self.build_headers(api_key)
        body = self.to_provider_payload(req)

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise ProviderError(status=0, body=str(e)) from e

        text = resp.text
        if not resp.is_success:
            raise ProviderError(
                status=resp.status_code,
                body=text,
                is_quota=looks_like_quota_error(resp.status_code, text),
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise ProviderError(status=resp.status_code, body=f"Invalid JSON: {text[:200]}") from e

        return self.from_provider_payload(data)

    async def acall(
        self,
        api_key: str,
        endpoint: str,
        req: UniversalRequest,
        timeout: float = 120.0,
    ) -> UniversalResponse:
        url = self.resolve_endpoint(endpoint or self.default_endpoint, req.model)
        headers = self.build_headers(api_key)
        body = self.to_provider_payload(req)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise ProviderError(status=0, body=str(e)) from e

        text = resp.text
        if not resp.is_success:
            raise ProviderError(
                status=resp.status_code,
                body=text,
                is_quota=looks_like_quota_error(resp.status_code, text),
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise ProviderError(status=resp.status_code, body=f"Invalid JSON: {text[:200]}") from e

        return self.from_provider_payload(data)


# ─── OpenAI 兼容协议 ───

class OpenAICompatAdapter(BaseAdapter):
    """OpenAI Chat Completions 协议。

    大多数国内厂商（豆包/通义/混元/Kimi/智谱/阶跃/OpenRouter/DeepSeek 等）
    走的都是这一套。所以我们以这个为基础，把其他厂商分别做小幅定制。
    """

    api_type: ApiType = ApiType.OPENAI
    default_endpoint: str = "https://api.openai.com/v1/chat/completions"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            **req.extras,
        }

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        choices = payload.get("choices") or []
        content = ""
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content") or ""
        if not content:
            content = payload.get("content") or payload.get("data", {}).get("answer") or ""
        return UniversalResponse(
            content=content,
            usage=payload.get("usage"),
            raw=payload,
        )


# ─── Anthropic Claude ───

class AnthropicAdapter(BaseAdapter):
    api_type: ApiType = ApiType.ANTHROPIC
    default_endpoint: str = "https://api.anthropic.com/v1/messages"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        # Anthropic 把 system 单独抽出来
        system_parts: list[str] = []
        msgs: list[dict[str, str]] = []
        for m in req.messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                msgs.append({"role": m.role, "content": m.content})
        payload: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": msgs,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        payload.update(req.extras)
        return payload

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        content_blocks = payload.get("content") or []
        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        if not text and isinstance(content_blocks, list) and content_blocks:
            first = content_blocks[0]
            if isinstance(first, dict):
                text = first.get("text", "")
        return UniversalResponse(
            content=text,
            usage=payload.get("usage"),
            raw=payload,
        )


# ─── Google Gemini ───

class GeminiAdapter(BaseAdapter):
    api_type: ApiType = ApiType.GOOGLE
    default_endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    uses_model_placeholder: bool = True

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in req.messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": req.temperature,
                "maxOutputTokens": req.max_tokens,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        payload.update(req.extras)
        return payload

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        candidates = payload.get("candidates") or []
        text = ""
        if candidates:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            if parts:
                text = parts[0].get("text", "")
        return UniversalResponse(
            content=text,
            usage=payload.get("usageMetadata"),
            raw=payload,
        )


# ─── 百度文心一言（qianfan V2） ───

class BaiduAdapter(BaseAdapter):
    """百度千帆 V2 ChatCompletion 协议。"""

    api_type: ApiType = ApiType.BAIDU
    default_endpoint: str = "https://qianfan.baidubce.com/v2/chat/completions"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            **req.extras,
        }

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        # 千帆 V2 形态与 OpenAI 一致
        choices = payload.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
        return UniversalResponse(content=content, usage=payload.get("usage"), raw=payload)


# ─── 腾讯混元 ───

class HunyuanAdapter(BaseAdapter):
    """腾讯混元 ChatCompletions — 与 OpenAI 类似，但需 TencentYpHeader 鉴权头（新版已支持 Bearer）。"""

    api_type: ApiType = ApiType.HUNYUAN
    default_endpoint: str = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            **req.extras,
        }

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        # 形态与 OpenAI 一致
        choices = payload.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
        return UniversalResponse(content=content, usage=payload.get("usage"), raw=payload)


# ─── 智谱 GLM ───

class ZhipuAdapter(BaseAdapter):
    """智谱 BigModel 开放平台 — OpenAI 兼容。"""

    api_type: ApiType = ApiType.ZHIPU
    default_endpoint: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            **req.extras,
        }

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        choices = payload.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
        return UniversalResponse(content=content, usage=payload.get("usage"), raw=payload)


# ─── 阶跃星辰 ───

class StepFunAdapter(BaseAdapter):
    """阶跃星辰 — OpenAI 兼容。"""

    api_type: ApiType = ApiType.STEPFUN
    default_endpoint: str = "https://api.stepfun.com/v1/chat/completions"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def to_provider_payload(self, req: UniversalRequest) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            **req.extras,
        }

    def from_provider_payload(self, payload: dict[str, Any]) -> UniversalResponse:
        choices = payload.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
        return UniversalResponse(content=content, usage=payload.get("usage"), raw=payload)


# ─── 自定义（透传 OpenAI 形态） ───

class CustomAdapter(OpenAICompatAdapter):
    api_type: ApiType = ApiType.CUSTOM
    default_endpoint: str = ""
