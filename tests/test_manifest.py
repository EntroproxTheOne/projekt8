from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest


def test_create_manifest_makes_expected_directories(tmp_path):
    paths = RunPaths(base_dir=tmp_path, run_id="run-a")
    manifest = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")

    assert manifest.run_id == "run-a"
    assert paths.audio_dir.exists()
    assert paths.timestamps_dir.exists()
    assert paths.images_dir.exists()


def test_save_and_reload_manifest_preserves_scene_status(tmp_path):
    paths = RunPaths(base_dir=tmp_path, run_id="run-a")
    manifest = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")
    manifest.scene_status(1).audio_path = "audio/wav_001.wav"
    save_manifest(paths, manifest)

    reloaded = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")

    assert reloaded.scene_status(1).audio_path == "audio/wav_001.wav"
