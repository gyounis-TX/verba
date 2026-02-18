"""
LLM client abstraction supporting Claude (primary) and OpenAI (secondary).

Both providers use their respective structured output mechanisms:
- Claude: tool_use (tools parameter)
- OpenAI: function calling (tools parameter with type "function")

BAA (Business Associate Agreement) compliance:
  Vendors with signed BAAs: bedrock (AWS BAA covers Bedrock).
  In production (REQUIRE_AUTH=true), only BAA-covered providers may be used.
  Set BAA_PROVIDERS env var to override (comma-separated provider names).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Providers with signed BAAs — only these may transmit PHI in production.
_BAA_PROVIDERS: set[str] = set(
    p.strip().lower()
    for p in os.getenv("BAA_PROVIDERS", "bedrock").split(",")
    if p.strip()
)
_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"

CLAUDE_DEEP_MODEL = "claude-opus-4-20250514"

# Mapping from Anthropic model IDs to Bedrock inference profile IDs.
# Bedrock requires inference profile IDs (with regional prefix) for on-demand use.
_BEDROCK_MODEL_MAP = {
    "claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
    "claude-sonnet-4-5": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-sonnet-4-20250514": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "claude-opus-4-20250514": "us.anthropic.claude-opus-4-20250514-v1:0",
    "claude-haiku-4-5-20251001": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-haiku-4-20250514": "us.anthropic.claude-haiku-4-20250514-v1:0",
    "claude-3-5-sonnet-20241022": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-5-haiku-20241022": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
}

# Region prefix mapping for inference profiles
_BEDROCK_REGION_PREFIX = {
    "us-east-1": "us",
    "us-east-2": "us",
    "us-west-2": "us",
    "eu-west-1": "eu",
    "eu-central-1": "eu",
    "ap-northeast-1": "ap",
    "ap-southeast-1": "ap",
}


def _to_bedrock_model_id(model: str, region: str = "us-east-1") -> str:
    """Convert an Anthropic model ID to its Bedrock inference profile ID."""
    # Already a Bedrock inference profile ID (has region prefix like "us." or "eu.")
    if model[:3] in ("us.", "eu.", "ap.") and "anthropic." in model:
        return model
    # Already a bare Bedrock model ID — add region prefix
    if "anthropic." in model and not model.startswith(("us.", "eu.", "ap.")):
        prefix = _BEDROCK_REGION_PREFIX.get(region, "us")
        return f"{prefix}.{model}"
    # Look up in our mapping
    if model in _BEDROCK_MODEL_MAP:
        profile_id = _BEDROCK_MODEL_MAP[model]
        # Replace the "us." prefix with the correct region prefix
        prefix = _BEDROCK_REGION_PREFIX.get(region, "us")
        return f"{prefix}.{profile_id[3:]}"
    # Best-effort: wrap in Bedrock format with region prefix
    prefix = _BEDROCK_REGION_PREFIX.get(region, "us")
    return f"{prefix}.anthropic.{model}-v1:0"


class LLMProvider(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    BEDROCK = "bedrock"


@dataclass
class LLMResponse:
    """Raw response from an LLM API call."""

    provider: LLMProvider
    raw_content: str
    tool_call_result: Optional[dict]
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def text_content(self) -> str:
        """Return the plain text content of the response."""
        return self.raw_content


class LLMClient:
    """Unified LLM client. Instantiated per-request with settings."""

    def __init__(
        self,
        provider: LLMProvider,
        api_key: str | dict,
        model: Optional[str] = None,
    ):
        # BAA guard: in production, block providers without a signed BAA
        if _REQUIRE_AUTH and provider.value.lower() not in _BAA_PROVIDERS:
            raise ValueError(
                f"Provider '{provider.value}' is not BAA-compliant. "
                f"Allowed providers: {', '.join(sorted(_BAA_PROVIDERS))}. "
                f"Set BAA_PROVIDERS env var to update."
            )
        self.provider = provider
        self.api_key = api_key
        self.model = model or self._default_model()

    def _default_model(self) -> str:
        if self.provider == LLMProvider.CLAUDE:
            return "claude-sonnet-4-6"
        if self.provider == LLMProvider.BEDROCK:
            return "claude-sonnet-4-6"
        return "gpt-4.1-mini"

    async def call_with_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        media_type: str = "image/png",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send an image + text prompt and return a plain text response."""
        if self.provider == LLMProvider.CLAUDE:
            return await self._call_claude_vision(
                system_prompt, user_prompt, image_bytes, media_type,
                max_tokens, temperature,
            )
        elif self.provider == LLMProvider.BEDROCK:
            return await self._call_bedrock_vision(
                system_prompt, user_prompt, image_bytes, media_type,
                max_tokens, temperature,
            )
        else:
            return await self._call_openai_vision(
                system_prompt, user_prompt, image_bytes, media_type,
                max_tokens, temperature,
            )

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Send a prompt and return a plain text response (no tool use)."""
        if self.provider == LLMProvider.CLAUDE:
            return await self._call_claude_text(
                system_prompt, user_prompt, max_tokens, temperature,
            )
        elif self.provider == LLMProvider.BEDROCK:
            return await self._call_bedrock_text(
                system_prompt, user_prompt, max_tokens, temperature,
            )
        else:
            return await self._call_openai_text(
                system_prompt, user_prompt, max_tokens, temperature,
            )

    async def call_with_tool(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Send a prompt and force a structured tool_use/function_call response."""
        if self.provider == LLMProvider.CLAUDE:
            return await self._call_claude(
                system_prompt,
                user_prompt,
                tool_name,
                tool_schema,
                max_tokens,
                temperature,
            )
        elif self.provider == LLMProvider.BEDROCK:
            return await self._call_bedrock(
                system_prompt,
                user_prompt,
                tool_name,
                tool_schema,
                max_tokens,
                temperature,
            )
        else:
            return await self._call_openai(
                system_prompt,
                user_prompt,
                tool_name,
                tool_schema,
                max_tokens,
                temperature,
            )

    async def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "name": tool_name,
                    "description": (
                        "Generate structured medical report explanation"
                    ),
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )

        tool_result = None
        raw_text = ""

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                tool_result = block.input
            elif block.type == "text":
                raw_text = block.text

        return LLMResponse(
            provider=LLMProvider.CLAUDE,
            raw_content=raw_text,
            tool_call_result=tool_result,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import json

        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": (
                            "Generate structured medical report explanation"
                        ),
                        "parameters": tool_schema,
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": tool_name},
            },
        )

        choice = response.choices[0]
        tool_result = None
        raw_text = choice.message.content or ""

        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            tool_result = json.loads(tc.function.arguments)

        return LLMResponse(
            provider=LLMProvider.OPENAI,
            raw_content=raw_text,
            tool_call_result=tool_result,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    async def _call_claude_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = ""
        for block in response.content:
            if block.type == "text":
                raw_text += block.text

        return LLMResponse(
            provider=LLMProvider.CLAUDE,
            raw_content=raw_text,
            tool_call_result=None,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def _call_openai_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        choice = response.choices[0]
        raw_text = choice.message.content or ""

        return LLMResponse(
            provider=LLMProvider.OPENAI,
            raw_content=raw_text,
            tool_call_result=None,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    def _get_bedrock_client(self):
        """Create a boto3 Bedrock Runtime client from the stored credentials.

        When access_key is "iam_role", creates the client without explicit
        credentials so boto3 uses the default credential chain (ECS task role,
        instance profile, etc.).
        """
        import boto3

        creds = self.api_key  # dict with access_key, secret_key, region
        if not isinstance(creds, dict):
            raise ValueError("Bedrock provider requires AWS credentials dict")

        region = creds.get("region", "us-east-1")

        # IAM role mode: let boto3 discover credentials from environment
        if creds.get("access_key") == "iam_role":
            return boto3.client(
                "bedrock-runtime",
                region_name=region,
            )

        return boto3.client(
            "bedrock-runtime",
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            region_name=region,
        )

    @staticmethod
    def _bedrock_tool_schema_to_converse(tool_name: str, tool_schema: dict[str, Any]) -> dict:
        """Convert our tool schema to Bedrock Converse API toolSpec format."""
        return {
            "toolSpec": {
                "name": tool_name,
                "description": "Generate structured medical report explanation",
                "inputSchema": {
                    "json": tool_schema,
                },
            }
        }

    async def _call_bedrock(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import asyncio

        bedrock = self._get_bedrock_client()
        region = self.api_key.get("region", "us-east-1") if isinstance(self.api_key, dict) else "us-east-1"
        model_id = _to_bedrock_model_id(self.model, region)

        tool_config = {
            "tools": [self._bedrock_tool_schema_to_converse(tool_name, tool_schema)],
            "toolChoice": {"tool": {"name": tool_name}},
        }

        def _invoke():
            return bedrock.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=tool_config,
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _invoke)

        tool_result = None
        raw_text = ""

        for block in response["output"]["message"]["content"]:
            if "toolUse" in block and block["toolUse"]["name"] == tool_name:
                tool_result = block["toolUse"]["input"]
            elif "text" in block:
                raw_text = block["text"]

        usage = response.get("usage", {})
        return LLMResponse(
            provider=LLMProvider.BEDROCK,
            raw_content=raw_text,
            tool_call_result=tool_result,
            model=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )

    async def _call_bedrock_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import asyncio

        bedrock = self._get_bedrock_client()
        region = self.api_key.get("region", "us-east-1") if isinstance(self.api_key, dict) else "us-east-1"
        model_id = _to_bedrock_model_id(self.model, region)

        def _invoke():
            return bedrock.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _invoke)

        raw_text = ""
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                raw_text += block["text"]

        usage = response.get("usage", {})
        return LLMResponse(
            provider=LLMProvider.BEDROCK,
            raw_content=raw_text,
            tool_call_result=None,
            model=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )

    # ── Vision methods ──────────────────────────────────────────────

    async def _call_claude_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        media_type: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import base64

        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }],
        )

        raw_text = ""
        for block in response.content:
            if block.type == "text":
                raw_text += block.text

        return LLMResponse(
            provider=LLMProvider.CLAUDE,
            raw_content=raw_text,
            tool_call_result=None,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def _call_bedrock_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        media_type: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import asyncio

        bedrock = self._get_bedrock_client()
        region = self.api_key.get("region", "us-east-1") if isinstance(self.api_key, dict) else "us-east-1"
        model_id = _to_bedrock_model_id(self.model, region)

        # Map MIME type to Bedrock image format
        fmt_map = {
            "image/png": "png",
            "image/jpeg": "jpeg",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        img_format = fmt_map.get(media_type, "png")

        def _invoke():
            return bedrock.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{
                    "role": "user",
                    "content": [
                        {"image": {"format": img_format, "source": {"bytes": image_bytes}}},
                        {"text": user_prompt},
                    ],
                }],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _invoke)

        raw_text = ""
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                raw_text += block["text"]

        usage = response.get("usage", {})
        return LLMResponse(
            provider=LLMProvider.BEDROCK,
            raw_content=raw_text,
            tool_call_result=None,
            model=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )

    async def _call_openai_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        media_type: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import base64

        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)
        b64_data = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{media_type};base64,{b64_data}"

        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
        )

        choice = response.choices[0]
        raw_text = choice.message.content or ""

        return LLMResponse(
            provider=LLMProvider.OPENAI,
            raw_content=raw_text,
            tool_call_result=None,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
