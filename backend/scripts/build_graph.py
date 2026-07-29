"""
build_graph.py — 一次性歷史資料同步腳本
讀取 Supabase 中所有現有記憶，批次同步到 Neo4j AuraDB。
執行方式: python scripts/build_graph.py <user_id>
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# 讓腳本能引用 backend 根目錄的模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from security import decrypt_text
from graph_db import sync_event_to_graph, get_driver, close_driver

def main():
    if len(sys.argv) < 2:
        print("使用方式: python scripts/build_graph.py <user_id>")
        print("  user_id: 您的 Supabase User ID（從 Supabase Auth > Users 查看）")
        exit(1)

    user_id = sys.argv[1]

    # 初始化 Supabase
    supabase = create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_KEY")
    )

    print(f"[START] Syncing memories for user {user_id} to Neo4j...")
    print("[INFO] Testing Neo4j connection...")
    
    try:
        driver = get_driver()
        driver.verify_connectivity()
        print("[OK] Neo4j connected!\n")
    except Exception as e:
        print(f"[ERROR] Neo4j connection failed: {e}")
        exit(1)

    # 建立索引（加速查詢，只需執行一次）
    print("[INFO] Creating Neo4j indexes...")
    with driver.session() as session:
        constraints = [
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT date_unique IF NOT EXISTS FOR (d:Date) REQUIRE d.date IS UNIQUE",
            "CREATE INDEX kw_name_user IF NOT EXISTS FOR (k:Keyword) ON (k.name, k.user_id)",
        ]
        for cypher in constraints:
            try:
                session.run(cypher)
            except Exception:
                pass  # 索引已存在時忽略
    print("[OK] Indexes created\n")

    # 抓取所有記憶
    print("[INFO] Loading memories from Supabase...")
    res = supabase.table("memories").select(
        "id, diary_date, topic, summary, keywords, emotion_score, content"
    ).eq("user_id", user_id).execute()
    
    memories = res.data or []
    if not memories:
        print("[ERROR] No memories found. Please import diary first!")
        return

    print(f"[INFO] Found {len(memories)} memories, syncing to Neo4j...\n")

    success = 0
    failed = 0

    for i, m in enumerate(memories):
        try:
            # 每 100 筆重建一次 Neo4j 連線，避免 AuraDB 免費版長連線超時
            if i > 0 and i % 100 == 0:
                close_driver()
                time.sleep(2)

            # 解密
            topic = decrypt_text(m.get("topic", ""))
            summary = decrypt_text(m.get("summary", ""))
            keywords = [decrypt_text(k) for k in (m.get("keywords") or [])]
            emotion_score = m.get("emotion_score", 50)
            date_str = m.get("diary_date", "")
            memory_id = str(m["id"])

            sync_event_to_graph(
                user_id=user_id,
                memory_id=memory_id,
                date_str=date_str,
                topic=topic,
                summary=summary,
                keywords=keywords,
                emotion_score=emotion_score
            )
            success += 1
            print(f"  [OK] [{i+1}/{len(memories)}] {date_str} | {topic}", end="\r")
            
            # 每 50 筆稍停一下，避免連線壓力
            if (i + 1) % 50 == 0:
                time.sleep(0.5)

        except Exception as e:
            failed += 1
            print(f"\n  [FAIL] [{i+1}] memory {m.get('id')} failed: {e}")

    print(f"""
======================================
  Neo4j Sync Complete!
  Success: {success} memories
  Failed:  {failed} memories
======================================
    """)
    print("[INFO] Go to Neo4j AuraDB > Query to browse your graph!")

if __name__ == "__main__":
    main()
