"""
graph_db.py — Neo4j AuraDB 共用連線模組
提供 get_driver() 和圖操作的 helper 函式
"""

import os
import time
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

load_dotenv()

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        # max_transaction_retry_time 縮短為 10 秒（預設 30 秒）：
        # AuraDB 免費層的路由表 ttl 只有 10 秒左右，遇到間歇性網路不穩時，
        # 讓失敗更快浮現，不要在批次匯入過程中卡住太久。
        # Neo4j 同步失敗不影響 Supabase 寫入，事後可用 build_graph.py 補跑修復。
        _driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            max_transaction_retry_time=10
        )
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None

def _reset_driver():
    """
    強制重建 driver（丟棄舊的連線池與路由表）。
    用於長時間執行的腳本（例如批次匯入）中，路由表過期或連線失效時的復原手段：
    單靠 retry_transaction 重試同一個壞掉的 driver 沒有用，必須重新建立連線。
    """
    global _driver
    if _driver:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None
    return get_driver()

def sync_event_to_graph(user_id: str, memory_id: str, date_str: str, keywords: list[str],
                         emotion_score: int, importance_weight: int = 3,
                         _retry: bool = True):
    """
    把一筆記憶事件同步到 Neo4j 圖資料庫。
    僅同步結構化關聯（人物、日期、情緒分數等），不寫入 topic/summary 等內容明文，
    以維持與 Supabase 加密欄位一致的隱私程度。事件內容一律回 Supabase 解密取得。

    若遇到路由資訊取得失敗或連線逾期（常見於長時間執行的批次腳本，AuraDB
    的連線池/路由表在間隔等待後失效），會重建 driver 後重試一次。
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            session.execute_write(
                _upsert_memory_graph,
                user_id, memory_id, date_str, keywords, emotion_score, importance_weight
            )
    except (ServiceUnavailable, SessionExpired) as e:
        if not _retry:
            raise
        print(f"⚠️ Neo4j 連線異常（{e}），重建連線後重試一次...")
        time.sleep(1)
        _reset_driver()
        sync_event_to_graph(user_id, memory_id, date_str, keywords, emotion_score,
                             importance_weight, _retry=False)

def _create_memory_graph(tx, user_id, memory_id, date_str, keywords, emotion_score, importance_weight):
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
    # 注意：只儲存結構化屬性，不存 topic/summary 等內容明文
    tx.run(
        """
        MERGE (e:Event {id: $memory_id})
        ON CREATE SET e.emotion_score = $emotion_score, e.importance_weight = $importance_weight,
                      e.date = $date_str, e.user_id = $user_id
        ON MATCH SET e.emotion_score = $emotion_score, e.importance_weight = $importance_weight
        """,
        memory_id=memory_id, emotion_score=emotion_score,
        importance_weight=importance_weight, date_str=date_str, user_id=user_id
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

def get_person_connections(user_id: str, person_name: str, limit: int | None = 30, _retry: bool = True) -> list[dict]:
    """
    查詢某人物的所有相關事件（多跳查詢）。
    只回傳結構化資訊（memory_id, date, emotion_score, importance_weight），
    不含事件內容，呼叫端需另外向 Supabase 查詢 memory_id 對應的記錄並解密。

    limit 預設保留 30 筆，供聊天 RAG 控制上下文大小；人物分析若要完整歷史，
    可傳入 limit=None，省略 Cypher LIMIT。
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            limit_clause = "LIMIT $limit" if limit is not None else ""
            query = f"""
                MATCH (u:User {{id: $user_id}})-[:EXPERIENCED]->(e:Event)-[:MENTIONS]->(k:Keyword {{name: $name, user_id: $user_id}})
                RETURN e.id AS memory_id, e.date AS date, e.emotion_score AS emotion_score, e.importance_weight AS importance_weight
                ORDER BY e.date DESC
                {limit_clause}
                """
            params = {"user_id": user_id, "name": person_name}
            if limit is not None:
                params["limit"] = limit
            result = session.run(query, **params)
            return [dict(record) for record in result]
    except (ServiceUnavailable, SessionExpired):
        if not _retry:
            raise
        _reset_driver()
        return get_person_connections(user_id, person_name, limit, _retry=False)

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
        # 取得所有 Keyword 節點（只抓有共現關係的，或常出現的）
        kw_result = session.run(
            """
            MATCH (k:Keyword {user_id: $user_id})
            WHERE k.mention_count > 1
            RETURN k.name AS name, k.mention_count AS count
            ORDER BY count DESC LIMIT 80
            """,
            user_id=user_id
        )
        nodes = [{"id": r["name"], "label": r["name"], "type": "keyword", "size": r["count"]} for r in kw_result]
        node_names = [n["id"] for n in nodes]

        if not node_names:
            return {"nodes": [], "links": []}

        # 取得 Keyword-Keyword 共現關係
        # 重要：必須限制在上面已選出的節點範圍內（$names）。
        # 否則節點查詢的 LIMIT 80 與連線查詢的 LIMIT 150 各自獨立，
        # 會產生「連線端點不在節點清單中」的懸空連線，導致前端 d3-force
        # 找不到對應節點而拋錯，整個力學模擬中斷（節點全部擠在中心不會動）。
        rel_result = session.run(
            """
            MATCH (k1:Keyword {user_id: $user_id})<-[:MENTIONS]-(e:Event)-[:MENTIONS]->(k2:Keyword {user_id: $user_id})
            WHERE k1.name < k2.name AND k1.name IN $names AND k2.name IN $names
            RETURN k1.name AS source, k2.name AS target, count(*) AS weight
            ORDER BY weight DESC LIMIT 150
            """,
            user_id=user_id, names=node_names
        )
        links = [{"source": r["source"], "target": r["target"], "weight": r["weight"]} for r in rel_result]

        return {
            "nodes": nodes,
            "links": links
        }

