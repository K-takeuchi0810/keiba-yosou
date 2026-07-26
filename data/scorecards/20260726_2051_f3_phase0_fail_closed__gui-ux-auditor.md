# GUI / UX 監査人 採点（post-fix）

## 判定: HOLD

**理由**: fail-closed の状態・買付停止の影響・復旧手順・reason codeが日本語バナーと専用空状態で一貫して表示され、前回3指摘は閉鎖した。JS/onclickとproduction buy guardも動作可能。ただし既存の操作help欠如、progress ARIA不足、長時間工程のキャンセル粒度がプロ承認水準に未達。  
**根拠ファイル**: `gui/app.py:421-436`, `gui/app.py:853-868`, `gui/app.py:956-978`, `gui/app.py:2306-2332`, `gui/app.py:2391-2417`  
**次アクション**: `<details id="helpBox">` と progress ARIA を追加し、ingest / publish 内部までキャンセルを伝播して再監査する。

**改修タイプ**: type-D（GUI/HTML表示）。`gui/app.py` の未コミットdiffを採点対象とし、production wrapper / semantic guardはGUIの買付停止契約に必要な範囲だけ確認した。CLI・ledger・monitor・モバイルHTMLは専門外で採点しない。P25 backtest採用ゲートは N/A。

## 総合: 3.6 / 5（参考スコア）

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 主要操作は「取得 → 予想 → 公開」、個別操作は Ⅰ〜Ⅳ と具体的な `title` で順序と依存関係が分かる（`gui/app.py:1988-2001`）。ただし必須観点の `<details id="helpBox">` は存在せず、詳細設定・実行ログ用detailsだけである（`gui/app.py:2012-2024`）。
- **エラー人間化 / 復旧支援: 4/5** — blocked / observation を「予測停止 / 観察専用」と日本語化し、影響「買い候補は作成しません」、reason別の復旧手順、監査用codeを1バナーにまとめた（`gui/app.py:2306-2332`）。backend warningも同じ4 codeを日本語案内へ変換する（`gui/app.py:961-978`）。blocked / observation / full ごとの空状態を分離し、通常のEV見送りとの誤認も解消した（`gui/app.py:2391-2417`）。既存 `_safe` の error / hint / trace 分離と詳細トグルも維持（`gui/app.py:215-242`, `gui/app.py:2553-2556`）。軽微な留保はreason案内がPythonとJSに重複し、将来の文言ドリフト余地がある点。
- **進捗表示 / ETA / キャンセル: 3/5** — 1秒ポーリング、進捗率、ETA、中止ボタンを維持（`gui/app.py:2495-2519`, `gui/app.py:2528-2533`, `gui/app.py:2550`）。予想生成subprocessは0.5秒単位でcancel checkされる（`gui/app.py:123-136`, `gui/app.py:1142-1151`）。一方、progress要素に `role="progressbar"` / `aria-valuenow` がなく（`gui/app.py:1981-1985`）、DB ingestや公開コピー内部への細粒度キャンセル伝播は確認できない（`gui/app.py:1051-1066`, `gui/app.py:1157-1184`）。
- **二重実行防止 / ボタン状態管理: 4/5** — JSはstatus取得後にactionボタンを同期disableし、毎秒statusで維持する（`gui/app.py:2518-2526`, `gui/app.py:2538-2574`）。明示的 `inFlight` はないが、Python `_begin_run` がlock内でrunningを原子的にcheck-and-setし、JV-Link COM二重Openを防ぐ（`gui/app.py:275-286`）。GUIの買付判定はproduction専用wrapperへ統一され、modeがfull以外またはreasonが1件でもあれば通常filter前にFalseとなる（`gui/app.py:421-436`, `predictor/filter.py:141-164`）。
- **レイアウト / タップ領域 / アクセシビリティ: 3/5** — sidebarは `overflow-y:auto`、focus-visible、バナーは `role="alert"` を備える（`gui/app.py:1284-1294`, `gui/app.py:1855-1859`, `gui/app.py:2039`）。前回の未定義 `--buy-soft` は定義済み `--buy-bg` へ修正され、警告背景が有効になった（`gui/app.py:1253-1257`, `gui/app.py:1410-1418`）。一方、タブ・filter操作など一部buttonに `title` がなく、progress ARIAも未実装（`gui/app.py:2030-2047`, `gui/app.py:1984`）。

