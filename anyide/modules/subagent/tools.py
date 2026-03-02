"""Subagent module tool implementations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from anyide.config import SubagentsConfig, SubagentTypeConfig
from anyide.core.llm_client import LLMClientError
from anyide.modules.subagent.schemas import (
    SubagentListResponse,
    SubagentRunRequest,
    SubagentRunResponse,
    SubagentTypeInfo,
)


class SubagentTools:
    """Tools that expose configured single-turn subagent executions."""

    TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

    def __init__(
        self,
        subagents_config: SubagentsConfig,
        llm_client: Any,
    ):
        self._subagents_config = subagents_config
        self._llm_client = llm_client
        self._module_dir = Path(__file__).resolve().parent
        self._prompts_dir = self._module_dir / "prompts"

    async def list(self) -> SubagentListResponse:
        """Return configured subagent type metadata."""
        types: list[SubagentTypeInfo] = []

        for type_id, subagent in sorted(self._subagents_config.types.items()):
            types.append(
                SubagentTypeInfo(
                    type_id=type_id,
                    display_name=subagent.display_name,
                    description=subagent.description,
                    llm_endpoint=subagent.llm_endpoint,
                    model=subagent.model,
                )
            )

        return SubagentListResponse(types=types, total=len(types))

    async def run(self, request: SubagentRunRequest) -> SubagentRunResponse:
        """Execute one configured subagent as a single LLM completion."""
        if self._llm_client is None:
            raise ValueError("LLM client is not configured")

        subagent = self._resolve_subagent(request.type)

        model = subagent.model
        if request.override_model:
            if not subagent.allow_model_override:
                raise ValueError(
                    f"override_model is disabled for subagent type '{request.type}'"
                )
            model = request.override_model

        temperature = subagent.temperature
        if request.override_temperature is not None:
            if not subagent.allow_temperature_override:
                raise ValueError(
                    f"override_temperature is disabled for subagent type '{request.type}'"
                )
            temperature = request.override_temperature

        prompt_template = self._load_prompt_template(subagent.system_prompt_file)
        rendered_prompt = self._render_prompt_template(
            prompt_template,
            {
                "type": request.type,
                "input": request.input,
                "context": request.context or "",
            },
        )

        user_content = request.input
        if request.context:
            user_content = f"{request.input}\n\nContext:\n{request.context}"

        messages = [
            {"role": "system", "content": rendered_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self._llm_client.complete(
                endpoint_id=subagent.llm_endpoint,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=subagent.max_tokens,
                response_format=subagent.response_format,
            )
        except LLMClientError as exc:
            self._raise_execution_error(request.type, subagent.llm_endpoint, exc)

        return SubagentRunResponse(
            type=request.type,
            model_used=response.model,
            endpoint_used=response.endpoint_id,
            response=response.content,
            usage=response.usage,
            latency_ms=response.latency_ms,
            response_format=subagent.response_format,
        )

    def _resolve_subagent(self, type_id: str) -> SubagentTypeConfig:
        normalized = type_id.strip()
        subagent = self._subagents_config.types.get(normalized)
        if subagent is None:
            available = sorted(self._subagents_config.types.keys())
            raise ValueError(
                f"Unknown subagent type '{normalized}'. Available: {available}"
            )
        return subagent

    def _load_prompt_template(self, prompt_path: str) -> str:
        resolved_path = self._resolve_prompt_path(prompt_path)
        try:
            return resolved_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Prompt template file not found: {resolved_path}"
            ) from exc

    def _resolve_prompt_path(self, prompt_path: str) -> Path:
        raw_path = prompt_path.strip()
        if not raw_path:
            raise ValueError("system_prompt_file must not be blank")

        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate

        options = [
            (self._module_dir / candidate).resolve(),
            (self._prompts_dir / candidate).resolve(),
            (self._prompts_dir / candidate.name).resolve(),
        ]

        for option in options:
            if option.is_file() and self._is_within(option, self._module_dir):
                return option

        # Return the first safe candidate so caller error contains deterministic path.
        for option in options:
            if self._is_within(option, self._module_dir):
                return option

        raise ValueError(
            "system_prompt_file resolves outside the subagent module directory"
        )

    def _is_within(self, path: Path, base: Path) -> bool:
        try:
            path.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False

    def _render_prompt_template(self, template: str, values: dict[str, str]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(values.get(key, match.group(0)))

        return self.TEMPLATE_PATTERN.sub(replace, template)

    def _raise_execution_error(
        self,
        type_id: str,
        endpoint_id: str,
        exc: LLMClientError,
    ) -> None:
        message = (
            f"Subagent '{type_id}' failed via endpoint '{endpoint_id}': {exc.message}"
        )
        if exc.error_type in {"connection_error", "timeout", "rate_limit"}:
            raise ConnectionError(message) from exc
        if exc.error_type in {
            "config_error",
            "secret_not_found",
            "authentication_error",
            "permission_error",
        }:
            raise ValueError(message) from exc
        raise RuntimeError(message) from exc
