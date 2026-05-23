# Prediction Output

CLI:

```powershell
.\predict.bat
.\predict.bat --date 20260503 --top 5
.\predict.bat --date 20260503 --only-bets --min-odds 10 --max-odds 20
.\predict.bat --from 20260501 --to 20260503 --format csv
```

Fetch latest realtime win/place odds before prediction:

```powershell
.\.venv32\Scripts\python.exe -m scripts.fetch_odds --date 20260503
.\.venv32\Scripts\python.exe -m scripts.fetch_odds --from 20260501 --to 20260503
```

GUI:

```powershell
.\run.bat
```

Use the date fields, then run:

1. `JVLink でデータ取得`
2. `最新オッズ取得`
3. `予想生成`

Default behavior:

- No date option: uses the latest race date in the DB.
- `--only-bets`: shows only rank 1 picks whose win odds are within the odds filter.
- Default buy filter: win odds 10.0 to 20.0.
- `--format`: `table`, `csv`, or `json`.

Use another DB:

```powershell
.\predict.bat --date 20240106 --only-bets --db data\keiba_old_bstr.db
```
