#!/usr/bin/env python3
"""Text-only Qwen3 chat for llama.cpp d3bd7193b (Python 3.6+)."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parent
FIELDS = {"speech", "emotion", "action", "motion_id"}
PATH_ENV = {"llama_cli": "ROBI_LLAMA_CLI", "model": "ROBI_MODEL",
            "motion_index": "ROBI_MOTION_INDEX", "personality": "ROBI_PERSONALITY",
            "examples": "ROBI_EXAMPLES"}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def read_json(path):
    return parse_json(path.read_text(encoding="utf-8"))


def load_config(path):
    path = path.resolve()
    config = read_json(path)
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    for key, env in PATH_ENV.items():
        value = os.environ.get(env, config.get(key))
        if not isinstance(value, str) or not value:
            raise ValueError("missing path: " + key)
        value = os.path.expandvars(os.path.expanduser(value))
        if "$" in value:
            raise ValueError("unresolved environment variable in " + key)
        target = Path(value)
        config[key] = (path.parent / target).resolve()
    for key, minimum in (("gpu_layers", 0), ("threads", 1), ("context_length", 64),
                         ("max_tokens", 1), ("history_turns", 0)):
        if type(config.get(key)) is not int or config[key] < minimum:
            raise ValueError("invalid integer setting: " + key)
    for key in ("temperature", "timeout_seconds"):
        value = config.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid number setting: " + key)
    if config["timeout_seconds"] == 0 or config["max_tokens"] + 32 >= config["context_length"]:
        raise ValueError("invalid timeout or context/generation budget")
    blocked = config.get("blocked_motion_ids")
    if not isinstance(blocked, list) or any(not isinstance(x, str) for x in blocked):
        raise ValueError("blocked_motion_ids must be an array of string IDs")
    return config


def validate_response(value, motions, blocked):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("response must contain exactly speech, emotion, action, motion_id")
    for key in ("speech", "emotion", "action"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(key + " must be a nonempty string")
        if any(token in value[key] for token in ("<think>", "</think>", "<|")):
            raise ValueError("unexpected model control/thinking text in " + key)
    motion_id = value["motion_id"]
    if motion_id is not None:
        if not isinstance(motion_id, str) or motion_id not in motions:
            raise ValueError("unknown motion_id: " + repr(motion_id))
        if motion_id in blocked:
            raise ValueError("blocked motion_id: " + motion_id)
    return value


def parse_output(text, motions, blocked):
    # Pinned main.cpp prints this exact trailer at EOG. Never search for JSON.
    text = text.strip()
    trailer = " [end of text]"
    if text.endswith(trailer):
        text = text[:-len(trailer)].rstrip()
    return validate_response(parse_json(text), motions, blocked)


def message(role, text):
    # Prevent external/user text from injecting ChatML role boundaries.
    text = text.replace("<|", "＜|")
    return "<|im_start|>" + role + "\n" + text + "<|im_end|>\n"


class Chat:
    def __init__(self, config):
        self.config = config
        index = read_json(config["motion_index"])
        if not isinstance(index, dict) or index.get("format") != "robi-motion-index-v1":
            raise ValueError("unsupported motion index format")
        rows = index.get("motions")
        if not isinstance(rows, list) or not rows:
            raise ValueError("motion index must contain a nonempty motions array")
        self.motions = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("motion must be an object")
            for key in ("id", "name", "description", "start_state_name", "end_state_name"):
                if key not in row or (not isinstance(row[key], str) and not
                                       (key.endswith("state_name") and row[key] is None)):
                    raise ValueError("invalid motion field: " + key)
            if not row["id"] or row["id"] in self.motions:
                raise ValueError("empty or duplicate motion ID: " + row["id"])
            self.motions[row["id"]] = row
        self.blocked = set(config["blocked_motion_ids"])
        if self.blocked - set(self.motions):
            raise ValueError("blocked_motion_ids contains unknown IDs")
        self.allowed = [row for row in rows if row["id"] not in self.blocked]
        self.personality = config["personality"].read_text(encoding="utf-8").strip()
        if not self.personality:
            raise ValueError("personality is empty")
        examples = read_json(config["examples"])
        if not isinstance(examples, list):
            raise ValueError("examples must be an array")
        self.examples = []
        for example in examples:
            if not isinstance(example, dict) or not isinstance(example.get("user"), str):
                raise ValueError("example must contain user and response")
            # Blocked examples are omitted when restrictions are tightened.
            validate_response(example.get("response"), self.motions, set())
            if example["response"]["motion_id"] not in self.blocked:
                self.examples.append(example)
        self.history = []

    def schema(self):
        return {"type": "object", "properties": {
            "speech": {"type": "string"}, "emotion": {"type": "string"},
            "action": {"type": "string"}, "motion_id": {
                "enum": [m["id"] for m in self.allowed] + [None]}},
            "required": ["speech", "emotion", "action", "motion_id"],
            "additionalProperties": False}

    def build_prompt(self, user):
        if not user.strip():
            raise ValueError("input is empty")
        system = self.personality + "\n" + (
            "今はテキスト試験。動作は実行されない。返答と意味が合う候補だけを選ぶ。"
            "質問への説明や無関係な場面ではmotion_idをnullにする。"
            "状態名は参考情報で現在の姿勢は不明。動作済みと話さない。"
            "出力はspeech(日本語),emotion,action,motion_idのJSONオブジェクト1個だけ。"
            "motion_idは候補の文字列IDかnull。思考・Markdown・前置き不要。/no_think\n"
            "候補の各行は[id,name,description,start_state_name,end_state_name]。nullは不明。\n")
        system += "\n".join(compact([m[k] for k in
            ("id", "name", "description", "start_state_name", "end_state_name")]) for m in self.allowed)
        turns = self.config["history_turns"]
        history = list(self.history[-turns:]) if turns else []
        examples = list(self.examples)
        while True:
            prompt = message("system", system)
            for example in examples:
                prompt += message("user", example["user"])
                prompt += message("assistant", compact(example["response"]))
            for previous_user, response in history:
                prompt += message("user", previous_user)
                prompt += message("assistant", compact(response))
            prompt += message("user", user)
            # Qwen3 non-thinking assistant prefill; grammar begins AFTER this.
            prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n"
            # Qwen3 byte-level BPE: UTF-8 bytes upper-bound text tokens.
            upper = len(prompt.encode("utf-8")) + 32
            if upper + self.config["max_tokens"] <= self.config["context_length"]:
                return prompt, {"prompt_chars": len(prompt), "prompt_token_upper_bound": upper,
                                "history_turns": len(history), "examples": len(examples),
                                "motion_candidates": len(self.allowed)}
            if history:
                history.pop(0)
            elif examples:
                examples.pop()
            else:
                raise ValueError("prompt exceeds context budget; shorten input/settings or increase context_length")

    def environment(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("LLAMA_ARG_", "LLAMA_LOG_"))}
        library_dir = str(self.config["llama_cli"].parent)
        env["LD_LIBRARY_PATH"] = library_dir + (":" + env["LD_LIBRARY_PATH"]
                                                   if env.get("LD_LIBRARY_PATH") else "")
        return env

    def preflight(self):
        exe = self.config["llama_cli"]
        if not exe.is_file() or not os.access(str(exe), os.X_OK):
            raise ValueError("llama-cli missing or not executable: " + str(exe))
        if not self.config["model"].is_file():
            raise ValueError("GGUF model missing: " + str(self.config["model"]))
        result = subprocess.run([str(exe), "--help"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self.environment(), timeout=30)
        help_text = (result.stdout + result.stderr).decode("utf-8", "replace")
        for flag in ("--json-schema", "--no-conversation", "--no-display-prompt",
                     "--simple-io", "--no-escape", "--no-context-shift"):
            if result.returncode != 0 or flag not in help_text:
                raise ValueError("unsupported llama-cli; required option: " + flag)

    def infer(self, user, debug=False):
        metrics = {"json_success": False, "inference_seconds": None, "prompt_chars": None}
        try:
            prompt, sizes = self.build_prompt(user)
            metrics.update(sizes)
            with tempfile.TemporaryDirectory(prefix="robi-llm-") as directory:
                prompt_file = Path(directory) / "prompt.txt"
                prompt_file.write_text(prompt, encoding="utf-8")
                c = self.config
                argv = [str(c["llama_cli"]), "-m", str(c["model"]), "-ngl", str(c["gpu_layers"]),
                        "-t", str(c["threads"]), "-c", str(c["context_length"]),
                        "-n", str(c["max_tokens"]), "--temp", str(c["temperature"]),
                        "--no-conversation", "--no-display-prompt", "--simple-io", "--no-escape",
                        "--no-context-shift", "--json-schema", compact(self.schema()), "-f", str(prompt_file)]
                started = time.monotonic()
                try:
                    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, env=self.environment(),
                                            timeout=c["timeout_seconds"])
                finally:
                    metrics["inference_seconds"] = round(time.monotonic() - started, 3)
                if debug or result.returncode != 0:
                    print("[llama-cli stderr]\n" + result.stderr.decode("utf-8", "replace"), file=sys.stderr)
                if result.returncode != 0:
                    raise ValueError("llama-cli exited with code {}".format(result.returncode))
                response = parse_output(result.stdout.decode("utf-8"), self.motions, self.blocked)
            metrics.update(json_success=True, motion_id=response["motion_id"],
                           motion_name=self.motions[response["motion_id"]]["name"]
                           if response["motion_id"] is not None else None)
            if c["history_turns"]:
                self.history.append((user, response))
                self.history = self.history[-c["history_turns"]:]
            return response
        finally:
            print("[metrics] " + compact(metrics), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("ROBI_LLM_CONFIG", str(BASE / "config.json"))))
    parser.add_argument("--once", help="one text input, then exit")
    parser.add_argument("--debug", action="store_true", help="show llama-cli stderr")
    parser.add_argument("--check-prompt", metavar="TEXT", help="validate assets and report prompt budget without inference")
    args = parser.parse_args()
    try:
        chat = Chat(load_config(args.config))
        if args.check_prompt is not None:
            _, metrics = chat.build_prompt(args.check_prompt)
            print("[prompt-check, no inference] " + compact(metrics), file=sys.stderr)
            return 0
        chat.preflight()
        if args.once is not None:
            print(compact(chat.infer(args.once, args.debug)), flush=True)
            return 0
        while True:
            print("あなた> ", end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline()
            if not line or line.strip() == "/quit":
                return 0
            if not line.strip():
                continue
            try:
                print(compact(chat.infer(line.strip(), args.debug)), flush=True)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                print("[error] " + str(exc), file=sys.stderr)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("[error] " + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[stopped]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
