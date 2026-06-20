"""検証 HTML (オッズ鮮度無視で生成) を iCloud 公開面に出さないためのセーフティ。

判定ロジックを 1 箇所 (assert_safe_to_publish) に集約することで、CLI / GUI /
Python 直 import の 3 経路で記述が食い違うリスクを消す (2026-06-17 コード品質
監査人指摘の単一出典化)。

判定マトリクス:
  ignore_odds_freshness | publish | allow_stale | 結果
  ---------------------+---------+-------------+---------------------------
  False                | *       | *           | OK (publish 値そのまま)
  True                 | False   | *           | OK (publish=False)
  True                 | True    | False       | UNSAFE → publish=False に強制+warning
  True                 | True    | True        | OK (明示的に許可された)

戻り値は (publish_decision: bool, warning: str | None)。
- warning が非 None なら、UI / stderr で必ず表示すべき
- publish_decision を尊重して呼び出し側は最終的な publish 動作を決める

VERIFICATION_BANNER_MARKER は web/templates/index.html.j2 が verification mode
HTML に出力する class 名と、publish_to_icloud のスキャナが探す文字列の **唯一の
共有 symbol**。templates と generator のどちらか片方を変更したときに、もう片方が
気付かず publish ガードが沈黙する変更失敗モードを防ぐ。テンプレート側 / generator
側 / test 側はすべてこの定数を参照する。
"""
from __future__ import annotations


STALE_PUBLISH_WARNING = (
    "検証モード (オッズ鮮度無視) では iCloud 公開を強制的にスキップしました。"
    "実弾運用の HTML として外部に出さないためのセーフティです。"
)

# verification-banner の HTML class 名。検証モード HTML 検出の唯一の symbol。
# テンプレート側 (`web/templates/index.html.j2`) のクラス名と一致させる。
# 一致しなくなった瞬間に test_publish_safety の integration test が fail する。
VERIFICATION_BANNER_MARKER = 'class="verification-banner"'


def assert_safe_to_publish(
    ignore_odds_freshness: bool,
    publish: bool,
    allow_stale: bool = False,
) -> tuple[bool, str | None]:
    """検証モード × publish の併用を安全側に倒す純関数。

    呼び出し側で副作用 (sys.exit / print / log) を起こさず、判定結果 + 警告文を
    返すだけ。CLI 側は warning を stderr に出して publish=False で続行するか、
    上位で sys.exit に変換するかを選べる。
    """
    if not ignore_odds_freshness:
        return (publish, None)
    if not publish:
        return (False, None)
    if allow_stale:
        return (True, None)
    return (False, STALE_PUBLISH_WARNING)
