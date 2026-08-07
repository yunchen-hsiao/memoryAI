"""
entity_profile_service.py — 匯入日記後，針對本次提到的人物做局部更新

與 backend/scripts/build_entities.py 的差異：
- build_entities.py 是全量重跑，會重新統計整個資料庫的關鍵字頻率，
  對所有達門檻的實體重新側寫（成本高，適合手動觸發）。
- update_entity_profiles() 只處理呼叫端傳入的人名清單（例如剛匯入的日記
  裡提到的人），不做全庫關鍵字統計，適合每次匯入後自動、輕量地觸發。

門檻與側寫邏輯（是否為人物、side-profile 產生方式）沿用 build_entities.py
的既有標準：至少 2 次互動才建檔，AI 判斷是否為人物並產生 description/relationship。
"""

import os
import json
import datetime
from google import genai
from google.genai import types
from supabase import create_client, Client

from security import decrypt_text

_supabase: Client | None = None
_genai_client = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_KEY")
        )
    return _supabase


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _genai_client


def _build_profile_prompt(entity_name: str, memories_text: str) -> str:
    return f"""
    你是一個頂尖的人類行為分析師。以下是日記主人與關鍵字「{entity_name}」過去的互動紀錄。
    首先，請判斷「{entity_name}」是不是一個具體的「人物」或「真實生活中的實體群體」（例如：室友、學姐、同事）。如果它只是一個地點（如台北）、一門課（如Linux課）、一個物品、專案或抽象概念（如資料庫、分組），請直接回傳 {{"is_person": false}}。

    如果確定是人物，請根據這些互動，對「{entity_name}」進行深度的人格側寫與行為分析。

    請以 JSON 格式輸出，只輸出 JSON，不要有其他廢話：
    {{
        "is_person": true,
        "description": "關於 {entity_name} 的性格特質、行為模式、潛在 MBTI（若能推測）、溝通風格等詳細的分析報告（約100-200字）。",
        "relationship": "他與使用者之間的關係狀態（例如：關係緊密的大學同學、經常交流的朋友等，簡短一句話）。"
    }}

    【互動歷史資料】：
    {memories_text}
    """


def update_entity_profiles(user_id: str, names: list[str]) -> None:
    """
    只針對傳入的人名重新產生 description/relationship，不做全庫關鍵字統計。
    任何單一人物側寫失敗都不影響其他人物的處理。
    """
    names = [n.strip() for n in (names or []) if n and n.strip()]
    if not names:
        return

    supabase = _get_supabase()
    client = _get_genai_client()

    memories_res = supabase.table("memories").select("id, summary, content, keywords, topic, diary_date") \
        .eq("user_id", user_id).execute()
    memories = memories_res.data or []
    for m in memories:
        m['summary'] = decrypt_text(m.get('summary', ''))
        m['content'] = decrypt_text(m.get('content', ''))
        m['keywords'] = [decrypt_text(k) for k in (m.get('keywords') or [])]

    if not memories:
        return

    for entity_name in names:
        related = [
            m for m in memories
            if entity_name in (m.get('keywords') or []) or entity_name in (m.get('summary') or '')
        ]
        # 沿用 build_entities.py 的門檻：至少 2 次互動才建檔
        if len(related) < 2:
            continue

        memories_text = "\n".join(
            f"[{m['diary_date']}] {m.get('content', m['summary'])}" for m in related
        )
        prompt = _build_profile_prompt(entity_name, memories_text)

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            profile = json.loads(response.text)

            if not profile.get("is_person", True):
                supabase.table("entities").delete().eq("name", entity_name).eq("user_id", user_id).execute()
                continue

            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            existing = supabase.table("entities").select("id").eq("name", entity_name).eq("user_id", user_id).execute()
            if existing.data:
                supabase.table("entities").update({
                    "description": profile["description"],
                    "relationship": profile["relationship"],
                    "updated_at": now_iso
                }).eq("id", existing.data[0]["id"]).execute()
            else:
                supabase.table("entities").insert({
                    "user_id": user_id,
                    "name": entity_name,
                    "description": profile["description"],
                    "relationship": profile["relationship"],
                    "updated_at": now_iso
                }).execute()
        except Exception as e:
            print(f"⚠️ update_entity_profiles: 編譯 {entity_name} 失敗，略過此人物: {e}")
            continue
