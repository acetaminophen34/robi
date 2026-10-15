# ロビの日本語意味分類

ターミナルの日本語テキストを文章埋め込みで分類する試作です。音声認識・発話・サーボ制御は実行しません。

## セットアップ（Mac）

Python 3.10 以上を使用します。Apple Silicon では arm64 版 Python を推奨します。CPU を明示しているため、MPS / CUDA は不要です。

```sh
cd /Users/utsukaryounin/Projects/robi/jetson/classification
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python classify.py
```

初回はインターネット接続が必要です。モデルは Hugging Face の通常のキャッシュにダウンロードされます。モデルファイルが揃った後は `HF_HUB_OFFLINE=1 python classify.py` でオフライン実行できます。初回起動はダウンロードに時間がかかります。

```text
入力> ダンスして
判定: dance_request / 類似度: ... / action: dance / motion_id: None
例文の類似度上位5件:
  ...
入力> exit
```

空行は無視し、`exit`、Ctrl+C、Ctrl+D で終了します。1文だけの実行や閾値の調整もできます。

```sh
python classify.py --text '自己紹介して'
python classify.py --threshold 0.65
python classify.py --intents ./intents.json
```

## モデルの選択

起動時に `--model` で選択できます。省略すると既存の `intents.json` のモデルを使用します。短縮名の代わりに正式なモデル名も指定できます。

| 短縮名 | モデル |
| --- | --- |
| `minilm` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `mpnet` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` |
| `e5` | `intfloat/multilingual-e5-small` |

```sh
python classify.py --model minilm
python classify.py --model mpnet
python classify.py --model e5 --threshold 0.85
```

通常入力・`batch`・`--text`・`--texts`・`--file` のすべてで選択したモデルを使用します。表示と結果辞書の `model` に正式名を含めるため、同じ文を別モデルで実行して類似度を確認できます。

```sh
python classify.py --model minilm --texts 'ロビのダンスが見たいな' '電車の時刻表を調べて'
python classify.py --model mpnet --texts 'ロビのダンスが見たいな' '電車の時刻表を調べて'
python classify.py --model e5 --texts 'ロビのダンスが見たいな' '電車の時刻表を調べて'
```

E5 は [公式モデルカード](https://huggingface.co/intfloat/multilingual-e5-small) の対称な類似度比較の指示に合わせ、入力文と登録例文の両方に `query: ` を付けて埋め込みを計算します。表示する原文と `intents.json` は変更しません。モデル側の既定プロンプトは無効にして、プレフィックスの二重適用を防ぎます。

モデルごとにスコアの分布が異なり、特に E5 は対象外の文でも高い類似度になりやすいため、閾値はモデルごとに調整してください。上記の `0.85` は実行例で、推奨値ではありません。初回は選択したモデルのダウンロードが必要です。MPNet は MiniLM より大きく、CPUでの起動・推論に時間やメモリを使います。

## まとめ入力

対話中に `batch` と入力すると、複数行をまとめて入力・貼り付けできます。1行を1文として扱い、最後に空行（Enter）を入れると各文を分類します。その後は通常の対話に戻ります。

```text
入力> batch
まとめ> こんにちは
まとめ> ダンスして
まとめ> 電車の時刻表を調べて
まとめ>
```

コマンド引数や UTF-8 テキストファイルからも実行できます。ファイルは1行1文で、空行は無視します。結果は入力順の JSON 配列です。

```sh
python classify.py --texts 'こんにちは' 'ダンスして' '電車の時刻表を調べて'
python classify.py --file inputs.txt
```

Python では `classifier.classify_many(["こんにちは", "ダンスして"])` が辞書のリストを返します。入力文は最大32文ずつ埋め込みを計算し、モデルと例文のキャッシュは再利用します。文中の句読点による自動分割は行いません。まとめ入力中の `exit` は分類対象の文で、終了する場合は通常の `入力>` に戻ってから入力してください。

## 分類方法と設定

[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) は日本語を含む多言語用の 384 次元文章埋め込みモデルです。大規模モデルより小さい MiniLM を使用していますが、モデルのダウンロードや PyTorch のメモリ消費はあります。

`intents.json` の `intents` にカテゴリを追加できます。各カテゴリには `examples`（空でない例文の配列）、`action`（文字列）、`motion_id`（整数・文字列・null）を設定します。`description` は説明用です。編集後はプログラムを再起動してください。モーション番号は実機の定義が未確定なので初期値を `null` にしています。

各例文とのコサイン類似度を計算し、最高スコアの例文が属するカテゴリを選びます。カテゴリの平均は使いません。上位5件は **例文単位** なので同じカテゴリが複数回表示されます。モデルは起動時に1回読み込み、例文の正規化済み埋め込みをメモリにキャッシュします。入力ごとの再計算は入力文だけです。埋め込みのディスクキャッシュは行いません。

最高スコアが `threshold` 未満なら `unknown` にします。`unknown.examples` は参考文であり、比較対象から除外します。初期閾値 `0.55` は仮の値です。スコアは -1〜1 の類似度で、確率や正答率ではありません。実際の入力を集め、既知カテゴリの言い換えと対象外の文の両方で閾値を調整してください。閾値だけでは否定文（「踊らないで」）や複数の要求を確実に扱えないため、現段階では動作指令への直接接続を想定していません。

`self_introduction` はロビへの自己紹介要求、`encouragement` はロビへの励ましとして定義しています。用途に応じて例文を編集してください。

## Python から使う

```python
from classify import IntentClassifier

classifier = IntentClassifier()  # 起動時に1回だけ生成
result = classifier.classify("踊ってくれる？")
print(result["intent"], result["action"], result["motion_id"])
```

結果は `text`、`model`、`intent`、`score`、`threshold`、`action`、`motion_id`、`top_matches` を持つ辞書です。`unknown` の場合も `score` は比較対象での最高類似度です。別の制御モジュールが結果を受け取り、発話やモーションを実行する設計にしてください。

## Jetson Nano への移植

この依存指定は Mac の試作用です。Jetson Nano 4GB では JetPack、Python、ARM64 対応 PyTorch の互換性とメモリ使用量を別途確認する必要があります。そのままのインストールは保証しません。将来 ONNX に移行するときも、同じトークナイザー、平均プーリング、正規化を再現し、分類結果を比較してください。現段階では学習・ファインチューニング・ONNX 変換は行いません。

API 参考: [SentenceTransformer / encode](https://sbert.net/docs/package_reference/sentence_transformer/model.html)。
