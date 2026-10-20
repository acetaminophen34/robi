# Jetson → ESP32 → Robi 接続メモ

構成：Jetson TX2（Ubuntu）→ USBシリアル → ESP32-S3 → Robiのサーボバス。
ESP32には [`robi_motion.ino`](../motion_editor/robi_motion/robi_motion.ino) を書き込み済み。

## 今回の実機確認

- ポートは `/dev/ttyACM0`、115200 baud。Pythonのpyserialで双方向通信できた。
- `PING` → `ROBI_MOTION_V3`、`READ_ALL` による角度取得が成功。
- 一般ユーザーでは `Permission denied`。sudoでは通信できた。
- サーボの駆動は未確認。

## Jetson側の準備

```bash
sudo apt update
sudo apt install python3-serial
ls -l /dev/ttyACM*
```

ポートが見つからなければ、USBを接続し直して `sudo dmesg | tail -n 30` で確認する。
通常ユーザーにポートの利用権限を付ける場合は、`ls -l` で所有グループを確認する。`dialout` の場合：

```bash
sudo usermod -aG dialout "$USER"
```

ログアウト・再ログイン後、`id -nG` で反映を確認する。以降のコマンドは権限設定後なら `sudo` を外せる。この権限設定後の通信は今回未確認。
GUIなど、同じポートを使うプログラムは閉じておく。

## 成功した通信コマンド

PING：

```bash
sudo python3 -c 'import serial,time; s=serial.Serial("/dev/ttyACM0",115200,timeout=2); time.sleep(2); s.reset_input_buffer(); s.write(b"PING\n"); print("応答:",s.readline().decode(errors="replace").strip()); s.close()'
```

応答は `ROBI_MOTION_V3`。

角度取得：

```bash
sudo python3 -c 'import serial,time; s=serial.Serial("/dev/ttyACM0",115200,timeout=3); time.sleep(2); s.reset_input_buffer(); s.write(b"READ_ALL\n"); [print(s.readline().decode(errors="replace").strip()) for _ in range(21)]; s.close()'
```

正常時はID 2〜21の `POSE,<ID>,<角度>` が20行、最後に `DONE,READ_ALL` が返る。角度の単位は度。

## コマンド仕様（ソースコード上）

USB側は115200 baud、8N1。ASCIIのコマンドを改行 `\n` で終える。`\r` は無視され、空行には応答しない。起動時にも `ROBI_MOTION_V3` が出力される。

| コマンド | 処理・応答 |
|---|---|
| `PING` | `ROBI_MOTION_V3` を返す。動作中も使用可能。 |
| `READ_ALL` | ID 2〜21を順に読み、`POSE,<ID>,<角度>`、最後に `DONE,READ_ALL`。各IDは100 msで別形式の要求を再試行し、さらに100 msで失敗すると `ERR,READ,<ID>` で打ち切る。フレーム実行中・読取中は `ERR,BUSY`。 |
| `TORQUE,1` | 全20軸のトルクONを送信し、`OK,TORQUE`。読取中は `ERR,BUSY`。 |
| `STOP` / `TORQUE,0` | 実行・読取状態を解除し、全20軸のトルクOFFを送信。`OK,STOP`。 |
| `FRAME,<ms>,<角度2>,...,<角度21>` | 全20軸の目標角度・移動時間を送信。`OK,FRAME`、指定時間経過後に `DONE,FRAME`。実行中・読取中は `ERR,BUSY`。 |
| `FRAME_RAW,<ms>,<角度2>,...,<角度21>` | `FRAME` と同じだが、下記の軸別角度制限を適用しない。応答は同じ。 |

`FRAME` / `FRAME_RAW` の値：

- 時間は50〜163830 ms。サーボへの送信時は10 ms単位に丸める。
- 角度はID 2〜21の順に20個すべて指定し、0.1度単位に丸めて送信する。
- `FRAME` の角度制限：ID 16は−100〜100度、ID 17は−60〜80度、ID 18は0〜90度、その他は−150〜150度。
- `FRAME_RAW` も数値範囲は−3276.8〜3276.7度。これは通信上の範囲で、機体の可動範囲を示すものではない。
- 時間不正は `ERR,TIME`、角度不正・不足は `ERR,ANGLE`、余分な値は `ERR,FIELDS`。全値を検証してから送信する。

不明なコマンドは `ERR,COMMAND`、511文字を超える行は `ERR,LINE_TOO_LONG`。
`OK` は送信処理の完了、`DONE,FRAME` はESP32側の時間経過を表し、サーボの到達確認ではない。フレーム送信はトルクを自動でONにしない。

ファームのサーボ側設定はUART2・115200 baud・RX GPIO44・TX GPIO43、送受信切替はGPIO1。

## Python／LLMから使うとき

接続は `serial.Serial("/dev/ttyACM0", 115200, timeout=3)`。上の成功例と同様に、接続後2秒待って起動メッセージを捨て、`PING` で相手を確認する。通信中は同じ接続を保持し、終了時に閉じる。

将来のモーション実行は、LLMが選んだモーションをPython側でフレームに展開し、`TORQUE,1` → `FRAME,...` → `DONE,FRAME` を待って次のフレーム、の順で送る。受信は `readline()` で行い、`ERR,...` やタイムアウト時は処理を打ち切る。`READ_ALL` は21行固定で待つより、`DONE,READ_ALL` または `ERR,...` まで読むと失敗時にも対応できる。

このモーション実行経路とトルク操作は今回未検証。現在のLLM対話プログラムへの実機実行の組み込みも未実施。
