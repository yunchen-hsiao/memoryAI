-- 【遷移腳本】新增 user_id 欄位並將舊資料綁定到新註冊的帳號
-- 請先在前端透過 Google 登入或註冊一個帳號。
-- 然後到 Supabase SQL Editor 執行以下查詢，找到你的帳號 ID：
-- SELECT id, email FROM auth.users;

-- 假設你的 ID 是 '12345678-1234-1234-1234-123456789abc'，請將下方引號內的 ID 替換掉並執行整個腳本：

DO $$
DECLARE
    my_user_id UUID := '7e49cc9e-2574-46bb-ba1a-a590335cc13f'; -- 例: '12345678-1234-1234-1234-123456789abc'
BEGIN
    -- 1. 新增 user_id 欄位 (如果不存在)
    BEGIN
        ALTER TABLE memories ADD COLUMN user_id UUID REFERENCES auth.users(id);
    EXCEPTION
        WHEN duplicate_column THEN null;
    END;

    BEGIN
        ALTER TABLE entities ADD COLUMN user_id UUID REFERENCES auth.users(id);
    EXCEPTION
        WHEN duplicate_column THEN null;
    END;

    -- 2. 將所有尚未綁定的記憶綁定給你
    UPDATE memories 
    SET user_id = my_user_id 
    WHERE user_id IS NULL;

    -- 3. 將所有尚未綁定的核心人物綁定給你
    UPDATE entities 
    SET user_id = my_user_id 
    WHERE user_id IS NULL;
    
    RAISE NOTICE '資料庫欄位新增與舊資料遷移完成！';
END $$;
