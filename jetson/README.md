# Jetson TX2

## 起動

```bash
cd ~/robi && python3 jetson/llm/robi_chat_motion.py
```

しゃがみ・トルクOFFのRobiを支え、確認に `y` を入力する。001「立ち上がり」後に対話開始。`exit` で002「しゃがみ」を実行して終了する。Ctrl+Cや動作エラー時は機体を支える。

## 参照先

| 対象 | パス |
|---|---|
| 設定 | `~/robi/jetson/llm/config.json` |
| CUDAサーバー | `~/jetson-work/llama-tx2/build-gpu/bin/llama-server` |
| モデル | `~/jetson-work/models/Qwen3-1.7B-Q4_K_M.gguf` |
| モーション | `~/robi/motion_editor/motions/` |
| ログ | `~/robi/jetson/llm/logs/` |
| ESP32 | `/dev/ttyACM0`、115200 baud |

Python 3.6とpyserialを使用。通常ユーザーで起動する。
設定の切替は `--config PATH`、ポートの変更は `--port PATH`。
サーボを動かさず試す場合は `--dry-run`、通信確認だけなら `--ping` を付ける。
