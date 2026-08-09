import asyncio
import importlib.metadata
import sys

from google.genai import types

from app.core.config import (
    GeminiConfigConflictError,
    gemini_credential_diagnostics,
    get_settings,
)
from app.core.exceptions import ServiceError
from app.schemas.chat import GeminiProbeOutput
from app.services.gemini_service import GeminiService
from app.services.structured_schema import provider_json_schema


async def run_checks() -> int:
    try:
        settings = get_settings()
    except GeminiConfigConflictError as exception:
        print(f"FAILED [{exception.code}]: {exception}")
        return 1

    diagnostics = gemini_credential_diagnostics(settings)
    print("=== Runtime configuration ===")
    print("Python:", sys.executable)
    print("google-genai:", importlib.metadata.version("google-genai"))
    print("Model:", settings.gemini_model)
    print("Credential source:", diagnostics.source)
    print("Key configured:", diagnostics.length > 0)
    print("Key length:", diagnostics.length)
    print("Key fingerprint:", diagnostics.fingerprint or "NOT SET")

    if not settings.gemini_api_key:
        print("FAILED [GEMINI_NOT_CONFIGURED]: GEMINI_API_KEY chưa được cấu hình.")
        return 1

    service = GeminiService(settings)
    try:
        print("\n[1/2] Testing plain response...")
        plain = await service.generate(
            "Reply exactly with the word OK.",
            system_instruction="Return only the requested answer.",
            temperature=0,
            max_output_tokens=64,
            thinking_level=types.ThinkingLevel.MINIMAL,
            max_attempts=1,
            trace_id="direct-plain-probe",
        )
        print("SUCCESS:", plain.answer.strip())

        print("\n[2/2] Testing structured response used by the application...")
        structured = await service.generate(
            "Return JSON confirming the connection status.",
            system_instruction="Return only JSON matching the schema with status OK.",
            temperature=0,
            max_output_tokens=256,
            thinking_level=types.ThinkingLevel.MINIMAL,
            response_schema=provider_json_schema(GeminiProbeOutput),
            max_attempts=1,
            trace_id="direct-structured-probe",
        )
        GeminiProbeOutput.model_validate_json(structured.answer)
        print("SUCCESS: structured output is valid")
        return 0
    except ServiceError as exception:
        print(f"FAILED [{exception.code}]: {exception.message}")
        return 2
    finally:
        await service.close()


def main() -> int:
    return asyncio.run(run_checks())


if __name__ == "__main__":
    raise SystemExit(main())
