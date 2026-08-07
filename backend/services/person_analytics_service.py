"""
person_analytics_service.py — 人物分析共用邏輯

集中處理「人物總覽」、「人物詳情面板強化」、「人物對比」三個功能會共用的計算，
避免在 main.py 裡重複實作以下邏輯：
  - 情緒趨勢方向判斷（↑ 升溫 / ↓ 降溫 / 持平）
  - 生命週期線圖的月度聚合
  - 關鍵時刻（情緒劇烈轉折事件）偵測
  - 人物「現況簡報卡」摘要組裝

所有函式皆為純函式（輸入已準備好的資料，輸出計算結果），不直接觸碰資料庫或
Neo4j。呼叫端（main.py）負責先解密、查詢好事件清單再傳入，這樣這裡的邏輯
可以獨立於資料庫連線之外被驗證。
"""

TREND_UP = "up"
TREND_DOWN = "down"
TREND_FLAT = "flat"
TREND_UNKNOWN = "unknown"

_TREND_LABELS = {
    TREND_UP: "↑ 升溫",
    TREND_DOWN: "↓ 降溫",
    TREND_FLAT: "→ 持平",
    TREND_UNKNOWN: "— 資料不足",
}


def compute_trend_direction(
    chronological_scores: list,
    flat_threshold: float = 5.0,
) -> str:
    """
    依時間先後排列的情緒分數序列，判斷整體趨勢方向。

    做法：把序列切成前半段與後半段分別取平均再比較，而不是只比較頭尾兩筆，
    避免單一離群事件（例如某天大吵一架）誤導對整段關係的趨勢判斷。
    兩段平均差距超過 flat_threshold 才視為明確上升/下降，否則視為持平。

    Args:
        chronological_scores: 依事件發生時間排序（舊→新）的情緒分數，None 會被忽略。
        flat_threshold: 前後半段平均分差在此範圍內視為「持平」。

    Returns:
        "up" | "down" | "flat" | "unknown"（資料點少於 2 筆時回傳 unknown）
    """
    scores = [s for s in chronological_scores if s is not None]
    if len(scores) < 2:
        return TREND_UNKNOWN

    midpoint = len(scores) // 2
    first_half = scores[:midpoint]
    second_half = scores[midpoint:]

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    delta = second_avg - first_avg

    if abs(delta) < flat_threshold:
        return TREND_FLAT
    return TREND_UP if delta > 0 else TREND_DOWN


def trend_label(direction: str) -> str:
    """把趨勢方向轉成中文顯示用字串（含箭頭符號），供前端直接顯示。"""
    return _TREND_LABELS.get(direction, _TREND_LABELS[TREND_UNKNOWN])


def build_monthly_series(events: list[dict]) -> list[dict]:
    """
    把事件清單（需含 date、emotion_score）依月份聚合成生命週期線圖資料。

    Args:
        events: [{"date": "2026-01-15", "emotion_score": 70, ...}, ...]，
                 date 可以是 "YYYY-MM-DD" 字串或 None（會被忽略）。

    Returns:
        依月份排序的 [{"month": "2026-01", "event_count": 3, "avg_score": 65.0}, ...]
    """
    by_month: dict[str, list[float]] = {}
    for event in events:
        date = event.get("date") or ""
        month = date[:7]
        score = event.get("emotion_score")
        if not month or score is None:
            continue
        by_month.setdefault(month, []).append(score)

    return [
        {
            "month": month,
            "event_count": len(scores),
            "avg_score": round(sum(scores) / len(scores), 1),
        }
        for month, scores in sorted(by_month.items())
    ]


def detect_key_moments(events: list[dict], max_moments: int = 3) -> list[dict]:
    """
    從事件時間軸中挑出情緒分數變化最劇烈的幾個「轉折點」。

    做法：events 需依時間先後排序（舊→新），計算每一筆事件與前一筆事件的
    情緒分數差，取絕對差值最大的幾筆。第一筆事件沒有「前一筆」可比較，
    不會被選入候選。

    Args:
        events: 依時間先後排序（舊→新）且含 emotion_score 的事件清單，
                 建議同時含 date/topic/summary 供前端直接顯示。
        max_moments: 最多回傳幾個轉折點。

    Returns:
        [{...原始事件欄位..., "score_delta": int}, ...]，
        依 |score_delta| 由大到小排序；score_delta > 0 代表「比前一次更正向」。
    """
    scored_events = [e for e in events if e.get("emotion_score") is not None]
    if len(scored_events) < 2:
        return []

    candidates = []
    for previous, current in zip(scored_events, scored_events[1:]):
        delta = current["emotion_score"] - previous["emotion_score"]
        candidates.append({**current, "score_delta": delta})

    candidates.sort(key=lambda item: abs(item["score_delta"]), reverse=True)
    return candidates[:max_moments]


def summarize_person_state(
    events: list[dict],
    profile_updated_at: str | None,
) -> dict:
    """
    組裝人物「現況簡報卡」所需的摘要資訊。

    Args:
        events: 依時間先後排序（舊→新）且含 date/emotion_score 的事件清單。
        profile_updated_at: entities.updated_at 的 ISO 字串；舊資料可能為 None。

    Returns:
        {
          "latest_event": {...} | None,
          "trend_direction": "up" | "down" | "flat" | "unknown",
          "trend_label": "↑ 升溫" 等中文標籤,
          "profile_updated_at": ...,
        }
    """
    latest_event = events[-1] if events else None
    direction = compute_trend_direction([e.get("emotion_score") for e in events])

    return {
        "latest_event": latest_event,
        "trend_direction": direction,
        "trend_label": trend_label(direction),
        "profile_updated_at": profile_updated_at,
    }
