# keiba-yosou

JRA-VAN JVLink を用いたローカル競馬予想アプリ。

- **データ取得**: JVLink (COM)
- **GUI**: ローカルアプリ（実装方針未定: PySide6 / Tauri / Electron など）
- **出力**: HTML（ローカル HTTP サーバ経由でスマホからも閲覧可）

## 構成

```
keiba-yosou/
├── jvlink_client/   # JVLink ラッパ（COM 呼び出し・データ取得ループ）
├── data/            # SQLite / 取得済みダンプ（同期対象外）
├── predictor/       # 予想ロジック
├── web/             # HTML 出力 + ローカル HTTP サーバ
│   ├── templates/
│   └── static/
└── gui/             # ローカル GUI 部分
```

## 前提条件

1. **JV-Link のインストール** — JRA-VAN サイトからインストーラを取得して導入。
2. **サービスキーの取得** — JRA-VAN Data Lab. の利用登録を行い、サービスキーを取得して `JVInit(sid)` の `sid` 引数に渡す。
3. **32bit プロセスでの実行** — JVLink は 32bit COM。Python から呼ぶ場合は **32bit 版 Python** + `pywin32` を使用。GUI / Web 部分は 64bit でも問題ないので、データ取得プロセスのみ分離する構成を推奨。

## 開発開始時の TODO

- [ ] 32bit Python 環境を別途用意（`py -3.x-32 -m venv .venv32` など）
- [ ] `jvlink_client/client.py` の `sid` を実サービスキーに差し替え
- [ ] SQLite スキーマ設計（`data/schema.sql`）
- [ ] 予想ロジック方針の決定（ルールベース / ML / 併用）
- [ ] ローカル LAN でスマホ閲覧する際の Bind アドレス・ファイアウォール設定
