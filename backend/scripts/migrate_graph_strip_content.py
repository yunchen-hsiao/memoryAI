"""
migrate_graph_strip_content.py — 一次性遷移腳本
移除既有 Neo4j Event 節點上的 topic/summary 內容明文屬性，
只保留結構化屬性（id, date, user_id, emotion_score, importance_weight）。

使用情境：graph_db.py 的 sync_event_to_graph() 已改為不再寫入內容明文，
但既有資料庫中可能還殘留舊版寫入的 topic/summary 屬性，需要跑這支腳本清除。

執行方式: python scripts/migrate_graph_strip_content.py
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_db import get_driver, close_driver


def strip_event_content():
    driver = get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"[ERROR] Neo4j 連線失敗: {e}")
        exit(1)

    with driver.session() as session:
        before_total = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        before_with_content = session.run(
            "MATCH (e:Event) WHERE e.topic IS NOT NULL OR e.summary IS NOT NULL RETURN count(e) AS c"
        ).single()["c"]

        print(f"[INFO] 目前節點總數: {before_total}")
        print(f"[INFO] 含有 topic/summary 內容明文的 Event 節點數: {before_with_content}")

        if before_with_content == 0:
            print("[OK] 沒有需要清除的內容明文，跳過。")
            return

        session.run("MATCH (e:Event) REMOVE e.topic, e.summary")

        after_total = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        after_with_content = session.run(
            "MATCH (e:Event) WHERE e.topic IS NOT NULL OR e.summary IS NOT NULL RETURN count(e) AS c"
        ).single()["c"]

        print(f"[OK] 已移除 {before_with_content} 個 Event 節點的 topic/summary 屬性")
        print(f"[VERIFY] 節點總數（應與遷移前相同）: {after_total}")
        print(f"[VERIFY] 剩餘含內容明文的 Event 節點數（應為 0）: {after_with_content}")

        if after_total != before_total:
            print("[WARNING] 節點總數改變了，請人工檢查！")


if __name__ == "__main__":
    strip_event_content()
    close_driver()
