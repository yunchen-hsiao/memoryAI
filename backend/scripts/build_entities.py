import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

load_dotenv()

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    print("❌ 找不到 SUPABASE_URL 或 SUPABASE_KEY，請確認 .env 檔案設定。")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)
client = genai.Client()

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from security import decrypt_text

def build_entities():
    if len(sys.argv) < 2:
        print("❌ 缺少 user_id 參數！")
        return
    user_id = sys.argv[1]
    
    print(f"🚀 開始為用戶 {user_id} 執行「核心實體檔案編譯 (Entity Profiling)」...")
    
    # 1. 抓取使用者的所有記憶
    res = supabase.table("memories").select("id, summary, keywords, topic, diary_date").eq("user_id", user_id).execute()
    memories = res.data or []
    for m in memories:
        m['summary'] = decrypt_text(m.get('summary', ''))
        m['topic'] = decrypt_text(m.get('topic', ''))
        m['keywords'] = [decrypt_text(k) for k in (m.get('keywords') or [])]
        
    if not memories:
        print("❌ 沒有找到任何記憶資料。")
        return
        
    # 2. 計算關鍵字頻率 (篩選出真正的人名或重要實體)
    stop_words = {"聊天", "訊息", "回覆", "晚餐", "午餐", "朋友", "我", "自己", "今天", "明天", "昨天", "感覺", "覺得", "事情", "時候", "最近", "有點", "一起", "一下", "一個"}
    keyword_counts = {}
    keyword_memories = {}
    
    for m in memories:
        for kw in (m.get("keywords") or []):
            if not kw or len(kw) > 10 or kw in stop_words: continue
            
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            if kw not in keyword_memories:
                keyword_memories[kw] = []
            keyword_memories[kw].append(f"[{m['diary_date']}] {m['summary']}")
            
    # 3. 取出出現最多次的前 15 大實體
    # 設定門檻：至少要出現 2 次才算得上是「核心人物」
    top_entities = [kw for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True) if count >= 2][:15]
    
    # 4. 請 Gemini 進行深度側寫
    
    if not top_entities:
        print("⚠️ 沒有找到符合門檻的核心實體。")
        return
        
    print(f"🎯 鎖定 {len(top_entities)} 個核心實體：{', '.join(top_entities)}")
    
    # 4. 請 Gemini 進行深度側寫
    for entity_name in top_entities:
        print(f"\n🧠 正在編譯 {entity_name} 的行為模型檔案...")
        
        memories_text = "\n".join(keyword_memories[entity_name])
        
        prompt = f"""
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
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                )
                profile = json.loads(response.text)
                
                if not profile.get("is_person", True):
                    print(f"   ⏩ [{entity_name}] 不是人物，已自動略過。")
                    break
                
                # 5. 寫入資料庫 (先檢查是否已存在，存在則更新，不存在則新增)
                existing = supabase.table("entities").select("id").eq("name", entity_name).eq("user_id", user_id).execute()
                if existing.data and len(existing.data) > 0:
                    supabase.table("entities").update({
                        "description": profile["description"],
                        "relationship": profile["relationship"]
                    }).eq("id", existing.data[0]["id"]).execute()
                    print(f"   ✅ 已更新現有檔案。")
                else:
                    supabase.table("entities").insert({
                        "user_id": user_id,
                        "name": entity_name,
                        "description": profile["description"],
                        "relationship": profile["relationship"]
                    }).execute()
                    print(f"   ✨ 已建立全新檔案。")
                
                # 為了避免觸發 Gemini 免費版 15 RPM 的限制 (429 Too Many Requests)，每次成功後暫停 4.5 秒
                time.sleep(4.5)
                break # 成功就跳出 retry 迴圈
                    
            except Exception as e:
                error_msg = str(e)
                if ("503" in error_msg or "429" in error_msg) and attempt < max_retries - 1:
                    print(f"   ⏳ 遇到 API 速率限制 (429/503)，等待 10 秒後進行第 {attempt + 2} 次重試...")
                    time.sleep(10)
                else:
                    print(f"   ❌ 編譯 {entity_name} 失敗: {e}")
                    break

    print("\n🎉 所有核心實體編譯完成！聊天引擎現在變得更聰明了！")

if __name__ == "__main__":
    build_entities()
