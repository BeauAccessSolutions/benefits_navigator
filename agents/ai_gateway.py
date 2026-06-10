"""
AI Gateway - Centralized Anthropic (Claude) API interface for Benefits Navigator.

This module provides a single entry point for all Claude API calls with:
- Timeout handling (120s default, configurable)
- Retry with exponential backoff (3 retries by default; SDK retries disabled
  so the gateway owns the retry policy)
- Schema-enforced structured outputs via messages.parse() + Pydantic
- Result types for error handling (no exceptions raised to callers)
- Consolidated input sanitization
- Centralized token/cost tracking
- Prompt caching on system prompts (cache_control ephemeral)
- PII-safe logging
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Callable, Generic, Optional, TypeVar

from django.conf import settings
from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')


# =============================================================================
# ERROR TYPES
# =============================================================================

class ErrorCode(Enum):
    """Standard error codes for AI gateway operations."""
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    API_ERROR = "api_error"
    VALIDATION_ERROR = "validation_error"
    PARSE_ERROR = "parse_error"
    SANITIZATION_ERROR = "sanitization_error"
    UNKNOWN = "unknown"


@dataclass
class GatewayError:
    """Structured error from AI gateway operations."""
    code: ErrorCode
    message: str
    retryable: bool
    details: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'code': self.code.value,
            'message': self.message,
            'retryable': self.retryable,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
        }


# =============================================================================
# RESULT TYPE
# =============================================================================

@dataclass
class Result(Generic[T]):
    """
    Result type for gateway operations.

    Either contains a success value or an error, never both.
    Callers should check is_success before accessing value.

    Usage:
        result = gateway.complete(...)
        if result.is_success:
            process(result.value)
        else:
            handle_error(result.error)
    """
    _value: Optional[T] = None
    _error: Optional[GatewayError] = None
    tokens_used: int = 0
    cost_estimate: Decimal = Decimal('0')
    duration_ms: int = 0

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_failure(self) -> bool:
        return self._error is not None

    @property
    def value(self) -> T:
        if self._error is not None:
            raise ValueError(f"Cannot access value on failed result: {self._error.message}")
        return self._value

    @property
    def error(self) -> GatewayError:
        if self._error is None:
            raise ValueError("Cannot access error on successful result")
        return self._error

    @classmethod
    def success(
        cls,
        value: T,
        tokens: int = 0,
        cost: Decimal = Decimal('0'),
        duration_ms: int = 0
    ) -> 'Result[T]':
        return cls(_value=value, tokens_used=tokens, cost_estimate=cost, duration_ms=duration_ms)

    @classmethod
    def failure(
        cls,
        error: GatewayError,
        tokens: int = 0,
        duration_ms: int = 0
    ) -> 'Result[T]':
        return cls(_error=error, tokens_used=tokens, duration_ms=duration_ms)

    def map(self, fn: Callable[[T], U]) -> 'Result[U]':
        """Transform the value if successful, propagate error if not."""
        if self.is_success:
            try:
                return Result.success(
                    fn(self._value),
                    self.tokens_used,
                    self.cost_estimate,
                    self.duration_ms
                )
            except Exception as e:
                return Result.failure(GatewayError(
                    code=ErrorCode.UNKNOWN,
                    message=str(e),
                    retryable=False
                ))
        return Result.failure(self._error, self.tokens_used, self.duration_ms)


# =============================================================================
# RESPONSE TYPES
# =============================================================================

@dataclass
class CompletionResponse:
    """Raw completion response from OpenAI."""
    content: str
    tokens_used: int
    model: str
    finish_reason: str


@dataclass
class StructuredResponse(Generic[T]):
    """Structured response validated against a Pydantic schema."""
    data: T
    tokens_used: int
    model: str
    raw_content: str


# =============================================================================
# INPUT SANITIZATION
# =============================================================================

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "forget previous",
    "new instructions:",
    "system prompt:",
    "you are now",
    "act as",
    "pretend to be",
    "roleplay as",
    "ignore the above",
    "ignore everything above",
    "do not follow",
    "override",
    "bypass",
]


def sanitize_input(text: str) -> str:
    """
    Sanitize user-provided text to prevent prompt injection attacks.

    This function:
    1. Removes/redacts common prompt injection patterns
    2. Preserves legitimate document content
    3. Does NOT log the input (may contain PII)

    Args:
        text: User-provided text (may contain PII, document content)

    Returns:
        Sanitized text safe for inclusion in prompts
    """
    if not text:
        return ""

    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in text_lower:
            # Replace with redaction marker
            text = re.sub(
                re.escape(pattern),
                f"[REDACTED: {pattern[:10]}...]",
                text,
                flags=re.IGNORECASE
            )

    return text


# =============================================================================
# GATEWAY CONFIGURATION
# =============================================================================

@dataclass
class GatewayConfig:
    """Configuration for AI Gateway."""
    model: str = "claude-opus-4-8"
    max_tokens: int = 8192
    # Retained for call-site compatibility; Claude 4.7+ models do not accept
    # sampling parameters, so this value is never sent to the API.
    default_temperature: float = 0.3
    adaptive_thinking: bool = True
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0

    @classmethod
    def from_settings(cls) -> 'GatewayConfig':
        """Create config from Django settings."""
        return cls(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-opus-4-8'),
            max_tokens=getattr(settings, 'ANTHROPIC_MAX_TOKENS', 8192),
            adaptive_thinking=getattr(settings, 'ANTHROPIC_ADAPTIVE_THINKING', True),
            timeout_seconds=getattr(settings, 'ANTHROPIC_TIMEOUT_SECONDS', 120),
            max_retries=getattr(settings, 'ANTHROPIC_MAX_RETRIES', 3),
            retry_base_delay=getattr(settings, 'ANTHROPIC_RETRY_BASE_DELAY', 1.0),
            retry_max_delay=getattr(settings, 'ANTHROPIC_RETRY_MAX_DELAY', 60.0),
        )


# =============================================================================
# AI GATEWAY
# =============================================================================

class AIGateway:
    """
    Centralized gateway for all OpenAI API calls.

    Features:
    - Single entry point for all AI operations
    - Automatic retry with exponential backoff
    - Timeout handling
    - Pydantic schema validation
    - Result types (no exceptions raised)
    - Token and cost tracking
    - PII-safe logging

    Usage:
        gateway = AIGateway()

        # Raw completion
        result = gateway.complete(
            system_prompt="You are a helpful assistant.",
            user_prompt="Analyze this document.",
        )

        # Structured completion with Pydantic validation
        result = gateway.complete_structured(
            system_prompt="Extract data as JSON.",
            user_prompt="Document text here.",
            response_schema=MyPydanticModel,
        )
    """

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig.from_settings()
        self._client: Optional[Anthropic] = None

    @property
    def client(self) -> Anthropic:
        """Lazy initialization of the Anthropic client."""
        if self._client is None:
            self._client = Anthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=self.config.timeout_seconds,
                # The gateway implements its own retry/backoff policy below;
                # disable SDK retries so attempts aren't multiplied.
                max_retries=0,
            )
        return self._client

    def _request_kwargs(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
    ) -> dict:
        """Build shared Messages API kwargs for complete()/complete_structured().

        The system prompt is marked cacheable: agent system prompts are large
        and identical across requests, so repeat calls read from the prompt
        cache. Claude 4.7+ models take no sampling parameters; thinking is
        adaptive (model decides per request) unless disabled in config.
        """
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_prompt}],
        )
        if self.config.adaptive_thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        return kwargs

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        sanitize: bool = True,
    ) -> Result[CompletionResponse]:
        """
        Make a chat completion request with retry and timeout handling.

        Args:
            system_prompt: System message (instructions)
            user_prompt: User message (may contain document content)
            temperature: Ignored — Claude 4.7+ models take no sampling
                parameters. Kept so existing call sites don't break.
            max_tokens: Override default max tokens
            model: Override default model
            sanitize: Whether to sanitize user_prompt (default True)

        Returns:
            Result containing CompletionResponse or GatewayError
        """
        start_time = time.time()

        # Sanitize user input if requested
        if sanitize:
            user_prompt = sanitize_input(user_prompt)

        model = model or self.config.model
        max_tokens = max_tokens or self.config.max_tokens

        last_error: Optional[Exception] = None
        tokens_used = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.messages.create(
                    **self._request_kwargs(system_prompt, user_prompt, model, max_tokens)
                )

                content = "".join(
                    block.text for block in response.content
                    if block.type == "text"
                )
                input_tokens = response.usage.input_tokens if response.usage else 0
                output_tokens = response.usage.output_tokens if response.usage else 0
                tokens_used = input_tokens + output_tokens
                finish_reason = response.stop_reason or "unknown"

                duration_ms = int((time.time() - start_time) * 1000)
                cost = self._estimate_cost(input_tokens, output_tokens, model)

                # Log success without PII
                logger.info(
                    f"AI completion successful: model={model} tokens={tokens_used} "
                    f"duration_ms={duration_ms}"
                )

                return Result.success(
                    CompletionResponse(
                        content=content,
                        tokens_used=tokens_used,
                        model=model,
                        finish_reason=finish_reason,
                    ),
                    tokens=tokens_used,
                    cost=cost,
                    duration_ms=duration_ms,
                )

            except APITimeoutError as e:
                last_error = e
                logger.warning(f"AI timeout (attempt {attempt + 1}/{self.config.max_retries + 1})")
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt)

            except RateLimitError as e:
                last_error = e
                logger.warning(f"AI rate limited (attempt {attempt + 1}/{self.config.max_retries + 1})")
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt, multiplier=2.0)

            except APIConnectionError as e:
                last_error = e
                logger.warning(
                    f"AI connection error (attempt {attempt + 1}/{self.config.max_retries + 1})"
                )
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt)

            except APIError as e:
                last_error = e
                logger.error(f"AI API error (attempt {attempt + 1}/{self.config.max_retries + 1}): {e}")
                if attempt < self.config.max_retries and self._is_retryable(e):
                    self._wait_with_backoff(attempt)
                else:
                    break

            except Exception as e:
                last_error = e
                # Type name only — stack traces could capture in-flight
                # document text (PII)
                logger.error(f"Unexpected AI error: {type(e).__name__}")
                break

        # All retries exhausted or non-retryable error
        duration_ms = int((time.time() - start_time) * 1000)
        error = self._create_error_from_exception(last_error)

        return Result.failure(error, tokens=tokens_used, duration_ms=duration_ms)

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        sanitize: bool = True,
    ) -> Result[StructuredResponse]:
        """
        Make a completion request and validate response against Pydantic schema.

        Uses the Anthropic SDK's messages.parse(), which enforces the schema
        at the API level (structured outputs) and validates the response
        against the Pydantic model — no markdown/JSON extraction needed.

        Args:
            system_prompt: System message
            user_prompt: User message
            response_schema: Pydantic model class for validation
            temperature: Ignored — kept for call-site compatibility
            model: Override default model
            sanitize: Whether to sanitize user_prompt

        Returns:
            Result containing validated StructuredResponse or GatewayError
        """
        start_time = time.time()

        if sanitize:
            user_prompt = sanitize_input(user_prompt)

        model = model or self.config.model
        max_tokens = self.config.max_tokens

        last_error: Optional[Exception] = None
        tokens_used = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.messages.parse(
                    output_format=response_schema,
                    **self._request_kwargs(system_prompt, user_prompt, model, max_tokens)
                )

                input_tokens = response.usage.input_tokens if response.usage else 0
                output_tokens = response.usage.output_tokens if response.usage else 0
                tokens_used = input_tokens + output_tokens
                duration_ms = int((time.time() - start_time) * 1000)

                validated = response.parsed_output
                if validated is None:
                    # Refusal or max_tokens truncation — schema not satisfiable
                    return Result.failure(
                        GatewayError(
                            code=ErrorCode.PARSE_ERROR,
                            message=(
                                f"No structured output returned "
                                f"(stop_reason={response.stop_reason})"
                            ),
                            retryable=response.stop_reason == "max_tokens",
                        ),
                        tokens=tokens_used,
                        duration_ms=duration_ms,
                    )

                raw_content = "".join(
                    block.text for block in response.content
                    if block.type == "text"
                )

                logger.info(
                    f"AI structured completion successful: model={model} "
                    f"tokens={tokens_used} duration_ms={duration_ms}"
                )

                return Result.success(
                    StructuredResponse(
                        data=validated,
                        tokens_used=tokens_used,
                        model=model,
                        raw_content=raw_content,
                    ),
                    tokens=tokens_used,
                    cost=self._estimate_cost(input_tokens, output_tokens, model),
                    duration_ms=duration_ms,
                )

            except ValidationError as e:
                return Result.failure(
                    GatewayError(
                        code=ErrorCode.VALIDATION_ERROR,
                        message=f"Response validation failed: {e}",
                        retryable=False,
                        details={'validation_errors': e.errors()},
                    ),
                    tokens=tokens_used,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except APITimeoutError as e:
                last_error = e
                logger.warning(f"AI timeout (attempt {attempt + 1}/{self.config.max_retries + 1})")
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt)

            except RateLimitError as e:
                last_error = e
                logger.warning(f"AI rate limited (attempt {attempt + 1}/{self.config.max_retries + 1})")
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt, multiplier=2.0)

            except APIConnectionError as e:
                last_error = e
                logger.warning(
                    f"AI connection error (attempt {attempt + 1}/{self.config.max_retries + 1})"
                )
                if attempt < self.config.max_retries:
                    self._wait_with_backoff(attempt)

            except APIError as e:
                last_error = e
                logger.error(f"AI API error (attempt {attempt + 1}/{self.config.max_retries + 1}): {e}")
                if attempt < self.config.max_retries and self._is_retryable(e):
                    self._wait_with_backoff(attempt)
                else:
                    break

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected AI error: {type(e).__name__}")
                break

        duration_ms = int((time.time() - start_time) * 1000)
        error = self._create_error_from_exception(last_error)
        return Result.failure(error, tokens=tokens_used, duration_ms=duration_ms)

    def _wait_with_backoff(self, attempt: int, multiplier: float = 1.0) -> None:
        """Wait with exponential backoff."""
        delay = min(
            self.config.retry_base_delay * (2 ** attempt) * multiplier,
            self.config.retry_max_delay
        )
        logger.info(f"Waiting {delay:.1f}s before retry")
        time.sleep(delay)

    def _is_retryable(self, error: APIError) -> bool:
        """Determine if an API error is retryable."""
        if isinstance(error, APIStatusError):
            # 5xx server errors + 529 (Anthropic overloaded)
            return error.status_code in {500, 502, 503, 504, 529}
        return False

    def _create_error_from_exception(self, exc: Exception) -> GatewayError:
        """Create a GatewayError from an exception."""
        if isinstance(exc, APITimeoutError):
            return GatewayError(
                code=ErrorCode.TIMEOUT,
                message="Request timed out after retries",
                retryable=True,
            )
        elif isinstance(exc, RateLimitError):
            return GatewayError(
                code=ErrorCode.RATE_LIMITED,
                message="Rate limit exceeded after retries",
                retryable=True,
            )
        elif isinstance(exc, APIConnectionError):
            return GatewayError(
                code=ErrorCode.API_ERROR,
                message="Connection to AI service failed after retries",
                retryable=True,
            )
        elif isinstance(exc, APIError):
            return GatewayError(
                code=ErrorCode.API_ERROR,
                message=str(exc),
                retryable=self._is_retryable(exc),
            )
        else:
            return GatewayError(
                code=ErrorCode.UNKNOWN,
                message=str(exc) if exc else "Unknown error",
                retryable=False,
            )

    def _estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> Decimal:
        """Estimate cost from input/output token usage.

        Rates are (input, output) USD per token. Cached-read discounts are
        not modeled — this slightly overestimates, which is the safe
        direction for budget tracking.
        """
        rates = {
            'claude-opus-4-8': (Decimal('0.000005'), Decimal('0.000025')),    # $5 / $25 per MTok
            'claude-sonnet-4-6': (Decimal('0.000003'), Decimal('0.000015')),  # $3 / $15 per MTok
            'claude-haiku-4-5': (Decimal('0.000001'), Decimal('0.000005')),   # $1 / $5 per MTok
        }
        input_rate, output_rate = rates.get(
            model, (Decimal('0.000005'), Decimal('0.000025'))
        )
        return (
            Decimal(str(input_tokens)) * input_rate
            + Decimal(str(output_tokens)) * output_rate
        )


# =============================================================================
# MODULE-LEVEL CONVENIENCE
# =============================================================================

# Default gateway instance (singleton)
_default_gateway: Optional[AIGateway] = None


def get_gateway() -> AIGateway:
    """Get the default gateway instance (singleton)."""
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = AIGateway()
    return _default_gateway


def reset_gateway() -> None:
    """Reset the default gateway (useful for testing)."""
    global _default_gateway
    _default_gateway = None


def complete(
    system_prompt: str,
    user_prompt: str,
    **kwargs
) -> Result[CompletionResponse]:
    """Convenience function for raw completion."""
    return get_gateway().complete(system_prompt, user_prompt, **kwargs)


def complete_structured(
    system_prompt: str,
    user_prompt: str,
    response_schema: type[BaseModel],
    **kwargs
) -> Result[StructuredResponse]:
    """Convenience function for structured completion."""
    return get_gateway().complete_structured(
        system_prompt, user_prompt, response_schema, **kwargs
    )
