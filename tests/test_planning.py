import pytest

from video_pipeline.planning import build_planner_prompt, parse_video_plan


def test_build_planner_prompt_includes_duration_targets():
    prompt = build_planner_prompt("Ocean myths", target_word_count=300, suggested_image_count=24)

    assert "Ocean myths" in prompt
    assert "300 words" in prompt
    assert "24" in prompt
    assert "scenes" in prompt


def test_build_planner_prompt_contains_fixed_human_voiceover_agent_prompt():
    prompt = build_planner_prompt("Ocean myths", target_word_count=300, suggested_image_count=24)

    assert "human, real sounding essay" in prompt
    assert "short pauses" in prompt
    assert "not AI-written" in prompt
    assert "contractions" in prompt


def test_parse_video_plan_rejects_empty_scene_prompt():
    payload = {
        "scenes": [{"paragraph_index": 1, "narration": "Hello world", "image_prompt": ""}],
        "thumbnail_prompt": "A bright thumbnail",
        "title_and_description": {"title": "Title", "description": "Description"},
    }

    with pytest.raises(ValueError, match="image_prompt"):
        parse_video_plan(payload)


def test_parse_video_plan_normalizes_scene_order():
    payload = {
        "scenes": [
            {"paragraph_index": 2, "narration": "Second", "image_prompt": "Second image"},
            {"paragraph_index": 1, "narration": "First", "image_prompt": "First image"},
        ],
        "thumbnail_prompt": "Thumb",
        "title_and_description": {"title": "Title", "description": "Description"},
    }

    plan = parse_video_plan(payload)

    assert [scene.paragraph_index for scene in plan.scenes] == [1, 2]
