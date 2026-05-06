from video_pipeline.assembly import distribute_clip_durations


def test_distribute_clip_durations_uses_audio_durations():
    durations = distribute_clip_durations([1.0, 2.5, 3.0])

    assert durations == [1.0, 2.5, 3.0]