## 停止条件チェック

- [x] JS parse / onclick target: 不抵触。Python展開後 CONTROL_HTML script 23,290 bytesを `node --check` し PASS。onclick 8種（`cancelRun`, `forceRefresh`, `presetLatest`, `presetToday`, `presetWeekend`, `resetFilters`, `runAction`, `showTab`）は定義欠落0。
- [x] HTML parse: 不抵触。Python展開後 CONTROL_HTML を `html.parser.HTMLParser` で解析し PASS。
- [x] 関連テスト: 不抵触。`test_prediction_fail_closed.py`, `test_gui_js_contract.py`, `test_prediction_consumers.py`, `test_filter.py` は合計31 passed。
- [x] 買付fail-closed: 不抵触。GUIは `is_production_buy_candidate` のみを使用し、observation / blocked / full+reasonのいずれも買付不可（`gui/app.py:421-436`, `predictor/filter.py:141-164`）。
- [x] semantic guard: 不抵触。unknown reason、full+reason、non-full+reasonなし、reasonとmode矛盾を拒否し、consumer取得時の矛盾もblockedへ閉じる（`predictor/rules.py:55-77`, `predictor/rules.py:282-325`）。
- [x] 専門領域別Hard Fail: 不抵触。JS破損なし、状態バナー・専用空状態・production guardあり。
- [ ] git_sha / rule_version / env_overrides: N/A（type-D、backtest artifact採用判断ではない）。
- [ ] baseline paired / market_snapshot / payout欠損: N/A（type-D）。

## 反証の試み

- 改修の主張「blocked / observationでも通常のEV見送りと誤認しない」に対し分岐を追跡した。backendは通常文言を `prediction_mode == "full"` のときだけ追加し（`gui/app.py:959-960`）、JSはblocked / observation / fullの3空状態を別文言へ分岐する（`gui/app.py:2391-2417`）。成立。
- 改修の主張「GUI経由の買付はmode/reason矛盾時もfail-closed」に対しproduction wrapperとsemantic guardを確認した。wrapperは `mode != full OR reasons` で通常filter前にFalse（`predictor/filter.py:141-164`）、矛盾statusは生成時にValueError、consumer取得時もblockedへ収束する（`predictor/rules.py:55-77`, `predictor/rules.py:302-325`）。関連テスト31件もPASSし、成立。
- 改修の主張「警告背景が有効」に対しCSS tokenを照合した。使用する `--buy-bg` は `#fff1f2` として定義済み（`gui/app.py:1255`, `gui/app.py:1413`）。成立。

## 主な改善提案

1. **操作helpを追加** — sidebar末尾に `<details id="helpBox">` を置き、Ⅰ→Ⅱ→Ⅲ→Ⅳ、検証モード禁止事項、予測停止時の復旧順を短く記載する（`gui/app.py:2012-2024`）。
2. **progress ARIAを実装** — `#progressWrap` に `role="progressbar"` と min/max を付け、`applyStatus` で `aria-valuenow` / `aria-valuetext` を進捗・ETAと同期する（`gui/app.py:1984`, `gui/app.py:2506-2517`）。
3. **reason案内を単一出典化** — Pythonがcode / label / guidanceを構造化してsummaryへ返し、JSは表示だけを担う。`guidance_by_reason` と `reasonHelp` の将来不一致を防ぐ（`gui/app.py:963-968`, `gui/app.py:2311-2316`）。

## 前回からの差分

- 直前pre-fix: 本scorecard初版、判定 HOLD、総合 3.4。
- ボタン発見性: 4→4（変更なし）。
- エラー人間化: 3→4（+1）。日本語の状態・影響・復旧手順・codeと専用空状態で前回指摘を閉鎖。
- 進捗 / ETA / キャンセル: 3→3（変更なし）。
- 二重実行防止: 4→4（production wrapper / semantic guardを追加、プロ水準を維持）。
- レイアウト / アクセシビリティ: 3→3（未定義CSS tokenは修正。既存progress ARIA・button title課題が残る）。
- 総合: 3.4→3.6（+0.2）。判定はHOLDを維持。
- 時系列上の直近保存済み監査 `20260720_1905_f3_morning_anchor__gui-ux-auditor.md` はHOLD 3.6であり、post-fixは同水準へ復帰。
