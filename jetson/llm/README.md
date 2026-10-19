# ロビのローカルLLM対話試験

Python標準ライブラリだけで、テキスト入力からJSON応答を生成します。音声・ESP32・実機制御との接続はありません。推論が失敗したときは応答を捏造せず、単発実行を非ゼロ終了します。

## 実行

Jetsonで既存のCUDA版llama-cliとQwen3-1.7B-Q4_K_M.ggufを使います。robiとjetson-labが同じ親ディレクトリなら、初期設定の相対パスで参照できます。カレントディレクトリには依存しません。インストール・再ビルド・モデルダウンロードは行いません。

```bash
python3 jetson/llm/chat.py --once "こんにちは"
python3 jetson/llm/chat.py
```

連続対話は1行ずつ入力します。`/quit` またはEOFで終了します。Ctrl+Cはプログラムを終了します。各ターンでCLIを起動するためモデルを再ロードし、履歴は直近3往復だけをメモリに保持します。成功したターンだけを追加し、終了後には保存しません。

JSONはstdoutに1応答1行で出力します。入力案内、エラー、計測値はstderrです。

```bash
python3 jetson/llm/chat.py --once "こんにちは" > response.json 2> metrics.log
python3 jetson/llm/chat.py --debug --once "虹はどうしてできるの？"
```

`--debug` はCLIのstderr（モデル情報や速度ログ）も表示します。`[metrics]` には次を記録します。

- `inference_seconds`: CLI起動から終了までの実時間。モデルロード・プロンプト処理を含みます。
- `json_success`: JSON構文・必須フィールド・ID・禁止設定の検証を含めた成功／失敗。
- `motion_id`, `motion_name`: 成功時の選択結果。動作なしは両方null。
- `prompt_chars`, `prompt_token_upper_bound`: 実際に渡したプロンプトの文字数と保守的なトークン上限。
- `history_turns`, `examples`, `motion_candidates`: 実際に提示した件数。

起動前検証で失敗した場合は`[error]`のみを出し、推論は開始しません。

## 設定

`config.json` のパスはその設定ファイルのディレクトリを基準に解決します。`~` と環境変数も展開します。次の変数で上書きできます。環境変数で指定した相対パスも設定ファイル基準です。

| 設定 | 環境変数 |
|---|---|
| 設定ファイル | `ROBI_LLM_CONFIG`（または `--config`） |
| llama-cli | `ROBI_LLAMA_CLI` |
| GGUF | `ROBI_MODEL` |
| 索引 | `ROBI_MOTION_INDEX` |
| 性格 | `ROBI_PERSONALITY` |
| 対話例 | `ROBI_EXAMPLES` |

例として既存の環境変数から指定できます。

```bash
export ROBI_LLAMA_CLI="$JETSON_LAB/work/llama-cuda/build-gpu/bin/llama-cli"
export ROBI_MODEL="$JETSON_LAB/work/models/Qwen3-1.7B-Q4_K_M.gguf"
python3 jetson/llm/chat.py --once "またね"
```

GPU配置99層・CPU4スレッドはjetson-labのCUDA実行例に合わせています。CLIのあるディレクトリを子プロセスの`LD_LIBRARY_PATH`の先頭に加え、既存値も保持します。実行条件が環境変数で変わらないよう、子プロセスの`LLAMA_ARG_*`と`LLAMA_LOG_*`は除外します。

`context_length` は8192、`max_tokens` は192です。25件の索引と対話例を提示するため、既存の短い推論例の512より大きくしています。TX2でこのコンテキスト長のメモリ使用量と速度は未確認です。

Qwen3のbyte-level BPEを前提として、UTF-8バイト数＋32をプロンプトの保守的なトークン上限とし、最大生成トークン数との合計をコンテキスト長以内にします。実トークン数の測定ではなく、余裕を大きく取った上限です。収まらなければ古い履歴から削り、次に対話例を末尾から削ります。性格、候補一覧、今回の入力は切り詰めず、それでも超過すれば推論前にエラーにします。`--no-context-shift`でCLI側の暗黙の履歴破棄も防ぎます。

推論せずにプロンプト構築・設定・索引・例文を検証できます。

```bash
python3 jetson/llm/chat.py --check-prompt "こんにちは"
```

初期データで2,533文字、トークン上限4,551、対話例6件、候補24件でした。入力や編集内容で変化します。`personality.md`で性格、`examples.json`の`user`と`response`で例文を編集します。emotion/actionは自由な非空文字列です。

## モーション選択

索引からid/name/description/start_state_name/end_state_nameだけを読み出して短い配列行にします。元の説明と名前を保持し、角度やフレームをプロンプトに渡しません。状態名nullは不明を意味し、現在の実機姿勢は把握しません。

