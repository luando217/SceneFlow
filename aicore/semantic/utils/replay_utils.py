"""Deterministic replay utilities — zero wall-clock dependency.

This module provides deterministic runtime abstractions that eliminate
replay-instability caused by runtime-generated timestamps and
nondeterministic identity fields.

Architecture constraints:
- frozen=True for all models using these utilities
- extra="forbid" enforced
- deterministic replay required
- deterministic serialization required
- no hidden mutations
- no runtime randomness
- same input -> byte-identical output

Phase: 3.1e — Deterministic Replay Hardening & Stable Runtime Identity
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


# ============================================================================
# Deterministic Clock — wall-clock free time abstraction
# ============================================================================


class DeterministicClock:
    """Deterministic clock that produces stable replay values.

    This clock does NOT access wall-clock time. Instead, it derives
    values deterministically from content hashes, ensuring that the same
    input always produces the same timestamp.

    Usage:
        # Explicit seed-based derivation
        ts = DeterministicClock.timestamp(seed="my_content_hash")

        # Zero-based replay timestamp (for serial consistency)
        ts = DeterministicClock.zero_timestamp()

        # Field-derived timestamp (uses field content as seed)
        ts = DeterministicClock.field_derived_timestamp("scene_id", "video_id")

    DO NOT use:
        - datetime.now()
        - datetime.utcnow()
        - time.time()
        - time.perf_counter() for identity fields
    """

    # Base epoch for zero-timestamp derivation
    REPLAY_EPOCH: float = 1704067200.0  # 2024-01-01 00:00:00 UTC

    @staticmethod
    def zero_timestamp() -> float:
        """Return deterministic zero-epoch timestamp.

        Always returns the same value for replay consistency.
        Use when timestamp is required but should not vary between runs.
        """
        return DeterministicClock.REPLAY_EPOCH

    @staticmethod
    def timestamp(seed: str) -> float:
        """Return deterministic timestamp derived from seed content.

        Uses SHA-256 to derive a stable timestamp from the seed string.
        The returned value is always in the valid timestamp range.

        Args:
            seed: Deterministic content to derive timestamp from

        Returns:
            Stable float timestamp derived from seed
        """
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        # Convert hex digest to float in valid timestamp range
        # SHA-256 produces 64 hex chars, use first 16 for reasonable precision
        hex_value = int(digest[:16], 16)
        # Map to valid timestamp range (2024-01-01 to 2030-01-01)
        min_ts = 1704067200.0  # 2024-01-01 00:00:00 UTC
        max_ts = 1893456000.0  # 2030-01-01 00:00:00 UTC
        ts_range = max_ts - min_ts
        return min_ts + (hex_value / (16**16)) * ts_range

    @staticmethod
    def field_derived_timestamp(*fields: str) -> float:
        """Return deterministic timestamp from field content.

        Combines multiple fields into a single seed for derivation.

        Args:
            *fields: Field values to combine

        Returns:
            Stable float timestamp derived from combined fields
        """
        combined = "|".join(str(f) for f in fields)
        return DeterministicClock.timestamp(combined)


# ============================================================================
# Replay Identity — stable SHA-256 based identity
# ============================================================================


def stable_hash(content: str) -> str:
    """Generate stable SHA-256 hex digest from string content.

    This hash is deterministic — same input always produces same output.
    Use for replay-safe identity generation.

    Args:
        content: String content to hash

    Returns:
        SHA-256 hex digest (64 characters)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_dict_hash(data: Dict[str, Any]) -> str:
    """Generate stable SHA-256 hash from dict content.

    Args:
        data: Dict to hash (must be JSON-serializable)

    Returns:
        SHA-256 hex digest
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return stable_hash(serialized)


def replay_fingerprint(*parts: str) -> str:
    """Generate deterministic replay fingerprint from parts.

    Args:
        *parts: Parts to combine into fingerprint

    Returns:
        SHA-256 hex digest of combined parts
    """
    content = "|".join(str(p) for p in parts)
    return stable_hash(content)


# ============================================================================
# Deterministic Serialization Helpers
# ============================================================================


def sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return deterministically-sorted copy of list.

    Args:
        items: List to sort (may be None or empty)

    Returns:
        Sorted list with stable ordering
    """
    if items is None:
        return []
    return sorted(items)


def to_dict_deterministic(model: Any) -> Dict[str, Any]:
    """Produce deterministically-ordered dict from any model.

    - Removes None values
    - Sorts keys alphabetically
    - Handles nested models with their own to_dict_deterministic methods

    Args:
        model: Pydantic model or dict to serialize

    Returns:
        Deterministic dict with stable key ordering
    """
    if hasattr(model, "model_dump"):
        raw = model.model_dump()
    elif isinstance(model, dict):
        raw = model
    else:
        return {"value": str(model)}

    cleaned = {k: v for k, v in raw.items() if v is not None}

    # Recursively process nested structures
    result = {}
    for key in sorted(cleaned.keys()):
        value = cleaned[key]
        if hasattr(value, "to_dict_deterministic"):
            result[key] = value.to_dict_deterministic()
        elif isinstance(value, list):
            result[key] = _process_list_deterministic(value)
        elif isinstance(value, dict):
            result[key] = to_dict_deterministic(value)
        else:
            result[key] = value

    return result


