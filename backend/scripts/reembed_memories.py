"""
重新嵌入既有記憶的向量 (Re-embedding Migration Script)

背景：
    import_history_v2.py 過去誤用了 `gemini-embedding-2` 模型產生向量，
    但 main.py 的語意搜尋 (/api/chat) 一直是用 `gemini-embedding-001`。
    根據 Google 官方文件，這兩個模型的 embedding 向量空間互不相容，
    無法直接比較，因此資料庫裡舊有的向量在語意搜尋時的相似度計算是無意義的。

    這支腳本會：
      1. 讀出 memories 表所有記錄
      2. 解密 content / topic / summary / keywords
      3. 用跟 import_history_v2.py 相同的組合方式重建 embedding_text
         （因為完整日記原文沒有單獨保存，改用該筆事件的 content 欄位代替）
      4. 呼叫 gemini-embedding-001 重新產生向量
      5. 覆蓋寫回該筆記錄的 embedding 欄位
      6. 覆蓋前會先把舊的 embedding 備份到本機 JSON 檔，避免資料無法復原

使用方式：
    python reembed_memories.py [--dry-run]

    --dry-run : 只印出將要處理的筆數與範例，不呼叫 API、不寫入資料庫
"""

import os
import sys
import json
import time
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from security import decrypt_text

load_dotenv()

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    print("❌ 找不到 SUPABASE_URL 或 SUPABASE_KEY，請確認 .env 檔案是否設定正確。")
    sys.exit(1)
supabase: Client = create_client(supabase_url, supabase_key)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

TARGET_MODEL = "gemini-embedding-001"
BACKUP_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f"embedding_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
)
PAGE_SIZE = 500


def get_embedding(text: str) -> list[float]:
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.embed_content(
                model=TARGET_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            return response.embeddings[0].values
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "503" in error_str or "UNAVAILABLE" in error_str:
                wait_time = 5 + attempt * 5
                print(f"   => ⚠️ API 忙碌，等待 {wait_time} 秒後重試 ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            raise e
    raise RuntimeError(f"呼叫 embedding API 失敗，已達最大重試次數：{text[:50]}...")


def fetch_all_memories():
    """分頁抓取所有記憶記錄，避免單次查詢筆數過多。"""
    all_rows = []
    offset = 0
    while True:
        res = supabase.table("memories") \
            .select("id, content, topic, summary, keywords, diary_date") \
            .range(offset, offset + PAGE_SIZE - 1) \
            .execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_rows


def build_embedding_text(row: dict) -> str:
    content = decrypt_text(row.get("content") or "")
    topic = decrypt_text(row.get("topic") or "")
    summary = decrypt_text(row.get("summary") or "")
    keywords = [decrypt_text(k) for k in (row.get("keywords") or [])]
    diary_date = row.get("diary_date") or ""
    return f"[{diary_date}] 標籤:{topic} - {summary}。相關細節：{', '.join(keywords)}。原文：{content}"


def main():
    dry_run = "--dry-run" in sys.argv

    print("📚 讀取 memories 表資料中...")
    rows = fetch_all_memories()
    total = len(rows)
    print(f"✅ 共找到 {total} 筆記憶記錄需要重新嵌入。")

    if total == 0:
        print("沒有資料需要處理，結束。")
        return

    if dry_run:
        print("\n🔎 [--dry-run] 只顯示前 3 筆範例，不會呼叫 API 或寫入資料庫：\n")
        for row in rows[:3]:
            print("-" * 50)
            print(f"id: {row['id']}")
            print(f"embedding_text: {build_embedding_text(row)[:150]}...")
        return

    # 覆蓋前先備份舊的 id -> embedding 對照，避免資料無法復原
    print(f"💾 備份舊向量到 {BACKUP_FILE} ...")
    backup_rows = supabase.table("memories").select("id, embedding").execute().data or []
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup_rows, f)
    print(f"✅ 已備份 {len(backup_rows)} 筆舊向量。")

    success = 0
    failed = []

    for idx, row in enumerate(rows, 1):
        memory_id = row["id"]
        print(f"⏳ [{idx}/{total}] 處理記憶 {memory_id} ...", end="", flush=True)
        try:
            embedding_text = build_embedding_text(row)
            new_embedding = get_embedding(embedding_text)
            supabase.table("memories").update({"embedding": new_embedding}).eq("id", memory_id).execute()
            success += 1
            print(" => ✅ 完成")
        except Exception as e:
            failed.append(memory_id)
            print(f" => ❌ 失敗：{e}")

        # 避免觸發速率限制
        time.sleep(1)

    print(f"""
╔══════════════════════════════════════╗
║         ✅ 重新嵌入完成！             ║
╠══════════════════════════════════════╣
║  成功：{success:>3} 筆                        ║
║  失敗：{len(failed):>3} 筆                        ║
╚══════════════════════════════════════╝
    """)
    if failed:
        print(f"失敗的記憶 ID：{failed}")


if __name__ == "__main__":
    main()
