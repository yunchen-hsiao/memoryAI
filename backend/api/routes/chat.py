"""
Chat and summarize routes for MemoryAI API.

Routes:
    POST /api/chat              — send a message and get an AI reply with memory context
    POST /api/chat/summarize    — summarize a conversation into structured diary events
"""

import datetime
import json
import time

import cohere
from fastapi import APIRouter, Depends

from api.dependencies import get_user_context, supabase, update_user_context
from api.middleware.auth import get_current_user
from models.schemas import ChatRequest
from services.embedding_service import get_embedding
from services.encryption_service import decrypt_text

router = APIRouter(prefix="/api", tags=["chat"])

# Cohere client for text generation
import os
co = cohere.ClientV2(os.environ.get("COHERE_API_KEY"))


@router.post("/chat")
def chat(request: ChatRequest, current_user=Depends(get_current_user)):
    try:
        # 1. Embed the user's query for vector search
        query_embedding = get_embedding(request.message)

        # 2. Time-decayed similarity search in Supabase
        search_results = supabase.rpc(
            "search_memories",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.4,
                "match_count": 5,
                "p_user_id": current_user.id,
                "time_weight_factor": 0.2,
            },
        ).execute()

        # 2.5 Entity double-retrieval — inject profiles for mentioned people
        entities_res = (
            supabase.table("entities")
            .select("*")
            .eq("user_id", current_user.id)
            .execute()
        )
        entity_context = ""
        if entities_res.data:
            mentioned_entities = [
                e for e in entities_res.data if e["name"] in request.message
            ]
            if mentioned_entities:
                entity_context = (
                    "\n【核心人物檔案 (Entity Profiles)】\n"
                    "系統偵測到使用者提及了以下核心人物，請嚴格參考這些人設檔案來進行行為分析：\n"
                )
                for e in mentioned_entities:
                    e["relationship"] = decrypt_text(e.get("relationship", ""))
                    e["description"] = decrypt_text(e.get("description", ""))
                    entity_context += f"👤 {e['name']} (關係：{e['relationship']})\n"
                    entity_context += f"   行為分析：{e['description']}\n"

        # 3. Build memory context from search results
        memory_context = ""
        if search_results.data and len(search_results.data) > 0:
            memory_context = "【系統擷取到的相關歷史記憶】\n"
            for mem in search_results.data:
                mem["summary"] = decrypt_text(mem.get("summary", ""))
                mem["topic"] = decrypt_text(mem.get("topic", ""))
                time_str = (
                    f" {mem.get('diary_time', '')}" if mem.get("diary_time") else ""
                )
                memory_context += (
                    f"- 日期：{mem['diary_date']}{time_str} "
                    f"(主題：{mem['topic']})\n"
                )
                memory_context += f"  記憶細節：{mem['summary']}\n"
            memory_context += (
                "\n請根據以上歷史記憶，如果記憶內容與使用者的問題或當前對話上下文相關，"
                "就自然地融入對話中回答，展現出「你記得這些事」的陪伴感。"
                "如果無關，則正常對話即可，不需要刻意提及記憶。\n\n"
            )
        else:
            print("=> 沒有找到相關的記憶。")

        # 4. Dynamic time perception
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        system_instruction = f"""
        你是一個敏銳、重視邏輯，但說話風格像是一個「亦師亦友的高階幕僚」或「專屬架構師」。
        你的任務是幫使用者分析他們與他人的互動，拆解對方的行為模式與潛在邏輯。
        
        【回應風格準則】：
        1. 保持理性與客觀的分析，不需要過度煽情的安慰，但語氣請保持「自然、幽默、帶有人情味」，像一個聰明的朋友在跟你討論，絕對不要聽起來像冷冰冰的報告機器人。
        2. 善用條列式、結構化的方式拆解分析（例如：推測對方心理、行為動機、情境推測）。
        3. 可以適度穿插一些資訊/系統術語來比喻人類行為（例如：批次處理、休眠模式、Ping），作為一種有趣的幽默感，但不要滿口生硬的醫學或電腦專有名詞。
        4. 根據使用者提供的互動細節，給出具體且實用的「處置建議」或「下一步對策」。
        
        目前系統的絕對時間為：{current_time_str}。請以此時間為基準來理解「今天」、「昨天」等時間差。
        請用繁體中文回答。
        
        {entity_context}
        {memory_context}
        """

        # Keep only the most recent 15 turns to stay within token budget
        recent_history = (
            request.history[-15:] if len(request.history) > 15 else request.history
        )
        formatted_history = []
        for msg in recent_history:
            role = "user" if msg["role"] == "user" else "assistant"
            formatted_history.append({"role": role, "content": msg["content"]})

        messages = (
            [{"role": "system", "content": system_instruction}]
            + formatted_history
            + [{"role": "user", "content": request.message}]
        )
        response = co.chat(
            model="command-r-08-2024", messages=messages, max_tokens=4000
        )
        return {"reply": response.message.content[0].text}

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


