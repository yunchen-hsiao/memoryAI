"""
AI service abstraction layer for MemoryAI.

Provides:
- AIProvider abstract base class (Requirements 8.1)
- CohereProvider for text generation via command-r-08-2024 (Requirement 8.2)
- GeminiProvider for embeddings via gemini-embedding-001 (Requirement 8.3)
- 3-tier JSON parsing with Pydantic validation (Requirements 9.2–9.7)
- Exponential backoff for 503 errors (Requirements 9.8–9.10)
- Provider selection via TEXT_GENERATION_PROVIDER env var (Requirement 8.4)
- 30-second timeout guard (Requirement 8.5)
"""

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Type, TypeVar

import cohere
from pydantic import BaseModel, ValidationError

from models.schemas import ParseError

# Google GenAI is imported lazily inside GeminiProvider to avoid module-level
# crashes on environments where the C-extension has missing native dependencies
# (e.g. some Windows + Python 3.13 combinations).  The import is performed once
# inside __init__ and the resulting objects are stored as instance attributes.

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TypeVar for generic Pydantic model
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Timeout constants
# ---------------------------------------------------------------------------

AI_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """
    Abstract base class for AI service providers.

    Every provider must implement:
    - generate_text()     — text completion / chat
    - generate_embedding() — vector embedding
    - parse_structured_json() — 3-tier JSON parsing with schema validation
    """

    @abstractmethod
    def generate_text(self, prompt: str, max_tokens: int = 4000) -> str:
        """
        Generate a text completion from *prompt*.

        Args:
            prompt:     The user / system prompt to send to the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The model's raw text output.

        Raises:
            NotImplementedError: If the provider does not support text generation.
            TimeoutError: If the call takes longer than AI_TIMEOUT_SECONDS.
        """

    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a vector embedding for *text*.

        Args:
            text: Input text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            NotImplementedError: If the provider does not support embeddings.
            TimeoutError: If the call takes longer than AI_TIMEOUT_SECONDS.
        """

    @abstractmethod
    def parse_structured_json(
        self, raw_text: str, schema: Type[T]
    ) -> tuple[T | None, ParseError | None]:
        """
        Parse JSON from a raw AI response using a 3-tier strategy, then
        validate the result against *schema*.

        Tier 1: Direct json.loads()
        Tier 2: Strip markdown code fences, retry json.loads()
        Tier 3: Extract between first [ / { and last ] / }, retry json.loads()

        Args:
            raw_text: Raw string returned by the AI provider.
            schema:   Pydantic model class to validate against.

        Returns:
            ``(model_instance, None)`` on success, or
            ``(None, ParseError)`` on any failure.
        """


# ---------------------------------------------------------------------------
# Shared 3-tier JSON parsing implementation
# ---------------------------------------------------------------------------


def _parse_structured_json(
    raw_text: str, schema: Type[T]
) -> tuple[T | None, ParseError | None]:
    """
    Shared 3-tier JSON parsing with Pydantic validation.

    Used by both CohereProvider and any other text-generating provider.

    Returns:
        (model_instance, None) on success, or (None, ParseError) on failure.
    """
    # --- Tier 1: Direct parse ---
    try:
        parsed = json.loads(raw_text)
        model = schema.model_validate(parsed)
        return (model, None)
    except json.JSONDecodeError:
        pass  # Fall through to Tier 2
    except ValidationError as exc:
        fields = [str(err["loc"]) for err in exc.errors()]
        return (
            None,
            ParseError(
                category="schema_validation_error",
                message=f"Schema validation failed after Tier 1: {fields}",
                raw_response=raw_text[:10_000],
            ),
        )

    # --- Tier 2: Strip markdown code fences ---
    markdown_stripped = re.sub(
        r"```(?:json)?\s*|\s*```", "", raw_text, flags=re.IGNORECASE
    ).strip()
    try:
        parsed = json.loads(markdown_stripped)
        model = schema.model_validate(parsed)
        return (model, None)
    except json.JSONDecodeError:
        pass  # Fall through to Tier 3
    except ValidationError as exc:
        fields = [str(err["loc"]) for err in exc.errors()]
        return (
            None,
            ParseError(
                category="schema_validation_error",
                message=f"Schema validation failed after Tier 2: {fields}",
                raw_response=raw_text[:10_000],
            ),
        )

    # --- Tier 3: Extract between first [ / { and last ] / } ---
    # Find the earliest opening bracket/brace
    first_bracket = raw_text.find("[")
    first_brace = raw_text.find("{")

    candidates_start: list[int] = [
        pos for pos in [first_bracket, first_brace] if pos != -1
    ]
    start_idx = min(candidates_start) if candidates_start else -1

    last_bracket = raw_text.rfind("]")
    last_brace = raw_text.rfind("}")
    end_idx = max(last_bracket, last_brace)

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        extracted = raw_text[start_idx : end_idx + 1]
        try:
            parsed = json.loads(extracted)
            model = schema.model_validate(parsed)
            return (model, None)
        except json.JSONDecodeError:
            pass  # All tiers exhausted
        except ValidationError as exc:
            fields = [str(err["loc"]) for err in exc.errors()]
            return (
                None,
                ParseError(
                    category="schema_validation_error",
                    message=f"Schema validation failed after Tier 3: {fields}",
                    raw_response=raw_text[:10_000],
                ),
            )

    # --- All tiers failed ---
    logger.error(
        "All JSON parsing strategies failed. Raw response: %s", raw_text
    )
    return (
        None,
        ParseError(
            category="parse_error",
            message="All parsing strategies failed",
            raw_response=raw_text[:10_000],
        ),
    )


# ---------------------------------------------------------------------------
# CohereProvider
# ---------------------------------------------------------------------------


class CohereProvider(AIProvider):
    """
    AI provider backed by Cohere command-r-08-2024 for text generation.

    Embeddings are NOT supported — calling generate_embedding() raises
    NotImplementedError as per Requirement 8.2.
    """

    _provider_name = "CohereProvider"

    def __init__(self, api_key: str) -> None:
        self.client = cohere.ClientV2(api_key)

    def generate_text(self, prompt: str, max_tokens: int = 4000) -> str:
        """Call Cohere command-r-08-2024 with a 30-second timeout guard."""
        import concurrent.futures

        def _call() -> str:
            response = self.client.chat(
                model="command-r-08-2024",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.message.content[0].text

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=AI_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"{self._provider_name}.generate_text exceeded "
                    f"{AI_TIMEOUT_SECONDS}s timeout"
                )

    def generate_embedding(self, text: str) -> list[float]:
        raise NotImplementedError(
            "CohereProvider does not support embeddings. "
            "Use GeminiProvider for generate_embedding()."
        )

    def parse_structured_json(
        self, raw_text: str, schema: Type[T]
    ) -> tuple[T | None, ParseError | None]:
        return _parse_structured_json(raw_text, schema)


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


class GeminiProvider(AIProvider):
    """
    AI provider backed by Google Gemini gemini-embedding-001 for embeddings.

    Text generation is NOT supported — calling generate_text() raises
    NotImplementedError as per Requirement 8.3.
    JSON parsing is NOT supported — calling parse_structured_json() raises
    NotImplementedError.

    The google.genai SDK is imported lazily inside ``__init__`` to avoid
    module-level crashes in environments where the native extension is broken.
    """

    _provider_name = "GeminiProvider"

    def __init__(self, api_key: str) -> None:
        # Lazy import to avoid module-level crash when native C extensions are
        # unavailable (e.g. some Windows + Python 3.13 configurations).
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415

        self._genai_types = types
        self.client = genai.Client(api_key=api_key)

    def generate_text(self, prompt: str, max_tokens: int = 4000) -> str:
        raise NotImplementedError(
            "GeminiProvider is only for embeddings. "
            "Use CohereProvider for generate_text()."
        )

    def generate_embedding(self, text: str) -> list[float]:
        """Call Gemini gemini-embedding-001 with a 30-second timeout guard."""
        import concurrent.futures

        def _call() -> list[float]:
            response = self.client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=self._genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )
            return response.embeddings[0].values

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=AI_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"{self._provider_name}.generate_embedding exceeded "
                    f"{AI_TIMEOUT_SECONDS}s timeout"
                )

    def parse_structured_json(
        self, raw_text: str, schema: Type[T]
    ) -> tuple[T | None, ParseError | None]:
        raise NotImplementedError(
            "GeminiProvider is only for embeddings. "
            "Use CohereProvider for parse_structured_json()."
        )


# ---------------------------------------------------------------------------
# Exponential backoff helper
# ---------------------------------------------------------------------------


def call_ai_with_retry(
    ai_provider: AIProvider,
    prompt: str,
    max_tokens: int = 4000,
    max_retries: int = 3,
) -> tuple[str | None, ParseError | None]:
    """
    Call ai_provider.generate_text() with exponential backoff on 503 errors.

    Retry schedule:
      - Before attempt 1 (retry 1): wait 1 second
      - Before attempt 2 (retry 2): wait 2 seconds
      - Before attempt 3 (retry 3): wait 4 seconds
      - After max_retries exhausted with 503: return ParseError(retry_error)

    A non-503 HTTP error on any attempt returns ParseError(provider_error)
    immediately without further retries.

    Args:
        ai_provider: AIProvider instance to use.
        prompt:      Prompt to send.
        max_tokens:  Token limit passed to generate_text().
        max_retries: Maximum number of attempts (default 3).

    Returns:
        ``(response_text, None)`` on success, or
        ``(None, ParseError)`` on exhausted retries / provider error.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        # Exponential wait before each retry (not before the first attempt)
        if attempt > 0:
            wait_seconds = 2 ** (attempt - 1)  # 1s, 2s, 4s for attempts 1,2,3
            logger.warning(
                "503 error on attempt %d/%d — retrying in %ds",
                attempt,
                max_retries,
                wait_seconds,
            )
            time.sleep(wait_seconds)

        try:
            text = ai_provider.generate_text(prompt, max_tokens=max_tokens)
            return (text, None)

        except Exception as exc:
            exc_str = str(exc)
            last_exception = exc

            is_503 = (
                "503" in exc_str
                or "Service Unavailable" in exc_str
                or "service_unavailable" in exc_str.lower()
            )

            if not is_503:
                # Non-503 HTTP error — do not retry
                logger.error(
                    "Non-503 provider error on attempt %d: %s", attempt + 1, exc_str
                )
                return (
                    None,
                    ParseError(
                        category="provider_error",
                        message=exc_str,
                    ),
                )

            # 503 — will retry if attempts remain
            if attempt == max_retries - 1:
                # Last attempt exhausted
                break

    # All retries exhausted for 503
    logger.error(
        "All %d retry attempts exhausted. Last error: %s",
        max_retries,
        str(last_exception),
    )
    return (
        None,
        ParseError(
            category="retry_error",
            message=f"Max retries ({max_retries}) exhausted: {last_exception}",
        ),
    )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def get_text_provider() -> AIProvider:
    """
    Instantiate and return the text generation AIProvider based on the
    TEXT_GENERATION_PROVIDER environment variable.

    Supported values:
    - ``"cohere"``  → CohereProvider (default)
    - ``"gemini"``  → would require a Gemini text client (not yet supported)

    Raises:
        ValueError: If TEXT_GENERATION_PROVIDER is set to an unrecognized value.
        RuntimeError: If the required API key is missing.
    """
    provider_name = os.environ.get("TEXT_GENERATION_PROVIDER", "cohere").lower()

    if provider_name == "cohere":
        api_key = os.environ.get("COHERE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "TEXT_GENERATION_PROVIDER=cohere but COHERE_API_KEY is not set"
            )
        return CohereProvider(api_key=api_key)

    if provider_name == "gemini":
        # Gemini text generation could be added in the future.
        # For now, signal that it is not yet implemented.
        raise ValueError(
            "TEXT_GENERATION_PROVIDER=gemini is not yet supported for text "
            "generation. Use provider_name='cohere' or add a Gemini text client."
        )

    raise ValueError(
        f"Unknown TEXT_GENERATION_PROVIDER='{provider_name}'. "
        "Supported values: 'cohere', 'gemini'."
    )


def get_embedding_provider() -> AIProvider:
    """
    Instantiate and return the embedding AIProvider.

    Always returns GeminiProvider backed by GEMINI_API_KEY.

    Raises:
        RuntimeError: If GEMINI_API_KEY is not set.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set — GeminiProvider cannot be initialized"
        )
    return GeminiProvider(api_key=api_key)