def get_person_relationship_graph(user_id: str, person_names: list[str],
                                   _retry: bool = True) -> dict:
    """
    取得「人物中心」的關係圖結構（供前端視覺化用）。

    與 get_full_graph() 的差異：
    - get_full_graph 會回傳所有高頻 Keyword（含地點、活動、雜訊通稱），節點多且雜。
    - 本函式只處理呼叫端傳入的人物白名單（通常來自 entities 表，已被 AI 判定為人物），
      節點數量少而精準，並額外聚合該人物相關事件的平均情緒與重要度。

    情緒/重要度來自 Neo4j Event 節點的結構化欄位，不需要解密任何日記內容。

    回傳:
        {
          "nodes": [{id, label, size, avg_score, event_count, first_date, last_date}, ...],
          "links": [{source, target, weight}, ...]
        }
    """
    names = [n.strip() for n in (person_names or []) if n and n.strip()]
    if not names:
        return {"nodes": [], "links": []}

    driver = get_driver()
    try:
        with driver.session() as session:
            node_result = session.run(
                """
                MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)-[:MENTIONS]->(k:Keyword {user_id: $user_id})
                WHERE k.name IN $names
                RETURN k.name AS name,
                       count(e) AS event_count,
                       avg(e.emotion_score) AS avg_score,
                       avg(e.importance_weight) AS avg_importance,
                       min(e.date) AS first_date,
                       max(e.date) AS last_date
                ORDER BY event_count DESC
                """,
                user_id=user_id, names=names
            )
            nodes = []
            for r in node_result:
                nodes.append({
                    "id": r["name"],
                    "label": r["name"],
                    "size": r["event_count"],
                    "event_count": r["event_count"],
                    "avg_score": round(r["avg_score"], 1) if r["avg_score"] is not None else None,
                    "avg_importance": round(r["avg_importance"], 1) if r["avg_importance"] is not None else None,
                    "first_date": r["first_date"],
                    "last_date": r["last_date"],
                })

            node_names = [n["id"] for n in nodes]
            if not node_names:
                return {"nodes": [], "links": []}

            # 連線僅限於已選出的節點之間，避免產生前端 d3-force 找不到端點的懸空連線
            rel_result = session.run(
                """
                MATCH (k1:Keyword {user_id: $user_id})<-[:MENTIONS]-(e:Event)-[:MENTIONS]->(k2:Keyword {user_id: $user_id})
                WHERE k1.name < k2.name AND k1.name IN $names AND k2.name IN $names
                RETURN k1.name AS source, k2.name AS target, count(*) AS weight
                ORDER BY weight DESC
                LIMIT 200
                """,
                user_id=user_id, names=node_names
            )
            links = [
                {"source": r["source"], "target": r["target"], "weight": r["weight"]}
                for r in rel_result
            ]

            return {"nodes": nodes, "links": links}
    except (ServiceUnavailable, SessionExpired):
        if not _retry:
            raise
        _reset_driver()
        return get_person_relationship_graph(user_id, person_names, _retry=False)


