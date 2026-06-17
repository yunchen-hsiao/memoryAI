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

# 設定 Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    print("❌ 找不到 SUPABASE_URL 或 SUPABASE_KEY，請確認 .env 檔案是否設定正確。")
    exit(1)
supabase: Client = create_client(supabase_url, supabase_key)

# 設定 Gemini
client = genai.Client()

def get_embedding(text: str) -> list[float]:
    """呼叫 Gemini 產生文字的向量 (Embedding)"""
    response = client.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT"
        )
    )
    return response.embeddings[0].values

def analyze_diary(content: str, date_str: str) -> tuple[list, int]:
    """呼叫 Gemini 進行事件切割、情緒分析與細節提取"""
    prompt = f"""
    你現在是一個專業的心理分析師與記憶萃取專家。
    請閱讀以下 {date_str} 的日記內容，並判斷這篇日記包含了「幾個獨立的事件或主題」。
    請將每個獨立事件切割出來，提取豐富細節，並輸出為一個純 JSON 陣列 (Array) 格式（不要包含 ```json 等 Markdown 標記，直接回傳 [ 開始的字串）：
    [
        {{
            "summary": "一段約50字的精要總結（請統一使用第一人稱「我」來代表日記的主人，不要使用「作者」、「日記主人」等稱呼）",
            "topic": "這個事件的主要標籤（簡短名詞），例如：感情、專題討論、鋼琴社",
            "keywords": ["關鍵字1", "關鍵字2", "陳政煒", "餅乾", "具體人事物"], // 🚨 請絕對排除「聊天、訊息、回覆、朋友、我」等無意義的通稱，只留下「專有名詞、具體人名、地名、獨特物件」！
            "emotion_score": 0到100的整數 (0是最負面悲傷，100是最快樂正面，50是平靜),
            "importance_weight": 1到5的整數 (1是最不重要，5是對人生影響重大),
            "content_chunk": "與這個事件相關的日記原文段落（請保留原汁原味的金句或所有微小細節，不要刪減）"
        }}
    ]

    如果整篇日記只有一個主題，就回傳只有一個物件的陣列。

    日記內容：
    {content}
    """
    
    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            break # 成功就跳出迴圈
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e):
                if attempt < max_retries - 1:
                    wait_time = 5 + (attempt * 5)
                    print(f"\n   => ⚠️ Google 伺服器忙碌中，等待 {wait_time} 秒後自動重試 (第 {attempt+1}/{max_retries} 次)...")
                    time.sleep(wait_time)
                    continue
            # 如果不是 503/429 或是超過重試次數，就直接拋出錯誤
            raise e

    try:
        # 取得 Token 使用量
        token_count = 0
        if response.usage_metadata:
            token_count = response.usage_metadata.total_token_count

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3]
            
        data = json.loads(raw_text, strict=False)
        if not isinstance(data, list):
            data = [data] # 確保一定是陣列
            
        return data, token_count
    except Exception as e:
        print(f"❌ 解析 Gemini JSON 時發生錯誤 ({date_str}): {e}")
        print(f"Gemini 回傳內容: {response.text if response else 'None'}")
        return [], 0

def parse_and_upload(file_path: str):
    if not os.path.exists(file_path):
        print(f"❌ 找不到日記檔案：{file_path}")
        print("請在同一個資料夾下建立 'diary.txt' 並貼上你的日記內容。")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex 用來找出 YYYY/MM/DD 或 YYYY-M-D (支援單數月份或日期)
    date_pattern = re.compile(r'^(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*$', re.MULTILINE)
    
    matches = list(date_pattern.finditer(content))
    if not matches:
        print("❌ 在檔案中找不到任何符合日期的標記。")
        return

    entries = []
    for i in range(len(matches)):
        date_str = matches[i].group(1).replace('/', '-') # 統一轉成 YYYY-MM-DD
        start_idx = matches[i].end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(content)
        
        entry_text = content[start_idx:end_idx].strip()
        if entry_text:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            entries.append({"date": date_obj.isoformat(), "text": entry_text})

    total_entries = len(entries)
    print(f"✅ 成功找到 {total_entries} 篇日記，準備開始事件切割與上傳至 Supabase...")
    print("-" * 50)

    total_tokens_used = 0

    for idx, entry in enumerate(entries, 1):
        print(f"⏳ [{idx}/{total_entries}] 正在處理 {entry['date']} 的日記...")
        
        # 檢查是否已經存在同一天的日記 (以天為單位檢查，避免重複呼叫 AI)
        try:
            existing = supabase.table('memories').select('id').eq('diary_date', entry['date']).limit(1).execute()
            if existing.data and len(existing.data) > 0:
                print(f"   => ⚠️ 發現 {entry['date']} 已經在資料庫中，已跳過整天不處理。")
                print("-" * 50)
                continue
        except Exception as e:
            pass

        print(f"   - 呼叫 Gemini 分析切割中...")
        events, tokens = analyze_diary(entry['text'], entry['date'])
        total_tokens_used += tokens
        
        if events:
            for event in events:

                # 高細節向量化 (Rich Embedding)
                # 組合：日期 + 主題 + 摘要 + 關鍵實體 + 原文段落
                embedding_text = f"[{entry['date']}] 標籤:{event['topic']} - {event['summary']}。相關細節：{', '.join(event['keywords'])}。原文：{event.get('content_chunk', '')}"
                print(f"   - 正在轉換「{event['topic']}」的 Embedding 向量...")
                embedding = get_embedding(embedding_text)
                
                # 準備寫入資料庫的格式
                row = {
                    "content": event.get('content_chunk', entry['text']),
                    "summary": event['summary'],
                    "topic": event['topic'],
                    "keywords": event['keywords'],
                    "emotion_score": event['emotion_score'],
                    "importance_weight": event['importance_weight'],
                    "diary_date": entry['date'],
                    "embedding": embedding
                }
                
                try:
                    supabase.table('memories').insert(row).execute()
                    print(f"   => ✅ 寫入成功！主題：{event['topic']} / 情緒分數：{event['emotion_score']}")
                except Exception as e:
                    print(f"   => ❌ 寫入 Supabase 失敗：{e}")
        print("-" * 50)
        
    print(f"🎉 批次匯入作業全部完成！總計消耗 Gemini Tokens: {total_tokens_used}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    diary_path = os.path.join(current_dir, "diary.txt")
    parse_and_upload(diary_path)