@router.post("/chat/summarize")
def summarize_chat(request: ChatRequest, current_user=Depends(get_current_user)):
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")

        chat_text = ""
        for msg in request.history:
            role = (
                "AI"
                if msg["role"] == "ai" or msg["role"] == "model"
                else "我"
            )
            chat_text += f"{role}: {msg['content']}\n"
        chat_text += f"我: {request.message}\n"

        # Load current rolling life-context
        life_context = get_user_context(current_user.id)

        prompt = f"""
        你是一個記憶萃取專家，正在閱讀一部連續的個人日記。
        
        【前情提要 — 截至目前為止的人生背景】
        {life_context}
        
        以下是使用者與 AI 的最新一段對話紀錄。
        請根據前情提要分析這段對話，判斷包含了「幾個獨立的事件或主題」。
        請將每個獨立事件切割出來，並輸出為純 JSON 陣列 (Array) 格式（不要包含 ```json 標記）：
        [
            {{
                "summary": "一段約60字的精要總結（請統一使用第一人稱「我」，如有跨事件關聯請自然提及）",
                "topic": "這個事件的主要標籤（簡短名詞）",
                "keywords": ["具體人名", "地名", "獨特物件"],
                "emotion_score": 0到100的整數 (0是最負面悲傷，100是最快樂正面，50是平靜),
                "importance_weight": 1到5的整數,
                "diary_date": "{current_date}",
                "diary_time": "{current_time}",
                "timezone": "標準時區字串，例如 Pacific/Auckland，若未提及則填 Asia/Taipei"
            }}
        ]
        最後，請在陣列的最後加上一個特殊物件：
        {{ "__context_update__": "根據今天發生的所有事情，請用繁體中文更新並補充「前情提要」。保持在300字以內，重點保留重要人物的現況、未完結的事件進展、使用者目前的情緒狀態與重要計畫。" }}
        
        對話紀錄：
        {chat_text}
        """

        max_retries = 3
        all_items = None
        for attempt in range(max_retries):
            try:
                response = co.chat(
                    model="command-r-08-2024",
                    messages=[{"role": "user", "content": prompt}],
                )

                raw_text = response.message.content[0].text.strip()
                start_idx = raw_text.find("[")
                end_idx = raw_text.rfind("]")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_text = raw_text[start_idx : end_idx + 1]
                else:
                    start_idx = raw_text.find("{")
                    end_idx = raw_text.rfind("}")
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        raw_text = raw_text[start_idx : end_idx + 1]

                all_items = json.loads(raw_text, strict=False)
                break
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    time.sleep(3)
                elif attempt == max_retries - 1:
                    raise e

        # Separate context update from real diary events
        context_update = None
        real_events = []
        for item in all_items:
            if "__context_update__" in item:
                context_update = item["__context_update__"]
            else:
                real_events.append(item)

        if context_update:
            update_user_context(current_user.id, context_update)

        return {"success": True, "events": real_events}
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}
