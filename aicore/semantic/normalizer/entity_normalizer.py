"""EntityNormalizer — deterministic entity name & feature normalization.

Stateless normalizer that converts raw extraction output into canonical
entity forms. No AI inference — pure rule-based normalization.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)


# ---------------------------------------------------------------------------
# Alias map for common anime character/term variants
# ---------------------------------------------------------------------------

_COMMON_ALIASES: Dict[str, List[str]] = {
    "naruto": ["naruto uzumaki", "uzumaki naruto"],
    "sasuke": ["sasuke uchiha", "uchiha sasuke"],
    "luffy": ["monkey d. luffy", "monkey d luffy"],
    "zoro": ["roronoa zoro"],
    "goku": ["son goku", "kakarot"],
    "vegeta": ["vegeta iv"],
}


def _normalize_case(text: str) -> str:
    """Lowercase and strip."""
    return text.strip().lower()


def _strip_accents(text: str) -> str:
    """Remove unicode accents for canonical matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _collapse_whitespace(text: str) -> str:
    """Replace any whitespace run with a single space."""
    return re.sub(r"\s+", " ", text).strip()


def _remove_punctuation_except_hyphen(text: str) -> str:
    """Remove punctuation but keep hyphens for compound names."""
    return re.sub(r"[^\w\s-]", "", text)


# ---------------------------------------------------------------------------
# EntityNormalizer
# ---------------------------------------------------------------------------


class EntityNormalizer:
    """Stateless deterministic entity normalizer.

    Usage:
        normalizer = EntityNormalizer()
        entity = normalizer.normalize_character("Naruto Uzumaki")
        # -> CharacterEntity(normalized_name="naruto uzumaki", ...)
    """

    def __init__(self, alias_map: Optional[Dict[str, List[str]]] = None):
        self._alias_map = alias_map or _COMMON_ALIASES

    # ── Core normalization pipeline ───────────────────────────────────

    def normalize_name(self, raw_name: str) -> str:
        """Canonical normalization pipeline for entity names."""
        name = raw_name
        name = _normalize_case(name)
        name = _strip_accents(name)
        name = _remove_punctuation_except_hyphen(name)
        name = _collapse_whitespace(name)
        return name

    def resolve_aliases(self, normalized_name: str) -> List[str]:
        """Resolve known aliases for a given canonical name."""
        aliases: List[str] = []
        for canonical, known_aliases in self._alias_map.items():
            if normalized_name == canonical:
                aliases.extend(known_aliases)
        return sorted(set(aliases))

    # ── Entity builders ──────────────────────────────────────────────

    def normalize_character(
        self,
        raw_name: str,
        confidence: float = 1.0,
    ) -> CharacterEntity:
        """Normalize raw character name into a CharacterEntity."""
        normalized = self.normalize_name(raw_name)
        aliases = self.resolve_aliases(normalized)
        return CharacterEntity(
            normalized_name=normalized,
            confidence=confidence,
            aliases=aliases,
        )

    def normalize_object(
        self,
        raw_name: str,
        confidence: float = 1.0,
    ) -> ObjectEntity:
        """Normalize raw object name into an ObjectEntity."""
        normalized = self.normalize_name(raw_name)
        return ObjectEntity(
            normalized_name=normalized,
            confidence=confidence,
        )

    def normalize_action(
        self,
        raw_name: str,
        confidence: float = 1.0,
        intensity: float = 0.0,
    ) -> ActionEntity:
        """Normalize raw action into an ActionEntity."""
        normalized = self.normalize_name(raw_name)
        return ActionEntity(
            normalized_name=normalized,
            confidence=confidence,
            intensity=intensity,
        )

    def normalize_emotion(
        self,
        raw_name: str,
        confidence: float = 1.0,
    ) -> EmotionEntity:
        """Normalize raw emotion into an EmotionEntity."""
        normalized = self.normalize_name(raw_name)
        aliases = self.resolve_aliases(normalized)
        return EmotionEntity(
            normalized_name=normalized,
            confidence=confidence,
            aliases=aliases,
        )

    def normalize_environment(
        self,
        raw_name: str,
        location: str = "unknown",
        confidence: float = 1.0,
    ) -> EnvironmentEntity:
        """Normalize raw environment name into an EnvironmentEntity."""
        normalized = self.normalize_name(raw_name)
        return EnvironmentEntity(
            normalized_name=normalized,
            location=location,
            confidence=confidence,
        )

    def normalize_character_batch(
        self,
        raw_names: List[str],
        default_confidence: float = 0.8,
    ) -> List[CharacterEntity]:
        """Normalize a batch of character names, deduplicated."""
        seen: set = set()
        entities: List[CharacterEntity] = []
        for name in raw_names:
            normalized = self.normalize_name(name)
            if normalized and normalized not in seen:
                seen.add(normalized)
                entities.append(
                    self.normalize_character(name, default_confidence)
                )
        # Sort for deterministic ordering
        entities.sort(key=lambda e: e.normalized_name)
        return entities