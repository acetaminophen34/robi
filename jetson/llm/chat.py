#!/usr/bin/env python3
"""Persistent text-only Qwen3 chat for llama.cpp build5092 (Python 3.6+)."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
FIELDS = {"speech", "emotion", "action", "motion_id"}
PATH_ENV = {"llama_server": "ROBI_LLAMA_SERVER", "log_dir": "ROBI_LLM_LOG_DIR",
            "model": "ROBI_MODEL",
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
    config.setdefault("history_reserve_tokens", 2048)
    config.setdefault("warmup", True)
    if type(config["warmup"]) is not bool:
        raise ValueError("warmup must be a boolean")
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
                         ("max_tokens", 1), ("history_turns", 0), ("history_reserve_tokens", 0),
                         ("batch_size", 1), ("ubatch_size", 1)):
        if type(config.get(key)) is not int or config[key] < minimum:
            raise ValueError("invalid integer setting: " + key)
    for key in ("temperature", "timeout_seconds", "startup_timeout_seconds", "shutdown_timeout_seconds"):
        value = config.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid number setting: " + key)
    if (any(config[k] == 0 for k in ("timeout_seconds", "startup_timeout_seconds", "shutdown_timeout_seconds"))
            or config["max_tokens"] + 32 >= config["context_length"]
            or config["ubatch_size"] > config["batch_size"]):
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
            "動作の依頼がなくても、返答の気持ちや会話の役割に合う動作を積極的に選ぶ。"
            "うん・うんうんは相づちや共感、オッケーは了承、ウキウキは楽しい雑談、えっへんは得意な返答にも使える。"
            "説明でも自然な身振りを添えてよい。動かない指定や、合う動作がない場合はmotion_idをnullにする。"
            "特定の動作だけを断られた場合は、その動作を避けて相づちなどを選んでよい。"
            "動作名への言及だけでその動作を選ばず、返答全体に合わせる。"
            "状態名は参考情報で現在の姿勢は不明。動作済みと話さない。"
            "出力はspeech(日本語),emotion,action,motion_idのJSONオブジェクト1個だけ。"
            "motion_idは候補の文字列IDかnull。思考・Markdown・前置き不要。/no_think\n"
            "候補の各行は[id,name,description,start_state_name,end_state_name]。nullは不明。\n")
        system += "\n".join(compact([m[k] for k in
            ("id", "name", "description", "start_state_name", "end_state_name")]) for m in self.allowed)
        turns = self.config["history_turns"]
        history = list(self.history[-turns:]) if turns else []
        examples = list(self.examples)
        def render(selected_examples, selected_history, current_user):
            prompt = message("system", system)
            for example in selected_examples:
                prompt += message("user", example["user"])
                prompt += message("assistant", compact(example["response"]))
            for previous_user, response in selected_history:
                prompt += message("user", previous_user)
                prompt += message("assistant", compact(response))
            prompt += message("user", current_user)
            # Qwen3 non-thinking assistant prefill; grammar begins AFTER this.
            prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n"
            return prompt

        # Keep a stable example prefix and leave space for user input/history.
        # Reserve uses the same conservative UTF-8 byte bound as the prompt.
        reserve = self.config["history_reserve_tokens"]
        while examples and (len(render(examples, [], "").encode("utf-8")) + 32
                            + reserve + self.config["max_tokens"] > self.config["context_length"]):
            examples.pop()
        while True:
            prompt = render(examples, history, user)
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

    def remember(self, user, response):
        turns = self.config["history_turns"]
        if turns:
            self.history.append((user, response))
            self.history = self.history[-turns:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("ROBI_LLM_CONFIG", str(BASE / "config.json"))))
    parser.add_argument("--once", help="one text input, then exit")
    parser.add_argument("--check-prompt", metavar="TEXT", help="validate assets and report prompt budget without inference")
    args = parser.parse_args()
    try:
        chat = Chat(load_config(args.config))
        if args.check_prompt is not None:
            _, metrics = chat.build_prompt(args.check_prompt)
            print("[prompt-check, no inference] " + compact(metrics), file=sys.stderr)
            return 0
        from server import Server
        with Server(chat) as server:
            if args.once is not None:
                print(compact(server.infer(args.once)), flush=True)
                return 0
            while True:
                print("あなた> ", end="", file=sys.stderr, flush=True)
                line = sys.stdin.readline()
                if not line or line.strip() == "/quit":
                    return 0
                if line.strip():
                    print(compact(server.infer(line.strip())), flush=True)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("[error] " + str(exc).replace("\n", " ")[:300], file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[stopped]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
