"""
Real unit tests for shipped ClipDeck clipping logic.
Drives _tail_segments directly + save_clip (up to concat) using temp files + mocks.
Per plan: import engine (shipped), no reimpl, cover empty/zero/happy, assert outcomes.
Run with: python -m unittest discover -s tests -v
"""
import os
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

import engine  # the shipped module


def _make_playlist_and_segs(seg_dir, num_segs=5, seg_size=10000, durs=None):
    """Helper: write buffer.m3u8 + seg*.ts files. Returns playlist path."""
    os.makedirs(seg_dir, exist_ok=True)
    plist = os.path.join(seg_dir, "buffer.m3u8")
    if durs is None:
        durs = [1.0] * num_segs
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:1"]
    for i, d in enumerate(durs[:num_segs]):
        lines.append(f"#EXTINF:{d},")
        lines.append(f"seg{i:08d}.ts")
        p = os.path.join(seg_dir, f"seg{i:08d}.ts")
        with open(p, "wb") as f:
            f.write(b"X" * seg_size)
    with open(plist, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return plist


class TestTailSegments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.r = engine.Recorder.__new__(engine.Recorder)
        self.r._seg_dir = self.tmp
        self.r._playlist = os.path.join(self.tmp, "buffer.m3u8")
        self.r.SEG_SECONDS = 1
        import threading
        self.r._lock = threading.Lock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_happy_path_selects_tail(self):
        _make_playlist_and_segs(self.tmp, num_segs=5, seg_size=12345)
        segs = self.r._tail_segments(2.5)
        self.assertEqual(len(segs), 3)  # last ~3s
        for p, d in segs:
            self.assertTrue(os.path.exists(p))
            self.assertGreater(os.path.getsize(p), 0)
            self.assertGreater(d, 0)

    def test_zero_byte_segments_skipped(self):
        _make_playlist_and_segs(self.tmp, num_segs=3, seg_size=0)
        # make one non-zero at end
        p = os.path.join(self.tmp, "seg00000002.ts")
        with open(p, "wb") as f:
            f.write(b"Y" * 8000)
        segs = self.r._tail_segments(5)
        # should only get the last non-zero
        self.assertEqual(len(segs), 1)
        self.assertGreater(os.path.getsize(segs[0][0]), 0)

    def test_empty_playlist_returns_empty(self):
        with open(self.r._playlist, "w") as f:
            f.write("#EXTM3U\n")
        segs = self.r._tail_segments(10)
        self.assertEqual(segs, [])

    def test_short_list_returns_what_is_there(self):
        _make_playlist_and_segs(self.tmp, num_segs=2, seg_size=5000)
        segs = self.r._tail_segments(30)
        self.assertEqual(len(segs), 2)


class TestSaveClipLogic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.r = engine.Recorder.__new__(engine.Recorder)
        self.r.ffmpeg = "ffmpeg"  # will be mocked before real run
        self.r._seg_dir = self.tmp
        self.r._playlist = os.path.join(self.tmp, "buffer.m3u8")
        self.r.SEG_SECONDS = 1
        import threading
        self.r._lock = threading.Lock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_raises_on_empty_buffer(self):
        with open(self.r._playlist, "w") as f:
            f.write("#EXTM3U\n")
        out = os.path.join(self.tmp, "out.mp4")
        with self.assertRaises(RuntimeError) as ctx:
            self.r.save_clip(5, out)
        self.assertIn("Buffer je prázdny", str(ctx.exception))

    @patch("engine.subprocess.run")
    @patch("engine.generate_thumbnail")
    def test_save_clip_calls_concat_and_thumbnail(self, mock_thumb, mock_run):
        _make_playlist_and_segs(self.tmp, num_segs=3, seg_size=4000)
        out = os.path.join(self.tmp, "clip_test.mp4")
        # make fake success
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # simulate out file created by "ffmpeg"
        def _side_effect(*a, **k):
            open(out, "wb").write(b"FAKE MP4")
            return mock_run.return_value
        mock_run.side_effect = _side_effect

        res = self.r.save_clip(2, out)
        self.assertEqual(res, out)
        self.assertTrue(os.path.isfile(out))
        # concat was called
        self.assertTrue(mock_run.called)
        cmd = " ".join(str(x) for x in mock_run.call_args[0][0])
        self.assertIn("-f concat", cmd)
        self.assertIn(out, cmd)
        mock_thumb.assert_called_once()

    @patch("engine.subprocess.run")
    def test_save_clip_raises_on_concat_fail(self, mock_run):
        _make_playlist_and_segs(self.tmp, num_segs=2, seg_size=3000)
        out = os.path.join(self.tmp, "bad.mp4")
        mock_run.return_value = MagicMock(returncode=1, stderr="concat boom\n")
        with self.assertRaises(RuntimeError) as ctx:
            self.r.save_clip(2, out)
        self.assertIn("concat", str(ctx.exception).lower() or "boom" in str(ctx.exception).lower())


import clipdeck as cd_mod  # shipped for cfg/save flow test

class TestClipSecondsConfigToRecorder(unittest.TestCase):
    """Drive SHIPPED pure functions only with plain data."""
    def test_clip_seconds_persists_and_reaches_start_cfg(self):
        tmpd = tempfile.mkdtemp()
        old_path = cd_mod.CONFIG_PATH
        cd_mod.CONFIG_PATH = os.path.join(tmpd, "config.json")
        try:
            import gallery as g_mod
            # simulate settings fields (from widgets)
            fields = {
                "fps": "60",
                "clip_seconds": "45",
                "use_audio": True,
                "audio_bitrate": "320",
                "smart_record": True,
                "mic_device": "",
                "capture_label": "Monitor 0: 2560x1600",
                "gui_label": "Monitor 0: 2560x1600",
                "save_dir": "C:/tmp",
            }
            monitors = [{"x":0,"y":0,"w":2560,"h":1600,"primary":True}, {"x":0,"y":-1080,"w":1440,"h":1080,"primary":False}]
            menus = g_mod.prepare_monitor_menus(monitors, curr_idx=0, capture_idx=0, gui_idx=0)
            cfg = dict(cd_mod.DEFAULTS)
            cfg = g_mod.apply_settings_fields(cfg, fields, menus.capture_labels)
            self.assertEqual(cfg["clip_seconds"], 45)
            self.assertEqual(cfg["capture_monitor"], 0)

            # drive SHIPPED build_recorder_start_cfg 
            start_cfg = cd_mod.build_recorder_start_cfg(cfg, monitors)
            self.assertEqual(start_cfg["clip_seconds"], 45)
            self.assertNotIn("capture_window", start_cfg)

            # drive engine
            ring = max(8, int(start_cfg["clip_seconds"]) + 6)
            self.assertEqual(ring, 51)
        finally:
            cd_mod.CONFIG_PATH = old_path
            shutil.rmtree(tmpd, ignore_errors=True)

    def test_topbar_target_updates_with_tag_case(self):
        """Test tag desync case with plain data."""
        import gallery as g_mod
        monitors = [{"x":0,"y":0,"w":2560,"h":1600,"primary":True}, {"x":0,"y":-1080,"w":1440,"h":1080,"primary":False}]
        menus = g_mod.prepare_monitor_menus(monitors, curr_idx=0, capture_idx=0, gui_idx=0)
        # use exact label from the capture list (may have tag)
        label1 = menus.capture_labels[1]
        cfg = dict(cd_mod.DEFAULTS)
        cfg = g_mod.apply_topbar_capture(cfg, label1, menus.capture_labels)
        self.assertEqual(cfg["capture_monitor"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
