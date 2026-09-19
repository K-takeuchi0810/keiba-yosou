# F3 Phase 0-0b paired control/treatment OOS ROI

**結論**: paired差分95%CIは0を含むため、3 POST-HIGHチャネルはROIに有意寄与しない。correctness章を閉じる。

OOS窓: `20260101`–`20260614` / rules SHA: `068efb0cce3d2b369942cced2d4601d04135f264` / bootstrap: day block, B=10000, seed=20260720

## 決定性チェック

| model | expected val AUC | reproduced val AUC | artifact SHA-256 |
|---|---:|---:|---|
| control | 0.791320 | 0.791320 | `b0bff530d105b40ea5fbff8d556add7fadac928a4190fc7735c364b356b608c7` |
| treatment | 0.788781 | 0.788781 | `debf5ebdef927bff7dd7d6319240849a9088c361cdfb1335d64c5fa981f950c4` |

## Paired OOS結果

| basis | control bets/hits/ROI (CI) | treatment bets/hits/ROI (CI) | d=control−treatment (CI) |
|---|---|---|---|
| (a) 各モデル自己選択 | 424/65/63.1132% ([49.5444%, 77.3060%]) | 425/65/62.0941% ([48.9680%, 76.2769%]) | +1.0191% ([-4.6737%, +6.4106%]) |
| (b-1) treatment bet races | 425/65/62.0941% ([48.9680%, 76.2769%]) | 425/65/62.0941% ([48.9680%, 76.2769%]) | +0.0000% ([+0.0000%, +0.0000%]) |
| (b-2) control bet races | 424/65/63.1132% ([49.5444%, 77.3060%]) | 424/65/63.1132% ([49.5444%, 77.3060%]) | +0.0000% ([+0.0000%, +0.0000%]) |

§3-4の事前コミット判定はbasis (a)に適用。95%CIが0を含む場合、3 POST-HIGHチャネルはROIに有意寄与しないと判定する。

## T-10正本転記用・確定ベースライン案

```text
control ROI = 63.1132% (95% CI [49.5444%, 77.3060%])
treatment ROI = 62.0941% (95% CI [48.9680%, 76.2769%])
paired d(control−treatment) = +1.0191% (95% CI [-4.6737%, +6.4106%])
de-leaked baseline = M2-treatment (3チャネル遮断・再学習後)
```

production artifact不変、DB read-only、2026-10-01以降の封印未アクセス。
