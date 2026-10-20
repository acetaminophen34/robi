# ロビの常駐LLM対話試験

会話開始時に既存CUDA版`llama-server`を1回だけ子プロセスとして起動し、Qwen3-1.7Bを会話中ずっとメモリに保持します。Python 3.6以降の標準ライブラリのみを使います。音声・ESP32・実機動作への接続はありません。

## ファイルの役割

普段実行するのは **`chat.py`だけ** です。設定を変更したいときは目的に応じて次のファイルを編集します。

| ファイル | 役割・使い方 |
|---|---|
| `chat.py` | 対話プログラムの入口。入力受付、性格・例文・候補の読み込み、プロンプト生成、会話履歴、JSON検証を担当 |
| `server.py` | `chat.py`から使う内部モジュール。llama-serverの起動・終了とHTTP通信を担当。単独では実行しない |
| `config.json` | モデル・サーバーの参照先、GPU・生成量・履歴数・禁止モーションなどの設定 |
| `personality.md` | ロビの口調、性格、返答の長さを指定 |
| `examples.json` | 入力と期待する返答・モーションの対話例 |
| `test_chat.py` | 単体・HTTPモックテストをまとめた開発用プログラム。通常の対話には不要 |
| `README.md` | この使い方・設定の説明 |

モーション一覧は`motion_editor/motions/index.json`を参照します。モデル本体とllama-server実行ファイルの準備・ビルド手順はjetson-labで管理します。

```text
利用者 → chat.py → server.py → llama-server（モデルを保持）
          ↑
          config.json / personality.md / examples.json / モーション索引
```

## 使用環境

| 項目 | 対象 |
|---|---|
| 実機 | Jetson TX2 8GB |
| JetPack / CUDA | 4.6.6 / 10.2 |
| 推論エンジン | CUDAパッチ適用済みllama.cpp build5092（d3bd7193b） |
| モデル | Qwen3-1.7B-Q4_K_M.gguf |
| Python | 3.6以降・標準ライブラリのみ（pip追加不要） |
| 入出力 | 日本語テキスト入力 → speech/emotion/action/motion_idのJSON |

