import pytest

from video_pipeline.models import WordTimestamp
from video_pipeline.timestamps import estimate_word_timestamps, offset_timestamps, validate_word_timestamps


def test_validate_rejects_missing_timestamps():
    with pytest.raises(ValueError, match="word-level timestamps"):
        validate_word_timestamps([])


def test_validate_rejects_non_increasing_times():
    words = [
        WordTimestamp(word="one", start=0.5, end=0.8),
        WordTimestamp(word="two", start=0.7, end=1.0),
    ]

    with pytest.raises(ValueError, match="overlap"):
        validate_word_timestamps(words)


def test_offset_timestamps_adds_scene_offset():
    words = [WordTimestamp(word="hello", start=0.0, end=0.4)]

    shifted = offset_timestamps(words, offset_seconds=10.0)

    assert shifted[0].start == 10.0
    assert shifted[0].end == 10.4


def test_estimate_word_timestamps_spreads_words_over_duration():
    words = estimate_word_timestamps("hello world again", duration_seconds=3.0)

    assert [item.word for item in words] == ["hello", "world", "again"]
    assert words[0].start == 0.0
    assert words[-1].end == 3.0
