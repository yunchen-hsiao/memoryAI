"""
entity_resolver.py — 從使用者訊息中解析出被提及的人物

純函式模組，不觸碰資料庫或網路，方便單元測試。

比對邏輯：使用者日記皆使用人物全名（見 memory-graph-retrieval spec 的設計決定：
不由 AI 自動推測別名），因此比對主要依賴 entities.name 完全比對。
entities.aliases 欄位目前預設為空陣列，保留作為未來手動維護擴充點；
若該欄位有值，也一併納入比對，不影響現有行為。
"""


def resolve_mentioned_entities(message: str, entities: list[dict]) -> list[dict]:
    """
    比對訊息中是否包含任一 entity 的 name（或已手動維護的 aliases）。

    Args:
        message: 使用者傳入的聊天訊息文字
        entities: 已解密的 entity 記錄清單，每筆至少包含 "name"，
                  可選包含 "aliases"（list[str]，預設空陣列）

    Returns:
        命中的 entity dict 清單（保留原始欄位），同一個 entity（以 name 判斷）
        不會重複出現。若沒有任何命中，回傳空陣列。
    """
    if not message or not entities:
        return []

    matched = []
    seen_names = set()

    for entity in entities:
        name = (entity.get("name") or "").strip()
        if not name or name in seen_names:
            continue

        candidates = [name] + [
            a.strip() for a in (entity.get("aliases") or [])
            if a and isinstance(a, str) and len(a.strip()) >= 2
        ]

        if any(candidate in message for candidate in candidates):
            matched.append(entity)
            seen_names.add(name)

    return matched
