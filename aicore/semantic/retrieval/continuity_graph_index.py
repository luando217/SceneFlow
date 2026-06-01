"""ContinuityGraphIndex — deterministic indexes for chain retrieval.

Provides deterministic, frozen indexes for:
- scene -> chains
- character -> chains
- action -> chains
- environment -> chains

Query integration hooks for future retrieval (NO AI, NO embeddings):
- retrieve_continuity_chains_by_character
- retrieve_continuity_chains_by_action
- retrieve_continuity_chains_by_environment

All operations are deterministic and replay-safe.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from aicore.semantic.aggregation.continuity_chain_schemas import (
    ActionContinuityChain,
    BaseContinuityChain,
    CharacterContinuityChain,
    ChainType,
    DialogueContinuityChain,
    EnvironmentContinuityChain,
)


class ContinuityGraphIndex:
    """Deterministic index for continuity chains.

    Indexes chains by:
    - Scene IDs
    - Characters
    - Actions
    - Environments
    - Speakers

    All indexes are frozen and immutable after construction.
    """

    def __init__(self) -> None:
        """Initialize empty index."""
        # scene_id -> chain_ids (which chains contain this scene)
        self._scene_to_chains: Dict[str, Set[str]] = {}

        # character name -> chain_ids
        self._character_to_chains: Dict[str, Set[str]] = {}

        # action name -> chain_ids
        self._action_to_chains: Dict[str, Set[str]] = {}

        # environment location -> chain_ids
        self._environment_to_chains: Dict[str, Set[str]] = {}

        # speaker name -> chain_ids
        self._speaker_to_chains: Dict[str, Set[str]] = {}

        # chain_id -> chain (for fast lookup)
        self._chains: Dict[str, BaseContinuityChain] = {}

        # All chains by type
        self._character_chains: List[CharacterContinuityChain] = []
        self._action_chains: List[ActionContinuityChain] = []
        self._environment_chains: List[EnvironmentContinuityChain] = []
        self._dialogue_chains: List[DialogueContinuityChain] = []

        # Index built flag
        self._is_built: bool = False

    def add_chain(self, chain: BaseContinuityChain) -> None:
        """Add a chain to the index.

        Args:
            chain: Any continuity chain to index
        """
        self._is_built = False
        chain_id = chain.chain_id
        self._chains[chain_id] = chain

        # Index by scene IDs
        for scene_id in chain.ordered_scene_ids:
            if scene_id not in self._scene_to_chains:
                self._scene_to_chains[scene_id] = set()
            self._scene_to_chains[scene_id].add(chain_id)

        # Index by type
        if isinstance(chain, CharacterContinuityChain):
            self._character_chains.append(chain)
            for char in chain.characters:
                if char not in self._character_to_chains:
                    self._character_to_chains[char] = set()
                self._character_to_chains[char].add(chain_id)

        elif isinstance(chain, ActionContinuityChain):
            self._action_chains.append(chain)
            for action in chain.actions:
                if action not in self._action_to_chains:
                    self._action_to_chains[action] = set()
                self._action_to_chains[action].add(chain_id)

        elif isinstance(chain, EnvironmentContinuityChain):
            self._environment_chains.append(chain)
            for env in chain.environments:
                if env not in self._environment_to_chains:
                    self._environment_to_chains[env] = set()
                self._environment_to_chains[env].add(chain_id)

        elif isinstance(chain, DialogueContinuityChain):
            self._dialogue_chains.append(chain)
            for speaker in chain.speakers:
                if speaker not in self._speaker_to_chains:
                    self._speaker_to_chains[speaker] = set()
                self._speaker_to_chains[speaker].add(chain_id)

    def build(self) -> None:
        """Finalize index building. Converts sets to frozen sets for immutability."""
        # Convert mutable sets to frozen sets for immutability
        self._scene_to_chains = {
            k: frozenset(v) for k, v in self._scene_to_chains.items()
        }
        self._character_to_chains = {
            k: frozenset(v) for k, v in self._character_to_chains.items()
        }
        self._action_to_chains = {
            k: frozenset(v) for k, v in self._action_to_chains.items()
        }
        self._environment_to_chains = {
            k: frozenset(v) for k, v in self._environment_to_chains.items()
        }
        self._speaker_to_chains = {
            k: frozenset(v) for k, v in self._speaker_to_chains.items()
        }
        self._is_built = True

    def get_chain(self, chain_id: str) -> Optional[BaseContinuityChain]:
        """Get chain by ID."""
        return self._chains.get(chain_id)

    def get_chains_for_scene(self, scene_id: str) -> List[BaseContinuityChain]:
        """Get all chains containing a scene.

        Args:
            scene_id: Scene identifier

        Returns:
            List of chains containing this scene
        """
        chain_ids = self._scene_to_chains.get(scene_id, set())
        return [self._chains[cid] for cid in chain_ids if cid in self._chains]

    def get_chains_for_character(
        self,
        character: str,
    ) -> List[CharacterContinuityChain]:
        """Get all chains containing a character.

        Args:
            character: Character name (normalized)

        Returns:
            List of character chains containing this character
        """
        chain_ids = self._character_to_chains.get(character, set())
        return [self._chains[cid] for cid in chain_ids
                if cid in self._chains and
                isinstance(self._chains[cid], CharacterContinuityChain)]

    def get_chains_for_action(
        self,
        action: str,
    ) -> List[ActionContinuityChain]:
        """Get all chains containing an action.

        Args:
            action: Action name (normalized)

        Returns:
            List of action chains containing this action
        """
        chain_ids = self._action_to_chains.get(action, set())
        return [self._chains[cid] for cid in chain_ids
                if cid in self._chains and
                isinstance(self._chains[cid], ActionContinuityChain)]

    def get_chains_for_environment(
        self,
        environment: str,
    ) -> List[EnvironmentContinuityChain]:
        """Get all chains containing an environment.

        Args:
            environment: Environment/location name

        Returns:
            List of environment chains containing this location
        """
        chain_ids = self._environment_to_chains.get(environment, set())
        return [self._chains[cid] for cid in chain_ids
                if cid in self._chains and
                isinstance(self._chains[cid], EnvironmentContinuityChain)]

    def get_chains_for_speaker(
        self,
        speaker: str,
    ) -> List[DialogueContinuityChain]:
        """Get all chains containing a speaker.

        Args:
            speaker: Speaker name

        Returns:
            List of dialogue chains containing this speaker
        """
        chain_ids = self._speaker_to_chains.get(speaker, set())
        return [self._chains[cid] for cid in chain_ids
                if cid in self._chains and
                isinstance(self._chains[cid], DialogueContinuityChain)]

    @property
    def all_chains(self) -> List[BaseContinuityChain]:
        """Get all indexed chains."""
        return list(self._chains.values())

    @property
    def character_chains(self) -> List[CharacterContinuityChain]:
        """Get all character chains."""
        return list(self._character_chains)

    @property
    def action_chains(self) -> List[ActionContinuityChain]:
        """Get all action chains."""
        return list(self._action_chains)

    @property
    def environment_chains(self) -> List[EnvironmentContinuityChain]:
        """Get all environment chains."""
        return list(self._environment_chains)

    @property
    def dialogue_chains(self) -> List[DialogueContinuityChain]:
        """Get all dialogue chains."""
        return list(self._dialogue_chains)

    def to_dict(self) -> Dict:
        """Serialize index to deterministic dict."""
        return {
            "chain_count": len(self._chains),
            "character_chain_count": len(self._character_chains),
            "action_chain_count": len(self._action_chains),
            "environment_chain_count": len(self._environment_chains),
            "dialogue_chain_count": len(self._dialogue_chains),
            "indexed_scenes": sorted(self._scene_to_chains.keys()),
            "indexed_characters": sorted(self._character_to_chains.keys()),
            "indexed_actions": sorted(self._action_to_chains.keys()),
            "indexed_environments": sorted(self._environment_to_chains.keys()),
            "indexed_speakers": sorted(self._speaker_to_chains.keys()),
        }


# ---------------------------------------------------------------------------
# Query integration hooks (NON-AI retrieval)
# ---------------------------------------------------------------------------


class ContinuityQueryHooks:
    """Query integration hooks for continuity chain retrieval.

    These are deterministic retrieval hooks - NO AI, NO embeddings.
    Future semantic ranking will be added separately.
    """

    def __init__(self, index: ContinuityGraphIndex) -> None:
        """Initialize with index.

        Args:
            index: Pre-built ContinuityGraphIndex
        """
        self.index = index

    def retrieve_by_character(
        self,
        character: str,
        min_continuity_score: float = 0.0,
    ) -> List[CharacterContinuityChain]:
        """Retrieve continuity chains by character.

        Args:
            character: Character name (normalized)
            min_continuity_score: Minimum continuity score filter

        Returns:
            Character chains containing this character
        """
        chains = self.index.get_chains_for_character(character)
        if min_continuity_score > 0:
            chains = [c for c in chains if c.continuity_score >= min_continuity_score]
        return sorted(chains, key=lambda c: -c.continuity_score)

    def retrieve_by_action(
        self,
        action: str,
        min_continuity_score: float = 0.0,
    ) -> List[ActionContinuityChain]:
        """Retrieve continuity chains by action.

        Args:
            action: Action name (normalized)
            min_continuity_score: Minimum continuity score filter

        Returns:
            Action chains containing this action
        """
        chains = self.index.get_chains_for_action(action)
        if min_continuity_score > 0:
            chains = [c for c in chains if c.continuity_score >= min_continuity_score]
        return sorted(chains, key=lambda c: -c.continuity_score)

    def retrieve_by_environment(
        self,
        environment: str,
        min_continuity_score: float = 0.0,
    ) -> List[EnvironmentContinuityChain]:
        """Retrieve continuity chains by environment.

        Args:
            environment: Environment/location name
            min_continuity_score: Minimum continuity score filter

        Returns:
            Environment chains containing this location
        """
        chains = self.index.get_chains_for_environment(environment)
        if min_continuity_score > 0:
            chains = [c for c in chains if c.continuity_score >= min_continuity_score]
        return sorted(chains, key=lambda c: -c.continuity_score)

    def retrieve_by_scene(self, scene_id: str) -> List[BaseContinuityChain]:
        """Retrieve all chains containing a scene.

        Args:
            scene_id: Scene identifier

        Returns:
            All chains containing this scene
        """
        return self.index.get_chains_for_scene(scene_id)

    def retrieve_chains_covering_time_range(
        self,
        start_time: float,
        end_time: float,
        chain_type: Optional[ChainType] = None,
    ) -> List[BaseContinuityChain]:
        """Retrieve chains that cover a time range.

        This uses metadata from scenes to determine coverage.
        This is a placeholder for future temporal indexing.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
            chain_type: Optional chain type filter

        Returns:
            Chains that potentially cover this time range
        """
        # For now, return all chains of type
        if chain_type == ChainType.CHARACTER:
            chains = self.index.character_chains
        elif chain_type == ChainType.ACTION:
            chains = self.index.action_chains
        elif chain_type == ChainType.ENVIRONMENT:
            chains = self.index.environment_chains
        elif chain_type == ChainType.DIALOGUE:
            chains = self.index.dialogue_chains
        else:
            chains = self.index.all_chains

        # Filter by temporal span (placeholder - actual implementation
        # would need scene timing metadata in chains)
        return chains


__all__ = [
    "ContinuityGraphIndex",
    "ContinuityQueryHooks",
]