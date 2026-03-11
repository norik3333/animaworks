"""Unit tests for RepetitionDetector (core.execution.base)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.execution.base import RepetitionDetector


class TestRepetitionDetector:
    """Tests for RepetitionDetector feed() and check_full_text()."""

    def test_no_detection_below_min_tokens(self) -> None:
        """Feed less than 100 words, should not trigger."""
        detector = RepetitionDetector()
        # 99 words of repeated "a b c d" (25 times = 100 words, but we need 99)
        words = ["a", "b", "c", "d"] * 24 + ["a", "b", "c"]  # 99 words
        text = " ".join(words)
        assert detector.feed(text) is False

    def test_detection_of_repeated_ngram(self) -> None:
        """Feed 100+ words with a repeated pattern appearing 10+ times, should trigger.

        With defaults n=10/threshold=10, a 4-word cycle repeated 13 times yields
        11 distinct 10-gram occurrences (>=threshold), so detection fires.
        """
        detector = RepetitionDetector()
        # "x y z w" repeated 13 times = 52 words; 10-gram appears 11 times (>=threshold=10)
        repeated = ["x", "y", "z", "w"] * 13  # 52 words
        pad = [f"word{i}" for i in range(80)]  # 80 unique words
        text = " ".join(pad + repeated)
        assert detector.feed(text) is True

    def test_no_false_positive_on_normal_text(self) -> None:
        """Feed 200 words of varied natural text, should not trigger."""
        detector = RepetitionDetector()
        # 200 unique words
        words = [f"word{i}" for i in range(200)]
        text = " ".join(words)
        assert detector.feed(text) is False

    def test_check_full_text_detects_repetition(self) -> None:
        """Use check_full_text() on repeated text.

        With defaults n=10/threshold=10, a 4-word cycle repeated 13 times yields
        11 distinct 10-gram occurrences (>=threshold), so detection fires.
        """
        detector = RepetitionDetector()
        # 4-word cycle repeated 13 times = 52 words; 10-gram appears 11 times (>=threshold=10)
        repeated = ["alpha", "beta", "gamma", "delta"] * 13  # 52 words
        pad = [f"unique{i}" for i in range(90)]  # 90 words
        text = " ".join(pad + repeated)
        assert detector.check_full_text(text) is True

    def test_check_full_text_no_detection_below_threshold(self) -> None:
        """Use check_full_text() on short text."""
        detector = RepetitionDetector()
        text = "short text with fewer than 100 words " * 2
        assert detector.check_full_text(text) is False

    def test_custom_parameters(self) -> None:
        """Test with custom n, threshold, min_tokens."""
        # n=3, threshold=4, min_tokens=20
        detector = RepetitionDetector(n=3, threshold=4, min_tokens=20)
        # "a b c" repeated 4 times = 12 words, pad to 20+
        repeated = ["a", "b", "c"] * 4
        pad = ["x", "y", "z", "w", "p", "q", "r", "s"]
        text = " ".join(pad + repeated)
        assert detector.check_full_text(text) is True

    def test_feed_small_chunks_one_word_at_a_time(self) -> None:
        """Feeding one word at a time still detects repetition correctly."""
        detector = RepetitionDetector(n=4, threshold=5, min_tokens=20)
        pad = [f"w{i}" for i in range(20)]
        repeated = ["a", "b", "c", "d"] * 6
        words = pad + repeated
        detected = False
        for w in words:
            if detector.feed(w):
                detected = True
                break
        assert detected is True

    def test_feed_empty_text_ignored(self) -> None:
        """Empty text chunks are silently ignored."""
        detector = RepetitionDetector()
        assert detector.feed("") is False
        assert detector.feed("   ") is False
        assert len(detector._tokens) == 0