Jetsonの初期設定、コンパイラ、CUDA互換パッチ、モデル配置は[jetson-lab](https://github.com/acetaminophen34/jetson-lab)を参照してください。このリポジトリでは対話、性格・例文、履歴、モーション選択を管理します。

## 起動

環境構築と`llama-server`の導入・追加ビルドは、[jetson-labの手順](https://github.com/acetaminophen34/jetson-lab/blob/main/llama-cpp/server.md)で管理します。準備済みなら、このページの起動手順から使えます。Robi側でCUDA環境やモデルを再構築する必要はありません。

以下は、`~/Projects/`に両リポジトリをcloneし、jetson-labの標準手順で環境を構築した場合の例です。配置が異なる場合は参照先を変更してください。

```bash
cd "$HOME/Projects/robi"
export ROBI_LLAMA_SERVER="$HOME/Projects/jetson-lab/work/llama-cuda/build-gpu/bin/llama-server"
export ROBI_MODEL="$HOME/Projects/jetson-lab/work/models/Qwen3-1.7B-Q4_K_M.gguf"
# 最初に1回だけ応答を確認
python3 jetson/llm/chat.py --once "こんにちは"
# 続けて会話する場合はこちら
python3 jetson/llm/chat.py
```

連続対話は1行ごとに入力します。`/quit`、EOF、Ctrl+Cで終了し、サーバーも停止・回収します。`--once`は1回応答して停止する確認用で、複数回実行するとその都度モデルをロードします。ロードを繰り返さない用途は引数なしの連続対話を使ってください。旧試作の入口`chat_persistent.py`は整理し、起動方法を`chat.py`に統一しました。

応答JSONだけをstdoutに1行ずつ出します。起動案内・入力案内・計測値・短いエラーはstderrです。

```bash
python3 jetson/llm/chat.py --once "こんにちは" > response.json 2> metrics.log
```

詳細なllama.cppログは`jetson/llm/logs/llama-server-*.log`へ実行ごとに保存し、端末に内容を流しません。起動時とエラー時にパスを表示します。HTTPエラー本文や検証に失敗した出力も同ファイルに保存するため、ログには会話内容が含まれ得ます。ファイル権限は0600、Git管理対象外です。不要なログは手動で整理してください。

起動失敗、HTTPエラー、タイムアウト、出力検証エラーは、サーバーを終了して非ゼロ終了します。失敗した発話は履歴に追加しません。再起動や架空の返答で成功扱いにはしません。終了はterminate→設定秒数待機→必要ならkill→waitの順です。`__enter__`途中の失敗も同じ後始末を行います。OSによる強制停止（SIGKILL等）まで回復する常駐サービス管理機能はありません。

## よく使う操作

| やりたいこと | 操作 |
|---|---|
| 会話を続ける | `python3 jetson/llm/chat.py`を起動して1行ずつ入力 |
| 1回だけ確認する | `python3 jetson/llm/chat.py --once "またね"` |
| モデルなしで設定を確認する | `python3 jetson/llm/chat.py --check-prompt "こんにちは"` |
| 口調・返答の長さを変える | `personality.md`を編集して再起動 |
| 応答例を増やす | `examples.json`を編集して再起動 |
| 生成量やばらつきを変える | 設定の`max_tokens`／`temperature`を編集 |
| 終了する | `/quit`、Ctrl+D（EOF）、Ctrl+C |

`[server] ready`が出たら入力できます。初回のモデル読み込みとプロンプト評価には時間がかかります。2発話目以降も同じプログラムを使い続けることで、モデル常駐と共通入力のKV再利用を利用できます。手動で別のllama-serverを起動しておく必要はありません。

## 困ったとき

| 表示・症状 | 確認すること |
|---|---|
| `llama-server missing or not executable` | `ROBI_LLAMA_SERVER`を確認。未ビルドならjetson-labのサーバー手順へ |
| `GGUF model missing` | `ROBI_MODEL`が既存GGUFを指しているか確認 |
| 起動失敗・起動タイムアウト | 表示されたログを確認。ライブラリ、空きメモリ、GPU配置を確認 |
| `generation incomplete` | 詳細ログと`max_tokens`を確認。生成上限で打ち切られていないか確認 |
| `prompt exceeds context budget` | 入力を短くするか、メモリを確認して`context_length`を調整 |
| 旧`prompt-cache.bin`が壊れている | 常駐方式では読み込まないため、キャッシュ作り直しは不要 |

失敗時はプログラムが終了します。原因を修正してから同じ起動コマンドで再実行してください。JSONの`motion_id`は選択結果であり、実機に動作を送ったことを意味しません。

## 設定

`config.json`のファイルパスは設定ファイルのディレクトリ基準です。`~`と環境変数を展開し、未解決の変数はエラーにします。Mac固有のパスはありません。

| 設定 | 既定値／用途 | パス上書き環境変数 |
|---|---|---|
| llama_server | 隣接jetson-labの新規構築例のビルド先 | `ROBI_LLAMA_SERVER` |
| model | Qwen3-1.7B-Q4_K_M.gguf | `ROBI_MODEL` |
| motion_index | 既存のモーション索引 | `ROBI_MOTION_INDEX` |
| personality | personality.md | `ROBI_PERSONALITY` |
| examples | examples.json | `ROBI_EXAMPLES` |
| log_dir | logs/ | `ROBI_LLM_LOG_DIR` |
| gpu_layers / threads | 99 / 4 | — |
| context_length | 8192 | — |
| batch_size / ubatch_size | 128 / 128 | — |
| max_tokens / temperature | 192 / 0.6 | — |
| history_turns | 直近3往復 | — |
| blocked_motion_ids | `["023"]` | — |
| startup_timeout_seconds | 起動待機180秒 | — |
| timeout_seconds | HTTP通信の待機上限600秒 | — |
| shutdown_timeout_seconds | 終了待機5秒 | — |

設定全体は`--config PATH`または`ROBI_LLM_CONFIG`で指定できます。旧`llama_cli`／`ROBI_LLAMA_CLI`は使いません。環境変数で指定した相対パスも設定ファイル基準です。実機専用の設定を作る場合はGit管理対象外の`config.local.json`にコピーして編集できます。

```bash
cp jetson/llm/config.json jetson/llm/config.local.json
python3 jetson/llm/chat.py --config jetson/llm/config.local.json
```

性格・返答の長さは`personality.md`、例文は`examples.json`、生成上限とtemperatureは設定JSONで変更します。ファイルは起動時に読みます。emotion/actionは厳密な固定カテゴリを設けず、非空文字列として検証します。

コンテキスト8192とバッチ128はTX2の共有8GBメモリで使用量・速度の実測が必要です。不要な推論プロセスを止め、`free -h`と`tegrastats`で監視してください。並列スロットは1に固定しています。メモリ不足ならローカル設定でコンテキスト・バッチを下げます。保守的な入力予算を満たせなければ推論前にエラーになります。

## API・履歴・KVキャッシュ

対象はbuild5092（`d3bd7193ba66c15963fd1c59448f22019a8caf6e`）。[固定版の公式API仕様](https://github.com/ggml-org/llama.cpp/blob/d3bd7193ba66c15963fd1c59448f22019a8caf6e/examples/server/README.md)と[実装](https://github.com/ggml-org/llama.cpp/blob/d3bd7193ba66c15963fd1c59448f22019a8caf6e/examples/server/server.cpp)を照合しています。最新APIやOpenAI APIは使いません。

- `127.0.0.1`の空きポートに自分専用の子サーバーを起動し、`/health`が200・status=okになるまで待ちます。起動ごとのAPIキーで`/props`も確認します。HTTPプロキシ設定は使いません。
- `POST /completion`へ完全なChatMLプロンプト、`json_schema`、`cache_prompt:true`、`id_slot:0`、`stream:false`、生成上限とtemperatureを送ります。自動チャットテンプレートを重ねないネイティブcompletionです。
- サーバーの1スロット内のKVを再利用します。プロンプトは性格→モーション候補→Few-shot→直近履歴→今回の入力の順で、共通接頭辞を安定させます。全体は毎回送りますが、共通部分の再評価を省くことをサーバーへ要求します。
- 履歴はPython側で成功した直近の往復だけを保持します。プロンプト予算不足時は古い履歴、次に末尾の例文を除外します。固定部分や今回の入力は切り詰めません。
- モデルとKVはプロセス存続中だけ保持します。`prompt-cache.bin`、`--prompt-cache`、スロット保存・復元APIには依存しません。旧ファイルが壊れていても読み込みません。終了後の次の起動は初回ロード・全入力評価が必要です。

Qwen3向け`/no_think`と空のthinkブロックをassistant末尾に先置きし、その直後からJSON Schemaで生成を制約します。`content`全体を厳密にJSON解析します。CLIの終了装飾除去や正規表現によるJSON抽出はありません。

必須4項目、余分なキー、重複キー、思考・Markdown混入、未知ID・数値ID・禁止IDを検証します。APIの`stop=true`、`stop_type=eos/word`、`truncated=false`も要求し、生成上限による打ち切りは完全なJSONに見えても失敗にします。023は候補・Schema列挙・例文から除外し、返却時にも拒否します。

モーションにはid/name/description/start_state_name/end_state_nameだけを使います。元の名前・説明は維持し、角度・フレームは送りません。開始・終了状態名は参考情報で、現在姿勢は把握しません。意味の合わない場面ではnullにするよう指示しますが、選択の意味的な適切さは実モデルで評価が必要です。

`[metrics]`には次を記録します。

- JSON検証の成否、HTTP推論時間、選択IDと名称。
- プロンプト文字数、UTF-8バイト数＋32による保守的トークン上限、実際に提示した履歴・例文・候補件数。
- サーバーの`timings`、`tokens_evaluated`、`tokens_cached`。

HTTP時間に初回モデル起動は含めず、起動時間は別の`[server] ready`で表示します。`timings.prompt_n`は今回処理した入力トークン数です。この版の`tokens_cached`は完了時の`n_past`なので、今回のキャッシュヒット数と同一視しません。初回／次回の`prompt_n`、時間、詳細ログを比較してください。履歴をずらすと固定部分以降の再評価が増えます。

プロンプト予算は実際のtokenizer測定ではなく、Qwen3 byte-level BPEを前提にした保守的上限です。入力上限＋生成上限が設定コンテキスト内に収まるよう管理し、`--no-context-shift`で暗黙の切り詰めを防ぎます。

```bash
# モデルを起動せず、設定・索引・例文とプロンプト予算だけを確認
python3 jetson/llm/chat.py --check-prompt "こんにちは"
```

文字数・例文件数は設定ファイルの編集によって変化します。現在の値は上の`--check-prompt`で確認できます。保守的なトークン上限は、実機で報告された実トークン数とは指標が異なります。

## GitHub経由のデプロイ

GitHubに反映済みの変更をTX2へ取り込む手順です。ローカルだけのコミットは、pushされるまでTX2のpullには反映されません。TX2の既存ローカル変更がある場合はpullを止めて差分を確認します。ソースやモデルの再clone／再取得は不要です。

```bash
cd "$HOME/Projects/jetson-lab"
git status --short
git pull --ff-only origin main
# llama-cpp/server.mdに従い、既存build-gpuへllama-serverのみ追加ビルド

cd "$HOME/Projects/robi"
git status --short
git pull --ff-only origin main
export ROBI_LLAMA_SERVER="$HOME/Projects/jetson-lab/work/llama-cuda/build-gpu/bin/llama-server"
export ROBI_MODEL="$HOME/Projects/jetson-lab/work/models/Qwen3-1.7B-Q4_K_M.gguf"
python3 -m unittest discover -s jetson/llm -p 'test_*.py' -v
python3 jetson/llm/chat.py --once "こんにちは"
python3 jetson/llm/chat.py
```

pull前に`git status --short`が空であることを確認してください。サーバー追加ビルドの正確なコマンドは上記jetson-lab文書にあります。

## MacからSSH/SCPで今回の差分を試す

push前にも試せるよう、TX2のGit作業ツリーを上書きしない転送先を用意します。Mac側で`TX2_HOST`を到達可能なIPまたはSSHホスト名に変更し、robiのルートで実行します。既存のSSH認証を使います。

```bash
export TX2_HOST="ユーザー名@Jetsonのホスト名またはIP"   # 実際の接続先に変更
export TX2_STAGE="robi-llm-preview"   # 接続先ホームからの相対パス
ssh "$TX2_HOST" "mkdir -p '$TX2_STAGE/jetson' '$TX2_STAGE/motion_editor' '$TX2_STAGE/docs'"
scp -r jetson/llm "$TX2_HOST:$TX2_STAGE/jetson/"
scp motion_editor/motions/index.json "$TX2_HOST:$TX2_STAGE/motion_editor/index.json"
scp ../jetson-lab/llama-cpp/server.md "$TX2_HOST:$TX2_STAGE/docs/jetson-server.md"
ssh -t "$TX2_HOST"
```

TX2に入った後、次を実行します。

```bash
cat "$HOME/robi-llm-preview/docs/jetson-server.md"
# 上の文書に従って既存CUDA環境へllama-serverを追加ビルドする
cd "$HOME/robi-llm-preview"
export ROBI_LLAMA_SERVER="$HOME/Projects/jetson-lab/work/llama-cuda/build-gpu/bin/llama-server"
export ROBI_MODEL="$HOME/Projects/jetson-lab/work/models/Qwen3-1.7B-Q4_K_M.gguf"
export ROBI_MOTION_INDEX="$HOME/robi-llm-preview/motion_editor/index.json"
python3 jetson/llm/chat.py --once "こんにちは"
python3 jetson/llm/chat.py
```

SCPで転送したコード・設定の変更は、このプレビュー先でのみ反映されます。`llm/`内にローカルログ等がある場合は転送前に確認してください。モデルやキャッシュを転送する必要はありません。

## 検証状況

```bash
python3 -m unittest discover -s jetson/llm -p 'test_*.py' -v
```

単体テストと実際のlocalhost HTTPを使う一時子プロセスのモックテストがあります。連続発話で起動1回、KV再利用指定、Schema・禁止023・未知ID・必須フィールド、履歴、起動失敗、API異常、打ち切り、タイムアウト、Ctrl+C・EOF・/quit、終了待機後kill、ログ分離を検証します。モック応答を実推論の成功として扱いません。

Python 3.6互換構文と標準ライブラリAPIで実装しています。開発Macで構文・テストを確認しましたが、Python 3.6実行環境・Jetson実機への接続はありません。TX2でのサーバー追加ビルド、実モデルによるHTTP推論、29層オフロード、メモリ使用量、初回と再利用時の速度、日本語品質・履歴理解・意味に合うモーション選択は未確認です。既報のCLIでの約56.7秒／完全一致キャッシュ約9.8秒は今回の常駐方式の実測値ではありません。
