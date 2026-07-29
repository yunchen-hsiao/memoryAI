"""
graph_db.py — Neo4j AuraDB 共用連線模組
提供 get_driver() 和圖操作的 helper 函式
"""

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None

def sync_event_to_graph(user_id: str, memory_id: str, date_str: str, topic: str, summary: str, keywords: list[str], emotion_score: int):
    """
    把一筆記憶事件同步到 Neo4j 圖資料庫。
    建立：使用者節點、事件節點、日期節點、人物節點，以及它們之間的關係邊。
    """
    driver = get_driver()
    with driver.session() as session:
        session.execute_write(
            _create_memory_graph,
            user_id, memory_id, date_str, topic, summary, keywords, emotion_score
        )

def _create_memory_graph(tx, user_id, memory_id, date_str, topic, summary, keywords, emotion_score):
    # 1. 建立/合併 User 節點
    tx.run(
        "MERGE (u:User {id: $user_id})",
        user_id=user_id
    )

    # 2. 建立/合併 Date 節點
    tx.run(
        "MERGE (d:Date {date: $date})",
        date=date_str
    )

    # 3. 建立 Event 節點 (每次都是新的，用 memory_id 識別)
    tx.run(
        """
        MERGE (e:Event {id: $memory_id})
        ON CREATE SET e.topic = $topic, e.summary = $summary, 
                      e.emotion_score = $emotion_score, e.date = $date_str,
                      e.user_id = $user_id
        ON MATCH SET e.topic = $topic, e.summary = $summary,
                     e.emotion_score = $emotion_score
        """,
        memory_id=memory_id, topic=topic, summary=summary,
        emotion_score=emotion_score, date_str=date_str, user_id=user_id
    )

    # 4. 關係：User -> 擁有 -> Event
    tx.run(
        """
        MATCH (u:User {id: $user_id}), (e:Event {id: $memory_id})
        MERGE (u)-[:EXPERIENCED]->(e)
        """,
        user_id=user_id, memory_id=memory_id
    )

    # 5. 關係：Event -> 發生於 -> Date
    tx.run(
        """
        MATCH (e:Event {id: $memory_id}), (d:Date {date: $date_str})
        MERGE (e)-[:OCCURRED_ON]->(d)
        """,
        memory_id=memory_id, date_str=date_str
    )

    # 6. 建立 Person 節點與關係（來自 keywords，人物判斷靠名稱長度 2-5 字）
    for kw in keywords:
        kw = kw.strip()
        if not kw or len(kw) < 2 or len(kw) > 6:
            continue
        # 建立/合併 Keyword 節點
        tx.run(
            """
            MERGE (k:Keyword {name: $name, user_id: $user_id})
            ON CREATE SET k.mention_count = 1
            ON MATCH SET k.mention_count = k.mention_count + 1
            """,
            name=kw, user_id=user_id
        )
        # 關係：Event -> 提及 -> Keyword
        tx.run(
            """
            MATCH (e:Event {id: $memory_id}), (k:Keyword {name: $kw, user_id: $user_id})
            MERGE (e)-[:MENTIONS]->(k)
            """,
            memory_id=memory_id, kw=kw, user_id=user_id
        )

def get_person_connections(user_id: str, person_name: str, limit: int = 10) -> list[dict]:
    """查詢某人物的所有相關事件（多跳查詢）"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)-[:MENTIONS]->(k:Keyword {name: $name, user_id: $user_id})
            RETURN e.date AS date, e.topic AS topic, e.summary AS summary, e.emotion_score AS emotion_score
            ORDER BY e.date DESC
            LIMIT $limit
            """,
            user_id=user_id, name=person_name, limit=limit
        )
        return [dict(record) for record in result]

def get_co_mentioned_keywords(user_id: str, keyword_name: str, limit: int = 8) -> list[dict]:
    """查詢跟某關鍵字最常同時出現的其他關鍵字（共現分析）"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (k1:Keyword {name: $name, user_id: $user_id})<-[:MENTIONS]-(e:Event)-[:MENTIONS]->(k2:Keyword {user_id: $user_id})
            WHERE k2.name <> $name
            RETURN k2.name AS name, count(*) AS co_count
            ORDER BY co_count DESC
            LIMIT $limit
            """,
            user_id=user_id, name=keyword_name, limit=limit
        )
        return [dict(record) for record in result]

def get_full_graph(user_id: str) -> dict:
    """取得使用者完整的圖結構（供前端視覺化用）"""
    driver = get_driver()
    with driver.session() as session:
        # 取得所有 Keyword 節點
        kw_result = session.run(
            "MATCH (k:Keyword {user_id: $user_id}) RETURN k.name AS name, k.mention_count AS count",
            user_id=user_id
        )
        nodes = [{"id": r["name"], "label": r["name"], "type": "keyword", "size": r["count"]} for r in kw_result]

        # 取得所有 Event 節點（只取最近 50 個，避免過於複雜）
        ev_result = session.run(
            """
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)
            RETURN e.id AS id, e.topic AS topic, e.summary AS summary, e.date AS date, e.emotion_score AS emotion
            ORDER BY e.date DESC LIMIT 50
            """,
            user_id=user_id
        )
        event_nodes = [{"id": r["id"], "label": r["topic"], "type": "event", "summary": r["summary"], "date": r["date"], "emotion": r["emotion"]} for r in ev_result]

        # 取得所有 Keyword-Keyword 共現關係
        rel_result = session.run(
            """
            MATCH (k1:Keyword {user_id: $user_id})<-[:MENTIONS]-(e:Event)-[:MENTIONS]->(k2:Keyword {user_id: $user_id})
            WHERE k1.name < k2.name
            RETURN k1.name AS source, k2.name AS target, count(*) AS weight
            ORDER BY weight DESC LIMIT 100
            """,
            user_id=user_id
        )
        links = [{"source": r["source"], "target": r["target"], "weight": r["weight"]} for r in rel_result]

        return {
            "nodes": nodes + event_nodes,
            "links": links
        }
