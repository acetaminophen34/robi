"""Display polarity inferred from Heart bilateral poses; never servo calibration."""
import math
from .motion import extract

# Robot x=left, y=up, z=forward. Rotations about x change sign across
# mirrored motors; rotations about z keep sign when raw bilateral angles
# already have opposite signs. Keep the existing right-side convention.
DISPLAY_SIGNS = {2:-1,3:1,4:1,5:1,6:-1,7:-1,8:-1,9:-1,10:-1,11:-1,
                 12:-1,13:1,14:-1,15:1,16:-1,17:1,18:1,19:1,20:1,21:-1}
PAIRS = [(2,7,'股関節 横','z'),(3,8,'股関節 縦','x'),(4,9,'ひざ','x'),
         (5,10,'足首 縦','x'),(6,11,'足首 横','z'),(16,19,'肩','x'),
         (17,20,'上腕','z'),(18,21,'前腕','x')]

def report(heart):
    frames=extract(heart/'座り.RM4',heart/'STARTUP.XML')['frames']
    lines=['Heartの左右軸推定（3D表示用）', '',
           f'根拠: 座り.RM4 の{len(frames)}姿勢。角度の平均を引いて左右の相関を比較。',
           '負の相関は左右の角度が逆に変化することを示します。',
           '強い相関でも、前後・内外の絶対方向の証明にはなりません。', '',
           '関節 / 右ID・左ID / 左右相関 / 推定の根拠 / 3D符号（右・左）']
    for a,b,name,axis in PAIRS:
        x=[f['angles'][str(a)] for f in frames]; y=[f['angles'][str(b)] for f in frames]
        mx=sum(x)/len(x);my=sum(y)/len(y)
        xx=sum((v-mx)**2 for v in x);yy=sum((v-my)**2 for v in y)
        r=sum((u-mx)*(v-my) for u,v in zip(x,y))/math.sqrt(xx*yy) if xx*yy else 0.
        strength='逆符号の傾向が強い' if r < -.85 else '弱い・対称性の仮定を使用'
        lines.append(f'{name} / {a}・{b} / {r:+.3f} / {strength} / {DISPLAY_SIGNS[a]:+d}・{DISPLAY_SIGNS[b]:+d}')
    lines.extend(['','x回転: 左右で3D符号を逆にする。z回転: 左右で3D符号を同じにする。',
                  '左肩ID19、左股関節横ID7、左足首横ID11を従来表示から反転。',
                  '腰・首は左右ペアがなく、従来の表示方向を維持しています。',
                  '実機コマンド、OFS、JSON角度は変更しません。',
                  '横回転はこのモーションだけでは根拠が弱く、機構の左右対称性からの推定です。'])
    return '\n'.join(lines)
