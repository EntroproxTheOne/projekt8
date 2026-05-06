from video_pipeline.models import WordTimestamp
from video_pipeline.subtitles import active_word_index, group_words, render_subtitle_html


def test_group_words_limits_group_size():
    words = [WordTimestamp(word=f"w{i}", start=i * 0.2, end=i * 0.2 + 0.1) for i in range(10)]

    groups = group_words(words, max_words=4)

    assert [len(group) for group in groups] == [4, 4, 2]


def test_active_word_index_finds_current_word():
    words = [
        WordTimestamp(word="hello", start=0.0, end=0.3),
        WordTimestamp(word="world", start=0.3, end=0.6),
    ]

    assert active_word_index(words, 0.4) == 1


def test_render_subtitle_html_marks_active_word():
    words = [
        WordTimestamp(word="hello", start=0.0, end=0.3),
        WordTimestamp(word="world", start=0.3, end=0.6),
    ]

    html = render_subtitle_html(words, active_index=1)

    assert "subtitle-active" in html
    assert "world" in html
