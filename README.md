# Robi Development Project

ロボット「ロビ」の制御システムを開発・実験するためのプロジェクトです。

ESP32を用いたサーボモーター制御、Pythonによる操作GUI・モーション編集、Jetsonを用いた認識処理、制御基板の設計などを扱います。

## 使い方を探す

| やりたいこと | 案内 |
|---|---|
| ロビと対話し、モーションを実行する | [Jetson実機環境・起動方法](jetson/README.md) |
| ロビとテキストで会話する | [LLM対話の環境・起動方法](jetson/llm/README.md#起動) |
| どのプログラムを使うか確認する | [LLMファイルの役割](jetson/llm/README.md#ファイルの役割) |
| 口調・返答・モーション選択を調整する | [LLM対話の設定](jetson/llm/README.md#設定) |
| 起動や推論のエラーを調べる | [困ったとき](jetson/llm/README.md#困ったとき) |
| Jetsonへコードを反映する | [GitHub経由](jetson/llm/README.md#github経由のデプロイ)・[SSH/SCP経由](jetson/llm/README.md#macからsshscpで今回の差分を試す) |
| モーションを編集・再生する | [モーションエディタの使い方](motion_editor/README.md) |
| JetsonからUSB経由でRobiに接続する | [ESP32とのシリアル接続メモ](jetson/serial_connection.md) |
| Jetsonの推論環境を準備する | [jetson-labの環境構築](https://github.com/acetaminophen34/jetson-lab)・[llama-serverの追加ビルド](https://github.com/acetaminophen34/jetson-lab/blob/main/llama-cpp/server.md) |

Jetsonでの対話＋モーション制御は[実機環境・起動方法](jetson/README.md)を参照してください。テキスト対話のみの場合は`jetson/llm/chat.py`から起動します。サーバーの導入・ビルドはjetson-lab、対話の使い方・設定はこのリポジトリで管理しています。

## ディレクトリ構成

| ディレクトリ | 内容 |
|---|---|
| `esp/` | ESP32向けプログラムおよびPython GUI |
| `esp/gui_motion/` | モーション編集・制御の試作とテスト |
| `esp/head/` | 頭部のサーボ・LEDなどの制御 |
| `esp/servo/` | サーボモーターの動作確認 |
| `motion_editor/` | モーション作成・編集・再生用のPythonツール |
| `jetson/llm/` | Qwen3常駐サーバーによるテキスト対話・モーション選択（[手順](jetson/llm/README.md)） |
| `jetson/classification/` | Jetson向けの分類処理 |
| `robi_PCB/` | KiCadによる制御基板の設計データ |

## 開発環境

使用する技術・ツール：

- Python
- Arduino / ESP32
- NVIDIA Jetson
- KiCad
- Visual Studio Code

Pythonプログラムの依存パッケージは、各ディレクトリの`requirements.txt`を参照してください。

## モーションデータ

モーションはJSON形式で管理しています。

`motion_editor/motions/`にモーションデータを配置し、編集・再生ツールから利用します。

データ形式や操作方法の詳細は、各ツールのREADMEを参照してください。

## Git管理について

本リポジトリでは、開発用のソースコード・設定ファイル・基板設計データを管理します。

仮想環境、ビルド生成物、一時ファイル、KiCadの自動バックアップなどは原則として管理対象外です。

また、一部の既存ソフトウェア・関連データは権利関係の確認が必要なため、本リポジトリには含めていません。

## 開発状況

開発・実験中のプロジェクトです。各機能の仕様や構成は変更される場合があります。