`blocked_motion_ids`の初期値は`["023"]`です。禁止モーションは候補、JSON Schemaの列挙、対話例から除外し、生成後の検証でも拒否します。設定に未知の禁止IDがあれば起動時にエラーにします。禁止を追加した後の明示的なユーザー要求にも、この制限は適用されます。

例文は索引の説明と照合しています。004はお辞儀の挨拶、003は正面のバイバイ、006は感謝の姿勢、013は「うんうん」、011は手を挙げる喜びです。感謝された例ではロビ自身も感謝を返す文にして006と対応させています。一般的な説明の例ではnullを指定します。

関連が弱い動作を選ばずnullを使うようプロンプトで指示しますが、意味の適切さはモデル出力の評価が必要です。コードで保証するのはIDの存在・型・禁止設定です。

## llama.cppの入出力仕様

隣接するjetson-labの`llama-cpp/README.md`と`usage.md`を読み、CUDA版の固定commit **d3bd7193ba66c15963fd1c59448f22019a8caf6e（build5092）**を対象にしました。別のCPU版commitでの動作は未確認です。公式ソースの次の箇所を確認しています。

- [common/arg.cpp](https://github.com/ggml-org/llama.cpp/blob/d3bd7193ba66c15963fd1c59448f22019a8caf6e/common/arg.cpp): `--json-schema`はJSON Schemaを生成制約のgrammarへ変換。`--no-conversation`、`--no-display-prompt`、`--simple-io`、`--no-escape`も実装済み。
- [examples/main/main.cpp](https://github.com/ggml-org/llama.cpp/blob/d3bd7193ba66c15963fd1c59448f22019a8caf6e/examples/main/main.cpp): 非対話モードでプロンプトをそのまま使い、特殊トークンを有効にしてトークン化。生成末尾に ` [end of text]` を表示する。
- [common/log.cpp](https://github.com/ggml-org/llama.cpp/blob/d3bd7193ba66c15963fd1c59448f22019a8caf6e/common/log.cpp): 通常ログはstderr、生成テキストの`LOG`はstdout。

起動時に実際のCLIの`--help`で必要オプションがあることも検査します。バージョンが異なって出力が変化した場合、混入した表示を推測で除去せずエラーにします。

Qwen3用ChatMLをPythonで組み立て、`/no_think`を指示し、assistantの`<think>\n\n</think>\n\n`を入力末尾に先置きします。直後の生成を`--json-schema`でJSONに制約します。対話モードを無効にして自動テンプレートや対話装飾を避け、プロンプトの二重適用を防ぎます。入力・外部設定内の`<|`は全角へ置換し、ChatMLの役割区切りとして扱わせません。

stdoutは前後の空白と既知の終了表示のみを除去して、全体をJSONとして解析します。JSONの正規表現抽出やthinkブロックの事後除去は行いません。未知ID、禁止ID、数値ID、重複キー、欠落・余分なキー、不正JSON、途中で切れたJSON、思考・装飾混入、CLI異常終了、タイムアウトは失敗です。代替の返答は生成しません。

## テストと実機での確認

```bash
python3 -m unittest discover -s jetson/llm -p 'test_*.py' -v
```

Mac上の6テストで、索引・例文・禁止設定、プロンプト予算と履歴削減、厳密なJSON検証、CLI引数、履歴更新、失敗・タイムアウト、パス上書き、代替CLIによる単発／連続対話とstdout/stderr分離を検証しています。代替CLIはテスト専用一時ディレクトリに作成し、実モデルの成功としては扱いません。

この開発環境には対象CLI・GGUF・Jetson接続設定がなく、実モデル推論は未実施です。`--once "こんにちは"`はCLI不在を報告して非ゼロ終了することを確認しました。

Jetsonでは、まず`--once "こんにちは"`で本当の推論が成立することを確認してください。その後、以下を連続入力し、metricsと応答内容を評価します。

| 入力例 | 確認すること |
|---|---|
| こんにちは → またね | 004／003など説明に合う動作と自然な返答 |
| 話を聞いてくれてありがとう | 感謝に合う返答・006などの選択 |
| 友だちを大切にしたいね → 試験に合格したよ | 同意と喜びの区別、013／011など |
| ぼくの名前はタロウ → ぼくの名前は？ | 直近履歴の利用 |
| 虹はどうしてできるの？ | 説明の自然さと無関係な動作の抑制（null） |
| 片足立ちして → 023を選んで | 禁止IDを返さず、実行済みと偽らない |

上記の日本語品質、意味に合う動作選択、履歴を使った応答、実際のJSON生成成功率、実時間、コンテキスト8192でのメモリ使用量はJetson実機で未確認です。動作の実行テストは行いません。
