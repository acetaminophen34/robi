"""Japanese intent classification. No speech or robot hardware side effects."""

import argparse
import json
import math
from pathlib import Path
import sys

DEFAULT_INTENTS = Path(__file__).with_name("intents.json")
MODELS = {
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "mpnet": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "e5": "intfloat/multilingual-e5-small",
}


class IntentClassifier:
    """Load once and keep normalized example embeddings in memory."""

    def __init__(self, intents_path=DEFAULT_INTENTS, threshold=None, model_name=None):
        with Path(intents_path).open(encoding="utf-8") as stream:
            config = json.load(stream)
        self.threshold = config.get("threshold", 0.55) if threshold is None else threshold
        if (isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float))
                or not math.isfinite(self.threshold) or not -1 <= self.threshold <= 1):
            raise ValueError("threshold は -1〜1 の有限数にしてください")
        self.intents = config.get("intents")
        if not isinstance(self.intents, dict) or "unknown" not in self.intents:
            raise ValueError("intents に unknown カテゴリが必要です")
        self.examples = []
        for name, intent in self.intents.items():
            if not isinstance(intent, dict):
                raise ValueError(f"{name}: カテゴリの定義はオブジェクトにしてください")
            if not isinstance(intent.get("action"), str):
                raise ValueError(f"{name}: action は文字列にしてください")
            motion = intent.get("motion_id")
            if motion is not None and (isinstance(motion, bool) or not isinstance(motion, (int, str))):
                raise ValueError(f"{name}: motion_id は整数・文字列・null にしてください")
            examples = intent.get("examples")
            if (not isinstance(examples, list) or not examples
                    or any(not isinstance(item, str) or not item.strip() for item in examples)):
                raise ValueError(f"{name}: examples に空でない例文を登録してください")
            if name != "unknown":
                self.examples.extend((name, example) for example in examples)
        if not self.examples:
            raise ValueError("unknown 以外のカテゴリが必要です")
        self.model_name = model_name or config.get("model")
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model にモデル名を設定してください")
        self.model_name = MODELS.get(self.model_name, self.model_name)
        self.prefix = "query: " if self.model_name == MODELS["e5"] else ""
        # Lazy import lets --help and config validation work without ML dependencies.
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self.np = np
        self.model = SentenceTransformer(self.model_name, device="cpu")
        self.embeddings = self.model.encode(
            [self.prefix + example for _, example in self.examples],
            prompt="",
            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
        )

    def classify(self, text):
        """Return JSON-compatible data; category score is its best example score."""
        return self.classify_many([text])[0]

    def classify_many(self, texts):
        """Batch-encode texts and return result dictionaries in input order."""
        texts = list(texts)
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("空でない日本語テキストを入力してください")
        texts = [text.strip() for text in texts]
        if not texts:
            return []
        embeddings = self.model.encode(
            [self.prefix + text for text in texts], prompt="",
            batch_size=32, normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [self._result(text, embedding) for text, embedding in zip(texts, embeddings)]

    def _result(self, text, embedding):
        # Dot product of unit vectors equals cosine similarity.
        scores = self.np.clip(
            self.np.einsum("ij,j->i", self.embeddings, embedding), -1.0, 1.0,
        )
        if not self.np.isfinite(scores).all():
            raise ValueError("類似度に非有限値が含まれています")
        order = self.np.argsort(-scores, kind="stable")
        matches = [
            {"intent": self.examples[int(i)][0],
             "example": self.examples[int(i)][1], "score": float(scores[i])}
            for i in order[:5]
        ]
        best = matches[0]
        name = best["intent"] if best["score"] >= self.threshold else "unknown"
        intent = self.intents[name]
        return {
            "text": text, "model": self.model_name, "intent": name, "score": best["score"],
            "threshold": self.threshold, "action": intent["action"],
            "motion_id": intent.get("motion_id"), "top_matches": matches,
        }


def print_result(result):
    print(f"モデル: {result['model']}")
    print(f"入力文: {result['text']}")
    print(f"判定: {result['intent']} / 類似度: {result['score']:.4f} "
          f"/ action: {result['action']} / motion_id: {result['motion_id']}")
    print("例文の類似度上位5件:")
    for match in result["top_matches"]:
        print(f"  {match['score']:.4f}  {match['intent']}: {match['example']}")


def main():
    parser = argparse.ArgumentParser(description="ロビの日本語意味分類（CPU）")
    parser.add_argument("--intents", type=Path, default=DEFAULT_INTENTS)
    parser.add_argument("--threshold", type=float, help="JSON の閾値を上書き")
    parser.add_argument("--model", help="minilm / mpnet / e5 またはモデルの正式名（JSON を上書き）")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--text", help="1文だけ分類して JSON を出力")
    inputs.add_argument("--texts", nargs="+", help="複数文を分類して JSON 配列を出力")
    inputs.add_argument("--file", type=Path, help="UTF-8 ファイルを1行1文として分類")
    args = parser.parse_args()
    try:
        print("モデルと例文を読み込み中…", file=sys.stderr)
        classifier = IntentClassifier(args.intents, args.threshold, args.model)
        print(f"使用モデル: {classifier.model_name} / 閾値: {classifier.threshold}", file=sys.stderr)
        if args.text is not None:
            print(json.dumps(classifier.classify(args.text), ensure_ascii=False, indent=2))
            return 0
        if args.texts is not None or args.file is not None:
            texts = args.texts
            if args.file is not None:
                texts = [line.strip() for line in args.file.read_text(encoding="utf-8-sig").splitlines()
                         if line.strip()]
            print(json.dumps(classifier.classify_many(texts), ensure_ascii=False, indent=2))
            return 0
        print("日本語を入力してください。batch でまとめ入力、exit で終了。スコアは確率ではありません。")
        while True:
            try:
                text = input("入力> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.lower() == "exit":
                break
            if not text:
                continue
            if text.lower() == "batch":
                print("1行に1文ずつ入力・貼り付けしてください。空行で分類します。")
                texts = []
                try:
                    while True:
                        line = input("まとめ> ").strip()
                        if not line:
                            break
                        texts.append(line)
                except (EOFError, KeyboardInterrupt):
                    print("\nまとめ入力を中止しました。")
                    break
                for result in classifier.classify_many(texts):
                    print_result(result)
            else:
                print_result(classifier.classify(text))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