def upsert_event_to_graph(user_id: str, memory_id: str, date_str: str, keywords: list[str],
                          emotion_score: int, importance_weight: int = 3,
                          _retry: bool = True) -> None:
    """Idempotently create or update an Event and its structural relationships."""
    driver = get_driver()
    try:
        with driver.session() as session:
            session.execute_write(
                _upsert_memory_graph,
                user_id, memory_id, date_str, keywords, emotion_score, importance_weight
            )
    except (ServiceUnavailable, SessionExpired):
        if not _retry:
            raise
        _reset_driver()
        upsert_event_to_graph(
            user_id, memory_id, date_str, keywords, emotion_score,
            importance_weight, _retry=False
        )


def _upsert_memory_graph(tx, user_id: str, memory_id: str, date_str: str,
                         keywords: list[str], emotion_score: int,
                         importance_weight: int) -> None:
    # Event properties and ownership are safe to MERGE because Event.id is unique.
    tx.run(
        "MERGE (u:User {id: $user_id})",
        user_id=user_id,
    )
    tx.run(
        "MERGE (d:Date {date: $date_str})",
        date_str=date_str,
    )
    tx.run(
        """
        MERGE (e:Event {id: $memory_id})
        SET e.user_id = $user_id,
            e.date = $date_str,
            e.emotion_score = $emotion_score,
            e.importance_weight = $importance_weight
        """,
        memory_id=memory_id,
        user_id=user_id,
        date_str=date_str,
        emotion_score=emotion_score,
        importance_weight=importance_weight,
    )
    tx.run(
        """
        MATCH (u:User {id: $user_id}), (e:Event {id: $memory_id})
        MERGE (u)-[:EXPERIENCED]->(e)
        """,
        user_id=user_id,
        memory_id=memory_id,
    )
    # Remove stale date and keyword relationships before adding the new snapshot.
    tx.run(
        """
        MATCH (e:Event {id: $memory_id})-[r:OCCURRED_ON]->(d:Date)
        DELETE r
        """,
        memory_id=memory_id,
    )
    tx.run(
        """
        MATCH (e:Event {id: $memory_id})-[r:MENTIONS]->(k:Keyword)
        DELETE r
        """,
        memory_id=memory_id,
    )
    tx.run(
        """
        MATCH (e:Event {id: $memory_id}), (d:Date {date: $date_str})
        MERGE (e)-[:OCCURRED_ON]->(d)
        """,
        memory_id=memory_id,
        date_str=date_str,
    )
    for keyword in {str(item).strip() for item in keywords}:
        if not keyword or len(keyword) < 2 or len(keyword) > 6:
            continue
        tx.run(
            """
            MERGE (k:Keyword {name: $keyword, user_id: $user_id})
            """,
            keyword=keyword,
            user_id=user_id,
        )
        tx.run(
            """
            MATCH (e:Event {id: $memory_id}), (k:Keyword {name: $keyword, user_id: $user_id})
            MERGE (e)-[:MENTIONS]->(k)
            """,
            memory_id=memory_id,
            keyword=keyword,
            user_id=user_id,
        )
    # Recompute counts after replacing relationships, then remove stale nodes.
    tx.run(
        """
        MATCH (k:Keyword {user_id: $user_id})
        OPTIONAL MATCH (e:Event)-[r:MENTIONS]->(k)
        WITH k, count(r) AS mention_count
        SET k.mention_count = mention_count
        """,
        user_id=user_id,
    )
    tx.run(
        """
        MATCH (k:Keyword {user_id: $user_id})
        WHERE NOT (k)<-[:MENTIONS]-()
        DETACH DELETE k
        """,
        user_id=user_id,
    )
    tx.run(
        """
        MATCH (d:Date)
        WHERE NOT (d)<-[:OCCURRED_ON]-()
        DETACH DELETE d
        """
    )


def delete_event_from_graph(user_id: str, memory_id: str, _retry: bool = True) -> None:
    """Delete an Event and clean orphaned structural nodes/relationships."""
    driver = get_driver()
    try:
        with driver.session() as session:
            session.execute_write(_delete_memory_graph, user_id, memory_id)
    except (ServiceUnavailable, SessionExpired):
        if not _retry:
            raise
        _reset_driver()
        delete_event_from_graph(user_id, memory_id, _retry=False)


def _delete_memory_graph(tx, user_id: str, memory_id: str) -> None:
    tx.run(
        """
        MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event {id: $memory_id})
        DETACH DELETE e
        """,
        user_id=user_id,
        memory_id=memory_id,
    )
    tx.run(
        """
        MATCH (k:Keyword {user_id: $user_id})
        WHERE NOT (k)<-[:MENTIONS]-()
        DETACH DELETE k
        """,
        user_id=user_id,
    )
    tx.run(
        """
        MATCH (d:Date)
        WHERE NOT (d)<-[:OCCURRED_ON]-()
        DETACH DELETE d
        """
    )
