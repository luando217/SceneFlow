"""TextNormalizer — deterministic text normalization for ASR/OCR output.

Stateless normalizer that converts raw ASR transcripts and OCR text into
canonical form. No AI inference — pure rule-based normalization.
"""

from __future__ import annotations

import re
import unicodedata


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# TextNormalizer
# ---------------------------------------------------------------------------


class TextNormalizer:
    """Stateless deterministic text normalizer for ASR/OCR output.

    Rules applied in order:
    1. Strip accents/unicode normalize
    2. Collapse whitespace
    3. Strip leading/trailing whitespace
    4. Remove zero-width characters
    5. Optionally collapse repeated punctuation
    """

    def normalize_dialogue(self, raw_text: str) -> str:
        """Normalize ASR dialogue transcript.

        Preserves sentence structure, punctuation, and casing
        for natural readability.
        """
        text = raw_text
        text = _strip_accents(text)
        # Remove zero-width spaces and control chars (keep newlines)
        text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
        # Collapse whitespace (but keep single newlines as spaces)
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse repeated newlines to single space
        text = re.sub(r"\n+", " ", text)
        text = text.strip()
        return text

    def normalize_ocr(self, raw_text: str) -> str:
        """Normalize OCR output.

        More aggressive than dialogue normalization:
        - Lowercase
        - Remove line breaks
        - Collapse repeated spaces
        - Remove non-alphanumeric noise
        """
        text = raw_text
        text = _strip_accents(text)
        text = text.lower()
        # Remove zero-width characters
        text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
        # Replace any newline/tab with space
        text = re.sub(r"[\n\r\t]+", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    def normalize_and_merge(
        self,
        dialogue: str = "",
        ocr: str = "",
    ) -> tuple[str, str]:
        """Normalize both dialogue and OCR in one call.

        Returns:
            (normalized_dialogue, normalized_ocr)
        """
        return (
            self.normalize_dialogue(dialogue),
            self.normalize_ocr(ocr),
        )

    def strip_fillers(self, dialogue: str) -> str:
        """Remove common speech fillers (um, uh, like, etc.).

        Useful for cleaner ASR output before entity extraction.
        """
        fillers = re.compile(
            r"\b(?:um|uh|er|ah|like|you know|i mean)\b\s*",
            re.IGNORECASE,
        )
        return fillers.sub("", dialogue).strip()