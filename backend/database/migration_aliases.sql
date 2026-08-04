-- Migration: 新增 entities.aliases 欄位
-- 用途：讓 Entity_Resolver 能比對使用者訊息中提及的別名/稱呼，不只靠完全比對 name。
-- 屬於明文陣列（未加密），理由見 .kiro/specs/memory-graph-retrieval/design.md
-- 的 "為何 aliases 不加密" 章節：entities.name 本身也一直是明文，aliases 是同一性質
-- 的檢索用索引，不包含日記內容，加密會讓每次聊天都要多一輪解密運算。

ALTER TABLE entities ADD COLUMN IF NOT EXISTS aliases text[] DEFAULT '{}';
