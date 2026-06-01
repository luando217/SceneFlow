"""Tests for TextNormalizer and EntityNormalizer."""

from aicore.semantic.normalizer.text_normalizer import TextNormalizer
from aicore.semantic.normalizer.entity_normalizer import EntityNormalizer


class TestTextNormalizer:
    """Tests for deterministic ASR/OCR text normalization."""

    def setup_method(self):
        self.normalizer = TextNormalizer()

    def test_normalize_dialogue_basic(self):
        result = self.normalizer.normalize_dialogue("  Hello world!  ")
        assert result == "Hello world!"

    def test_normalize_dialogue_strip_accents(self):
        result = self.normalizer.normalize_dialogue("Café résumé")
        assert "é" not in result
        assert "e" in result

    def test_normalize_dialogue_zero_width(self):
        result = self.normalizer.normalize_dialogue("Hello\u200bWorld")
        assert result == "HelloWorld"

    def test_normalize_dialogue_collapse_newlines(self):
        result = self.normalizer.normalize_dialogue("Line1\n\n\nLine2")
        assert result == "Line1 Line2"

    def test_normalize_dialogue_preserve_case(self):
        result = self.normalizer.normalize_dialogue("I AM Naruto!")
        assert result == "I AM Naruto!"

    def test_normalize_ocr_basic(self):
        result = self.normalizer.normalize_ocr("  EPISODE 1  ")
        assert result == "episode 1"

    def test_normalize_ocr_lowercase(self):
        result = self.normalizer.normalize_ocr("HELLO WORLD")
        assert result == "hello world"

    def test_normalize_ocr_remove_newlines(self):
        result = self.normalizer.normalize_ocr("Line1\nLine2\nLine3")
        assert result == "line1 line2 line3"

    def test_normalize_ocr_strip_accents(self):
        result = self.normalizer.normalize_ocr("Pokémon")
        assert result == "pokemon"

    def test_normalize_and_merge(self):
        dia, ocr = self.normalizer.normalize_and_merge(
            dialogue="  Hello!  ", ocr="  WORLD  "
        )
        assert dia == "Hello!"
        assert ocr == "world"

    def test_strip_fillers(self):
        result = self.normalizer.strip_fillers(
            "I um went to like the store you know"
        )
        assert result == "I went to the store"

    def test_strip_fillers_no_change(self):
        result = self.normalizer.strip_fillers("I went to the store")
        assert result == "I went to the store"

    def test_empty_input(self):
        assert self.normalizer.normalize_dialogue("") == ""
        assert self.normalizer.normalize_ocr("") == ""


class TestEntityNormalizer:
    """Tests for entity name normalization."""

    def setup_method(self):
        self.normalizer = EntityNormalizer()

    def test_normalize_character_basic(self):
        entities = self.normalizer.normalize_character_batch(
            ["Naruto", "Sasuke"]
        )
        assert len(entities) == 2
        assert entities[0].normalized_name == "naruto"
        assert entities[1].normalized_name == "sasuke"

    def test_normalize_character_deduplicates(self):
        entities = self.normalizer.normalize_character_batch(
            ["Naruto", "NARUTO", "naruto  "]
        )
        assert len(entities) == 1
        assert entities[0].normalized_name == "naruto"

    def test_normalize_character_empty_skipped(self):
        entities = self.normalizer.normalize_character_batch(
            ["Naruto", "", "Sasuke", " "]
        )
        assert len(entities) == 2

    def test_normalize_action(self):
        action = self.normalizer.normalize_action(
            "RUNNING", confidence=0.8
        )
        assert action.normalized_name == "running"
        assert action.confidence == 0.8

    def test_normalize_object(self):
        obj = self.normalizer.normalize_object(
            "Kunai Knife", confidence=0.9
        )
        assert obj.normalized_name == "kunai knife"
        assert obj.confidence == 0.9

    def test_normalize_emotion(self):
        emotion = self.normalizer.normalize_emotion(
            "ANGRY", confidence=0.85
        )
        assert emotion.normalized_name == "angry"
        assert emotion.confidence == 0.85

    def test_normalize_environment(self):
        env = self.normalizer.normalize_environment(
            "FOREST CLEARING",
            location="outdoors",
            confidence=0.7,
        )
        assert env.normalized_name == "forest clearing"
        assert env.location == "outdoors"
        assert env.confidence == 0.7

