"""i18n endpoints (TASK-062): string bundles + advisory translation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.i18n import (
    GLOSSARY,
    SUPPORTED_LANGUAGES,
    UI_STRINGS,
    bhashini_translate,
    translate_bundle,
    translate_text,
)

router = APIRouter(prefix="/v1/i18n", tags=["i18n"])


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    target_lang: str = Field("hi", pattern="^(en|hi|ta|bn|te|mr)$")
    props: dict[str, Any] | None = Field(
        None, description="Optional structured bundle — translated leaf-wise"
    )
    use_bhashini: bool = Field(
        False, description="Try the live pipeline first (needs BHASHINI_API_KEY)"
    )


@router.get("/languages")
async def languages() -> dict:
    """Vocabulary for the client's language selector (TASK-063)."""
    return {
        "default": "en",
        "configured_bhashini": bool(settings.BHASHINI_API_KEY),
        "languages": [
            {"code": code, "label": label} for code, label in SUPPORTED_LANGUAGES.items()
        ],
        "glossary_terms": len(GLOSSARY),
        "ui_strings": len(UI_STRINGS),
    }


@router.get("/strings/{lang}")
async def strings(lang: str) -> dict:
    """Full UI string bundle for one language (client caches per install)."""
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(404, f"unsupported language: {lang}")
    return {
        "lang": lang,
        "strings": translate_bundle(UI_STRINGS, lang),
        "glossary": {
            en: translations.get(lang, en)
            for en, translations in GLOSSARY.items()
        },
    }


@router.post("/translate")
async def translate(req: TranslateRequest) -> dict:
    """Translate a free-text advisory (and optional props bundle).

    Live Bhashini first when requested+configured; deterministic glossary
    always backstops. Genuinely unknown free text passes through unchanged
    (honest fallback instead of garbage) — dynamic advisories in production
    flow through the glossary pipeline upstream.
    """
    result: str | None = None
    used = "glossary"
    if req.use_bhashini:
        result = await bhashini_translate(req.text, req.target_lang)
        if result is not None:
            used = "bhashini"
    if result is None:
        result = translate_text(req.text, req.target_lang)

    return {
        "source": req.text,
        "target_lang": req.target_lang,
        "translated": result,
        "engine": used,
        "props": translate_bundle(req.props, req.target_lang) if req.props else None,
    }
