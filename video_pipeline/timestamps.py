import re

from video_pipeline.models import WordTimestamp


def validate_word_timestamps(words: list[WordTimestamp]) -> list[WordTimestamp]:
    if not words:
        raise ValueError("audio provider must return word-level timestamps")
    previous_end = 0.0
    for word in words:
        if word.end <= word.start:
            raise ValueError(f"timestamp for {word.word!r} has end before start")
        if word.start < previous_end:
            raise ValueError(f"timestamp overlap before {word.word!r}")
        previous_end = word.end
    return words


def offset_timestamps(words: list[WordTimestamp], offset_seconds: float) -> list[WordTimestamp]:
    return [
        WordTimestamp(word=item.word, start=round(item.start + offset_seconds, 4), end=round(item.end + offset_seconds, 4))
        for item in words
    ]


def estimate_word_timestamps(text: str, duration_seconds: float) -> list[WordTimestamp]:
    tokens = re.findall(r"[\w']+|[^\w\s]", text, flags=re.UNICODE)
    if not tokens:
        raise ValueError("cannot estimate timestamps for empty text")
    step = max(duration_seconds, 0.01) / len(tokens)
    words = []
    for index, token in enumerate(tokens):
        start = round(index * step, 4)
        end = round(duration_seconds if index == len(tokens) - 1 else (index + 1) * step, 4)
        words.append(WordTimestamp(word=token, start=start, end=max(end, start + 0.01)))
    return validate_word_timestamps(words)
