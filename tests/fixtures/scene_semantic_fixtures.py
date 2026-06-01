"""Test fixtures for SceneSemantic and related objects."""

from typing import List, Optional

from aicore.semantic.schemas.entities import (
    CharacterEntity,
    ActionEntity,
    EnvironmentEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


def create_test_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    video_id: str = "test_video",
    episode_id: Optional[str] = None,
    dialogue: str = "",
    actions: Optional[List[ActionEntity]] = None,
    motion_direction: str = "static",
    motion_intensity: float = 0.0,
) -> SceneSemantic:
    """Create a minimal test scene.

    Args:
        scene_id: Scene identifier
        start_time: Start time in seconds
        end_time: End time in seconds
        video_id: Video identifier
        episode_id: Optional episode identifier
        dialogue: Dialogue text (default empty)
        actions: List of action entities (default empty)
        motion_direction: Motion direction (default static)
        motion_intensity: Motion intensity (default 0.0)

    Returns:
        SceneSemantic with basic properties
    """
    return SceneSemantic(
        scene_id=scene_id,
        video_id=video_id,
        episode_id=episode_id,
        start_time=start_time,
        end_time=end_time,
        start_frame=0,
        end_frame=30,
        characters=[],
        actions=actions or [],
        objects=[],
        environments=[
            EnvironmentEntity(
                normalized_name="test_environment",
                confidence=1.0,
            ),
        ],
        emotions=[],
        dialogue=dialogue,
        motion_direction=motion_direction,
        motion_intensity=motion_intensity,
    )


def create_multi_character_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    character_names: List[str],
    video_id: str = "test_video",
) -> SceneSemantic:
    """Create test scene with multiple characters.

    Args:
        scene_id: Scene identifier
        start_time: Start time in seconds
        end_time: End time in seconds
        character_names: List of character names
        video_id: Video identifier

    Returns:
        SceneSemantic with characters
    """
    characters = [
        CharacterEntity(
            normalized_name=name.lower(),
            confidence=1.0,
        )
        for name in character_names
    ]

    return SceneSemantic(
        scene_id=scene_id,
        video_id=video_id,
        episode_id=None,
        start_time=start_time,
        end_time=end_time,
        start_frame=0,
        end_frame=30,
        characters=characters,
        actions=[],
        objects=[],
        environments=[
            EnvironmentEntity(
                normalized_name="test_environment",
                confidence=1.0,
            ),
        ],
        emotions=[],
    )