"""SmartRC 踏襲の独自競馬 Web アプリ (自己利用向け)。

- aggregate.py : 傾向集計 (コース × ファクター別の複勝率/回収率, Wilson CI 付)
- server.py    : FastAPI サーバ (出馬表 / 傾向集計 / 当日傾向速報)

JV-Data 由来のデータを一般公開する場合は JRA-VAN のサービス提供契約が必要。
本 webapp はローカル自己利用を前提とする。

予想生成 (gui/generator/ingest) への非干渉: プロセス分離 + DB は
db.open_db_readonly (mode=ro + query_only) のみ使用し、migration も書込みも
発行しない。予想結果・weights・calibrator を変更する経路は存在しない。
"""
