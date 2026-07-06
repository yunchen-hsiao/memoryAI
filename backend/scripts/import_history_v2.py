import os
import re
import datetime
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

# 載入環境變數
load_dotenv()

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

# 設定 Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# 設定 Gemini
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ── 加密模組 (與 security.py 相同邏輯) ──────────────────────────────────────
from cryptography.fernet import Fernet
_fernet = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None

def encrypt_text(text: str, user_email: str) -> str:
    if not _fernet or not text:
        return text
    if ADMIN_EMAIL and user_email.strip().lower() == ADMIN_EMAIL:
        return text  # 管理員豁免
    return _fernet.encrypt(text.encode()).decode()

def get_embedding(text: str) -> list[float]:
    response = client.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return response.embeddings[0].values

# ── 全局脈絡 Helpers ────────────────────────────────────────────────────────
def get_user_context(user_id: str) -> str:
    try:
        res = supabase.table("user_contexts").select("life_context").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return res.data[0].get("life_context", "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。")
    except:
        pass
    return "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。"

def update_user_context(user_id: str, new_context: str):
    supabase.table("user_contexts").upsert({
        "user_id": user_id,
        "life_context": new_context,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).execute()

# ── 核心分析函式（帶前情提要）────────────────────────────────────────────────
def analyze_diary_with_context(content: str, date_str: str, life_context: str) -> tuple[list, str | None, int]:
    """
    呼叫 Gemini 分析日記，同時傳入滾動前情提要。
    回傳: (事件清單, 更新後的前情提要, token 數)
    """
    prompt = f"""
    你現在是一個專業的心理分析師與記憶萃取專家，正在閱讀一部連續的個人生活日記。

    【前情提要 — 截至目前為止的人生背景】
    {life_context}

    請根據以上前情提要，閱讀以下 {date_str} 的日記內容，判斷包含了「幾個獨立的事件或主題」。
    如果今天的事件與前情提要中的人物或事件有所關聯，請在 summary 中自然地點出前後因果。
    請將每個獨立事件切割出來，提取豐富細節，並輸出為一個純 JSON 陣列格式（不要包含 ```json 等 Markdown 標記）：
    [
        {{
            "summary": "一段約60字的精要總結（請統一使用第一人稱「我」，如有跨事件關聯請自然提及）",
            "topic": "這個事件的主要標籤（簡短名詞），例如：感情、專題討論、紐西蘭旅遊",
            "keywords": ["具體人名", "地名", "獨特物件"], // 排除「聊天、訊息、朋友、我」等無意義通稱
            "emotion_score": 0到100的整數 (0是最負面悲傷，100是最快樂正面，50是平靜),
            "importance_weight": 1到5的整數 (1是最不重要，5是對人生影響重大),
            "content_chunk": "與這個事件相關的日記原文段落（請保留原汁原味，不要刪減）",
            "diary_time": "HH:MM 格式，若無則填 null",
            "timezone": "標準時區字串，例如 Pacific/Auckland，若無則填 Asia/Taipei"
        }}
    ]
    最後，請在 JSON 陣列的最後加上一個特殊物件（作為最後一個元素）：
    {{ "__context_update__": "根據今天發生的所有事情，請用繁體中文更新並補充「前情提要」，請整合舊的前情提要內容，加入今天的新進展。保持在300字以內，重點保留重要人物的現況、未完結的事件進展、使用者目前的情緒狀態與重要計畫。" }}

    如果整篇日記只有一個主題，就回傳兩個元素的陣列（一個事件 + 一個 __context_update__）。
    日記內容：
    {content}
    """

    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            break
        except Exception as e:
            if ("503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                wait_time = 10 + (attempt * 10)
                print(f"   => ⚠️ API 忙碌，等待 {wait_time} 秒後重試 ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise e

    token_count = 0
    if response and response.usage_metadata:
        token_count = response.usage_metadata.total_token_count

    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:-3]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:-3]

    all_items = json.loads(raw_text, strict=False)
    if not isinstance(all_items, list):
        all_items = [all_items]

    events = []
    context_update = None
    for item in all_items:
        if "__context_update__" in item:
            context_update = item["__context_update__"]
        else:
            events.append(item)

    return events, context_update, token_count

# ── 主程式 ────────────────────────────────────────────────────────────────────
def main():
    import sys
    if len(sys.argv) < 2:
        print("使用方式: python import_history_v2.py <user_id> [diary_file]")
        print("  user_id    : 您的 Supabase User ID（從 Supabase Dashboard > Authentication > Users 查看）")
        print("  diary_file : 日記檔案路徑（預設: scripts/diary.txt）")
        exit(1)

    user_id = sys.argv[1]
    diary_file = sys.argv[2] if len(sys.argv) > 2 else "scripts/diary.txt"

    # 取得 user_email 用於加密
    try:
        user_res = supabase.auth.admin.get_user_by_id(user_id)
        user_email = user_res.user.email if user_res and user_res.user else ""
    except Exception as e:
        print(f"⚠️ 無法取得使用者 Email: {e}")
        user_email = ""
    print(f"✅ 使用者: {user_email}")

    # 讀取日記並按日期切割
    with open(diary_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 支援 YYYY/MM/DD 或 YYYY-MM-DD 格式
    date_pattern = re.compile(r'^(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*$', re.MULTILINE)
    parts = date_pattern.split(content)

    diary_by_date: dict[str, str] = {}
    i = 1
    while i < len(parts):
        raw_date = parts[i].strip()
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        normalized = raw_date.replace("/", "-")
        # 補齊月份日期
        segments = normalized.split("-")
        normalized = f"{segments[0]}-{int(segments[1]):02d}-{int(segments[2]):02d}"
        if text:
            diary_by_date[normalized] = text
        i += 2

    sorted_dates = sorted(diary_by_date.keys())
    print(f"\n📚 共找到 {len(sorted_dates)} 天的日記，開始逐日分析...\n")

    total_tokens = 0
    total_inserted = 0
    skipped = 0

    # 讀取目前已有的全局前情提要
    current_context = get_user_context(user_id)
    print(f"📖 載入現有前情提要（前50字）：{current_context[:50]}...\n")

    for date_str in sorted_dates:
        diary_text = diary_by_date[date_str]

        # 檢查是否已匯入過（跳過重複）
        existing = supabase.table("memories").select("id") \
            .eq("diary_date", date_str).eq("user_id", user_id).limit(1).execute()
        if existing.data:
            print(f"⏭️  {date_str} 已存在，跳過。")
            skipped += 1
            continue

        print(f"🔍 分析 {date_str}（{len(diary_text)} 字）...", end="", flush=True)

        try:
            events, context_update, tokens = analyze_diary_with_context(diary_text, date_str, current_context)
            total_tokens += tokens
            print(f" => 切割出 {len(events)} 個事件（消耗 {tokens} tokens）")

            # 將事件寫入資料庫
            for event in events:
                embedding_text = f"[{date_str}] 標籤:{event.get('topic','')} - {event.get('summary','')}。相關細節：{', '.join(event.get('keywords',[]))}。原文：{event.get('content_chunk', '')}"
                embedding = get_embedding(embedding_text)

                data = {
                    "user_id": user_id,
                    "diary_date": date_str,
                    "diary_time": event.get("diary_time"),
                    "timezone": event.get("timezone"),
                    "topic": encrypt_text(event.get("topic", ""), user_email),
                    "summary": encrypt_text(event.get("summary", ""), user_email),
                    "keywords": [encrypt_text(k, user_email) for k in event.get("keywords", [])],
                    "emotion_score": event.get("emotion_score", 50),
                    "importance_weight": event.get("importance_weight", 3),
                    "content": encrypt_text(event.get("content_chunk", ""), user_email),
                    "embedding": embedding
                }
                supabase.table("memories").insert(data).execute()
                total_inserted += 1

            # 更新滾動式前情提要
            if context_update:
                current_context = context_update
                update_user_context(user_id, current_context)
                print(f"   📝 前情提要已更新（前50字）：{current_context[:50]}...")

            # 避免 429，每天之間稍微暫停
            print(f"   ⏱️  等待 3 秒後繼續...")
            time.sleep(3)

        except Exception as e:
            print(f"\n   ❌ {date_str} 分析失敗：{e}")
            continue

    print(f"""
╔══════════════════════════════════════╗
║         ✅ 匯入完成！                ║
╠══════════════════════════════════════╣
║  共處理：{len(sorted_dates) - skipped:>3} 天（跳過 {skipped} 天）        ║
║  寫入事件：{total_inserted:>3} 筆                   ║
║  總消耗 Token：{total_tokens:>8} 個          ║
╚══════════════════════════════════════╝
    """)

if __name__ == "__main__":
    main()
