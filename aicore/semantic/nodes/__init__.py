"""Semantic extraction nodes — deterministic mock extraction pipeline.

Each node produces typed ExtractionResult + SemanticPatch pairs.
No AI integration yet — all outputs are deterministic mock data.
"""

from aicore.semantic.nodes.base import BaseSemanticNode
from aicore.semantic.nodes.ocr_node import OcrNode
from aicore.semantic.nodes.asr_node import AsrNode
from aicore.semantic.nodes.vision_node import VisionNode
from aicore.semantic.nodes.motion_node import MotionNode
from aicore.semantic.nodes.environment_node import EnvironmentNode
from aicore.semantic.nodes.character_node import CharacterNode
from aicore.semantic.nodes.aggregation_node import AggregationNode

__all__ = [
    "BaseSemanticNode",
    "OcrNode",
    "AsrNode",
    "VisionNode",
    "MotionNode",
    "EnvironmentNode",
    "CharacterNode",
    "AggregationNode",
]