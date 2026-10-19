"""Run with python3 -m unittest discover -s motion_editor -p 'test_*.py'."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


BASE = Path(__file__).resolve().parent


class MotionIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        shutil.copy2(BASE / "generate_motion_index.py", self.base)
        shutil.copy2(BASE / "common_states.json", self.base)
        shutil.copytree(BASE / "motions", self.base / "motions")
        self.output = self.base / "motions/index.json"

    def run_script(self, success=True):
        result = subprocess.run(
            [sys.executable, str(self.base / "generate_motion_index.py")],
            cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def write_motion(self, name, data):
        path = self.base / "motions" / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_all_real_data_and_repeatability(self):
        self.run_script()
        original = self.output.read_bytes()
        index = json.loads(original)
        self.assertEqual(index["format"], "robi-motion-index-v1")
        sources = {p.name: json.loads(p.read_text(encoding="utf-8"))
                   for p in (BASE / "motions").glob("*.json") if p.name != "index.json"}
        self.assertEqual({m["file"] for m in index["motions"]}, set(sources))
        states = json.loads((BASE / "common_states.json").read_text(encoding="utf-8"))
        names = {s["id"]: s["name"] for s in states["states"]}
        for motion in index["motions"]:
            source = sources[motion["file"]]
            for key in ("name", "description", "start_state", "end_state"):
                self.assertEqual(motion[key], source[key])
            for side in ("start", "end"):
                self.assertEqual(motion[side + "_state_name"], names.get(source[side + "_state"]))
            self.assertEqual(motion["frame_count"], len(source["frames"]))
            self.assertEqual(motion["duration_ms"], sum(f["duration_ms"] for f in source["frames"]))
        bye = next(m for m in index["motions"] if m["id"] == "003")
        self.assertEqual((bye["name"], bye["description"], bye["frame_count"], bye["duration_ms"]),
                         ("バイバイ", "右手で正面にバイバイ", 7, 5400))
        self.assertEqual(bye["start_state_name"], "立ち姿")
        self.assertEqual(bye["end_state_name"], "立ち姿")
        self.run_script()
        self.assertEqual(self.output.read_bytes(), original)

    def fixture(self):
        return {"description": "説明を保持", "start_state": "unknown", "end_state": None,
                "frames": [{"type": kind, "duration_ms": value}
                           for kind, value in zip(("pose", "delay", "audio", "torque"), (1, 2.5, 0, 3))]}

    def test_rescan_fallback_mixed_frames_sort_and_ignore(self):
        path = self.write_motion("100_追加.json", self.fixture())
        self.write_motion("30_先.json", self.fixture())
        (self.base / "motions/notes.txt").write_text("not JSON")
        nested = self.base / "motions/nested"
        nested.mkdir()
        (nested / "bad.json").write_text("invalid")
        self.output.write_text("invalid old index")
        self.run_script()
        motions = json.loads(self.output.read_text(encoding="utf-8"))["motions"]
        self.assertEqual([m["id"] for m in motions][-2:], ["30", "100"])
        added = motions[-1]
        self.assertEqual(added["name"], "追加")
        self.assertEqual((added["frame_count"], added["duration_ms"]), (4, 6.5))
        self.assertIsNone(added["start_state_name"])
        self.assertIsNone(added["end_state_name"])
        data = self.fixture()
        data["description"] = "変更"
        self.write_motion(path.name, data)
        self.run_script()
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["motions"][-1]["description"], "変更")
        path.unlink()
        self.run_script()
        self.assertNotIn("100", [m["id"] for m in json.loads(self.output.read_text())["motions"]])

    def test_invalid_inputs_preserve_index(self):
        self.run_script()
        original = self.output.read_bytes()
        fixtures = [("100_bad.json", "{"), ("003_duplicate.json", self.fixture()),
                    ("3_duplicate.json", self.fixture()), ("no_id.json", self.fixture()),
                    ("100_bad.json", []), ("100_bad.json", {})]
        for key in ("description", "start_state", "end_state", "frames"):
            data = self.fixture()
            del data[key]
            fixtures.append(("100_bad.json", data))
        for value in (None, "100", True, -1, float("nan"), float("inf")):
            data = self.fixture()
            data["frames"][0]["duration_ms"] = value
            fixtures.append(("100_bad.json", data))
        for frames in ([{}], [None], {}, None):
            data = self.fixture()
            data["frames"] = frames
            fixtures.append(("100_bad.json", data))
        for name, data in fixtures:
            with self.subTest(name=name, data=data):
                path = self.base / "motions" / name
                if isinstance(data, str):
                    path.write_text(data)
                else:
                    self.write_motion(name, data)
                result = self.run_script(success=False)
                self.assertIn(name, result.stderr)
                self.assertEqual(self.output.read_bytes(), original)
                path.unlink()

    def test_bad_common_states_preserves_index(self):
        self.run_script()
        original = self.output.read_bytes()
        path = self.base / "common_states.json"
        for data in ({}, {"states": [{}]}, {"states": [{"id": "x", "name": "a"}] * 2}):
            path.write_text(json.dumps(data))
            result = self.run_script(success=False)
            self.assertIn("common_states.json", result.stderr)
            self.assertEqual(self.output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
