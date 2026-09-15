from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a transaction categorizer for an Indian personal-finance app.
Pick exactly one category for the merchant/description from this list (use the EXACT name):
{categories}

Return strict JSON: {{"category": "<one of the above>", "confidence": <0..1>, "rationale": "<<=20 words>"}}.
If you are unsure, set confidence < 0.5 and pick "Other"."""


def llm_categorize(db: Session, merchant_or_desc: str) -> Optional[tuple[int, float, str]]:
    """Call configured LLM provider. Returns (category_id, confidence, rationale) or None."""
    cfg = get_settings()
    if not cfg.llm_enabled:
        return None
    text = (merchant_or_desc or "").strip()
    if not text:
        return None

    # cache hit?
    cached = db.query(models.LLMCache).filter_by(key=text.lower()).first()
    if cached and cached.category_id is not None:
        return cached.category_id, cached.confidence, cached.rationale or ""

    cats = db.query(models.Category).order_by(models.Category.name.asc()).all()
    names = [c.name for c in cats]
    if not names:
        return None
    prompt = SYSTEM_PROMPT.format(categories="\n - " + "\n - ".join(names))
    try:
        if cfg.llm_provider == "openai":
            parsed = _call_openai(cfg, prompt, text)
        elif cfg.llm_provider == "gemini":
            parsed = _call_gemini(cfg, prompt, text)
        else:
            log.warning("unknown llm_provider %s", cfg.llm_provider)
            return None
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM call failed: %s", exc)
        return None
    if not parsed:
        return None
    cat_name = parsed.get("category")
    confidence = float(parsed.get("confidence") or 0.0)
    rationale = parsed.get("rationale") or ""
    match = next((c for c in cats if c.name == cat_name), None)
    if not match:
        return None
    db.merge(
        models.LLMCache(
            key=text.lower(),
            category_id=match.id,
            confidence=confidence,
            rationale=rationale,
        )
    )
    db.commit()
    return match.id, confidence, rationale


def _call_openai(cfg, prompt: str, text: str) -> Optional[dict]:
    if not cfg.openai_api_key:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    rsp = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = rsp.choices[0].message.content or "{}"
    return json.loads(content)


def _call_gemini(cfg, prompt: str, text: str) -> Optional[dict]:
    if not cfg.gemini_api_key:
        return None
    import google.generativeai as genai

    genai.configure(api_key=cfg.gemini_api_key)
    model = genai.GenerativeModel(cfg.llm_model or "gemini-1.5-flash")
    rsp = model.generate_content(
        [prompt, text],
        generation_config={"response_mime_type": "application/json", "temperature": 0},
    )
    return json.loads(rsp.text)
