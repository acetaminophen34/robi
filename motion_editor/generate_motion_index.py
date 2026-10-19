#!/usr/bin/env python3
"""Generate motion metadata without modifying source motions.

duration_ms sums recorded frame times, regardless of frame type. It does not
represent actual audio playback time or guarantee hardware completion time.
Missing names use the filename; descriptions and state fields are required
(state values may be null). Unknown state IDs resolve to a null state name.
"""

import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile


def reject_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def read_object(path):
    with path.open(encoding="utf-8") as source:
        data = json.load(source, parse_constant=reject_constant)
    if not isinstance(data, dict):
        raise ValueError("root must be an object")
    return data


def load_state_names(path):
    data = read_object(path)
    if not isinstance(data.get("states"), list):
        raise ValueError("states must be an array")
    names = {}
    for i, state in enumerate(data["states"]):
        if not isinstance(state, dict):
            raise ValueError("states[{}] must be an object".format(i))
        state_id, name = state.get("id"), state.get("name")
        if not isinstance(state_id, str) or not state_id:
            raise ValueError("states[{}].id must be a nonempty string".format(i))
        if not isinstance(name, str):
            raise ValueError("states[{}].name must be a string".format(i))
        if state_id in names:
            raise ValueError("duplicate state ID: " + state_id)
        names[state_id] = name
    return names


def extract_motion(path, motion_id, state_names):
    data = read_object(path)
    fallback = path.stem[len(motion_id):].lstrip("_ -") or motion_id
    name = data.get("name", fallback)
    if not isinstance(name, str):
        raise ValueError("name must be a string")
    if not isinstance(data.get("description"), str):
        raise ValueError("description is required and must be a string")
    for key in ("start_state", "end_state"):
        if key not in data or (data[key] is not None and not isinstance(data[key], str)):
            raise ValueError(key + " is required and must be a string or null")
    frames = data.get("frames")
    if not isinstance(frames, list):
        raise ValueError("frames is required and must be an array")
    duration = 0
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError("frames[{}] must be an object".format(i))
        value = frame.get("duration_ms")
        if (type(value) not in (int, float) or value < 0
                or (isinstance(value, float) and not math.isfinite(value))):
            raise ValueError("frames[{}].duration_ms must be a finite nonnegative number".format(i))
        duration += value
    if isinstance(duration, float) and not math.isfinite(duration):
        raise ValueError("total duration_ms must be finite")
    return {
        "id": motion_id,
        "name": name,
        "description": data["description"],
        "file": path.name,
        "start_state": data["start_state"],
        "start_state_name": state_names.get(data["start_state"]),
        "end_state": data["end_state"],
        "end_state_name": state_names.get(data["end_state"]),
        "duration_ms": duration,
        "frame_count": len(frames),
    }


def generate_index(base_dir):
    """Validate all inputs before atomically replacing motions/index.json."""
    errors = []
    states_path = base_dir / "common_states.json"
    try:
        state_names = load_state_names(states_path)
    except (OSError, ValueError) as exc:
        errors.append("{}: {}".format(states_path, exc))
        state_names = {}

    motions_dir = base_dir / "motions"
    # iterdir deliberately scans only direct children, not nested directories.
    paths = sorted(p for p in motions_dir.iterdir()
                   if p.is_file() and p.suffix.lower() == ".json" and p.name != "index.json")
    motions = []
    seen = {}
    for path in paths:
        match = re.match(r"[0-9]+", path.stem)
        if match is None:
            errors.append("{}: filename must begin with a numeric ID".format(path.name))
            continue
        motion_id = match.group()
        numeric_id = int(motion_id)
        if numeric_id in seen:
            errors.append("{}: duplicate ID {} (also {})".format(
                path.name, motion_id, seen[numeric_id]))
        else:
            seen[numeric_id] = path.name
        try:
            motions.append(extract_motion(path, motion_id, state_names))
        except (OSError, ValueError, OverflowError) as exc:
            errors.append("{}: {}".format(path.name, exc))
    if errors:
        raise ValueError("\n".join(errors))
    motions.sort(key=lambda motion: (int(motion["id"]), motion["file"]))
    payload = json.dumps({"format": "robi-motion-index-v1", "motions": motions},
                         ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=motions_dir, prefix=".index-",
                                         suffix=".tmp", delete=False) as target:
            temporary_path = Path(target.name)
            target.write(payload)
        os.replace(temporary_path, motions_dir / "index.json")
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return len(motions)


def main():
    try:
        count = generate_index(Path(__file__).resolve().parent)
    except (OSError, ValueError, OverflowError) as exc:
        print("Motion index generation failed:\n{}".format(exc), file=sys.stderr)
        return 1
    print("Generated motions/index.json: {} motions".format(count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
