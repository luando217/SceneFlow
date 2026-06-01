"""Node registry — discoverable, typed node catalogue."""

from __future__ import annotations

from typing import Any, Optional, Type

from .base import BaseNode


class _NodeRegistryMeta(type):
    """Metaclass that auto-registers subclasses of BaseNode."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> type:
        cls = super().__new__(mcs, name, bases, namespace)
        if name != "BaseNode" and issubclass(cls, BaseNode) and not getattr(cls, "_abstract", False):
            NodeRegistry.register(cls)
        return cls


class NodeRegistry:
    """
    Global registry of available node types.

    Nodes are registered automatically via the metaclass or manually
    with ``register()``.  Lookup is by class name or node_id prefix.
    """

    _types: dict[str, Type[BaseNode]] = {}

    @classmethod
    def register(cls, node_class: Type[BaseNode]) -> None:
        name = node_class.__name__
        if name in cls._types:
            return  # idempotent
        cls._types[name] = node_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseNode]]:
        return cls._types.get(name)

    @classmethod
    def all(cls) -> dict[str, Type[BaseNode]]:
        return dict(cls._types)

    @classmethod
    def instantiate(cls, name: str, **kwargs: Any) -> BaseNode:
        klass = cls.get(name)
        if klass is None:
            raise ValueError(f"Unknown node type: {name}. Available: {list(cls._types)}")
        return klass(**kwargs)

    @classmethod
    def clear(cls) -> None:
        cls._types.clear()