def _process_list_deterministic(items: List[Any]) -> List[Any]:
    """Process list items deterministically."""
    result = []
    for item in items:
        if hasattr(item, "to_dict_deterministic"):
            result.append(item.to_dict_deterministic())
        elif isinstance(item, dict):
            result.append(to_dict_deterministic(item))
        else:
            result.append(item)
    # Sort if all items are comparable
    try:
        return sorted(result)
    except TypeError:
        return result


def stable_json(obj: Any, indent: int = 2) -> str:
    """Generate deterministic JSON string.

    Args:
        obj: Object to serialize
        indent: JSON indentation

    Returns:
        Deterministic JSON string
    """
    return json.dumps(
        to_dict_deterministic(obj),
        indent=indent,
        sort_keys=True,
        default=str,
    )


# ============================================================================
# Replay Validation Helpers
# ============================================================================


def validate_replay_identity(
    instance: Any,
    expected_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate that an instance produces stable replay identity.

    Args:
        instance: Object to validate
        expected_hash: Optional expected hash to verify against

    Returns:
        Dict with validation results:
        - is_valid: bool
        - instance_hash: str
        - matches_expected: bool
        - to_dict: dict
        - errors: list of issues
    """
    errors = []

    # Get deterministic dict
    if hasattr(instance, "to_dict_deterministic"):
        dict_form = instance.to_dict_deterministic()
    elif hasattr(instance, "model_dump"):
        dict_form = instance.model_dump()
    else:
        errors.append("Instance has no deterministic serialization method")
        dict_form = {}

    # Compute hash
    instance_hash = stable_dict_hash(dict_form)

    # Check for problematic fields that might cause instability
    if hasattr(instance, "created_at"):
        created_at = getattr(instance, "created_at", None)
        if created_at is not None and isinstance(created_at, float):
            # Check if it's a wall-clock derived timestamp
            clock = DeterministicClock
            deviation = abs(created_at - clock.REPLAY_EPOCH)
            if deviation > 1.0:
                # Not using the default zero timestamp
                # might be wall-clock based
                errors.append(
                    f"created_at={created_at} appears to use wall-clock time"
                )

    return {
        "is_valid": len(errors) == 0,
        "instance_hash": instance_hash,
        "matches_expected": (
            expected_hash == instance_hash if expected_hash else True
        ),
        "to_dict": dict_form,
        "errors": errors,
    }


def assert_deterministic_output(
    instance: Any,
    context: str = "",
) -> None:
    """Assert that an instance has deterministic output.

    Raises AssertionError if the instance has non-deterministic fields.

    Args:
        instance: Object to validate
        context: Context string for error messages
    """
    result = validate_replay_identity(instance)

    if not result["is_valid"]:
        err_msg = (
            f"Non-deterministic output in {context}: "
            f"{result['errors']}"
        )
        raise AssertionError(err_msg)


def deterministic_diff(
    instance1: Any,
    instance2: Any,
) -> Dict[str, Any]:
    """Compare two instances for deterministic equality.

    Args:
        instance1: First instance
        instance2: Second instance

    Returns:
        Dict with comparison results:
        - is_equal: bool
        - hash1: str
        - hash2: str
        - differences: list of field differences
    """
    has_to_dict1 = hasattr(instance1, "to_dict_deterministic")
    has_to_dict2 = hasattr(instance2, "to_dict_deterministic")
    dict1 = to_dict_deterministic(instance1) if has_to_dict1 else {}
    dict2 = to_dict_deterministic(instance2) if has_to_dict2 else {}

    hash1 = stable_dict_hash(dict1)
    hash2 = stable_dict_hash(dict2)

    differences = []
    all_keys = set(dict1.keys()) | set(dict2.keys())
    for key in sorted(all_keys):
        val1 = dict1.get(key)
        val2 = dict2.get(key)
        if val1 != val2:
            differences.append({
                "field": key,
                "value1": val1,
                "value2": val2,
            })

    return {
        "is_equal": hash1 == hash2,
        "hash1": hash1,
        "hash2": hash2,
        "differences": differences,
    }


__all__ = [
    # Deterministic clock
    "DeterministicClock",
    # Identity generation
    "stable_hash",
    "stable_dict_hash",
    "replay_fingerprint",
    # Serialization helpers
    "sorted_strings",
    "to_dict_deterministic",
    "stable_json",
    # Validation helpers
    "validate_replay_identity",
    "assert_deterministic_output",
    "deterministic_diff",
]