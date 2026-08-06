import asyncio
from dataclasses import dataclass
from time import perf_counter

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import RootCauseAnalysisContent


class GeminiServiceError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class GeminiAnalysisResult:
    content: RootCauseAnalysisContent
    model_name: str
    latency_ms: int
    token_usage: dict[str, int]


class GeminiService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key or not self.settings.gemini_model:
            raise GeminiServiceError(
                "GEMINI_NOT_CONFIGURED",
                "Gemini analysis is not configured. Set GEMINI_API_KEY and GEMINI_MODEL.",
            )
        self.model_name = self.settings.gemini_model
        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(self.settings.gemini_timeout_seconds * 1000)
            ),
        )

    async def generate_analysis(self, prompt: str) -> GeminiAnalysisResult:
        started_at = perf_counter()
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.settings.gemini_temperature,
                        response_mime_type="application/json",
                        response_schema=RootCauseAnalysisContent,
                    ),
                ),
                timeout=self.settings.gemini_timeout_seconds,
            )
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise GeminiServiceError(
                "GEMINI_TIMEOUT",
                "Gemini analysis timed out. Retry the request.",
                retryable=True,
            ) from error
        except errors.APIError as error:
            if error.code == 429:
                raise GeminiServiceError(
                    "GEMINI_RATE_LIMITED",
                    "Gemini rate limit reached. Retry the request shortly.",
                    retryable=True,
                ) from error
            raise GeminiServiceError(
                "GEMINI_PROVIDER_ERROR",
                "Gemini could not complete the analysis.",
                retryable=error.code >= 500,
            ) from error
        except Exception as error:
            raise GeminiServiceError(
                "GEMINI_PROVIDER_ERROR",
                "Gemini could not complete the analysis.",
                retryable=True,
            ) from error

        try:
            content = (
                response.parsed
                if isinstance(response.parsed, RootCauseAnalysisContent)
                else RootCauseAnalysisContent.model_validate_json(response.text or "")
            )
        except (ValidationError, ValueError) as error:
            raise GeminiServiceError(
                "GEMINI_INVALID_RESPONSE",
                "Gemini returned an invalid structured analysis.",
            ) from error

        usage = response.usage_metadata
        token_usage = {
            key: value
            for key, value in {
                "prompt_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "total_tokens": getattr(usage, "total_token_count", None),
            }.items()
            if value is not None
        }
        return GeminiAnalysisResult(
            content=content,
            model_name=self.model_name,
            latency_ms=round((perf_counter() - started_at) * 1000),
            token_usage=token_usage,
        )