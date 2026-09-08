from video_pipeline.models import WordTimestamp


def estimate_word_timestamps(text: str, total_duration: float | None = None) -> list[WordTimestamp]:
    words = [word.strip() for word in text.split() if word.strip()]
    if not words:
        return []
    duration = total_duration or max(1.0, len(words) * 0.36)
    step = duration / len(words)
    return [
        WordTimestamp(word=word, start=round(index * step, 3), end=round((index + 1) * step, 3))
        for index, word in enumerate(words)
    ]


def validate_word_timestamps(words: list[WordTimestamp]) -> None:
    last_end = -0.001
    for word in words:
        if word.end <= word.start:
            raise ValueError(f"Invalid timestamp for {word.word}: end must be after start")
        if word.start < last_end - 0.05:
            raise ValueError(f"Invalid timestamp order near {word.word}")
        last_end = word.end


def offset_timestamps(words: list[WordTimestamp], offset: float) -> list[WordTimestamp]:
    return [
        WordTimestamp(word=item.word, start=item.start + offset, end=item.end + offset)
        for item in words
    ]
