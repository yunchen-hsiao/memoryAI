import { useState } from 'react';
import { UploadCloud, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface BatchImportProps {
  token: string | null;
}

export default function BatchImport({ token }: BatchImportProps) {
  const [text, setText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [status, setStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleImport = async () => {
    if (!text.trim()) {
      setMessage('請貼上日記內容！');
      setStatus('error');
      return;
    }

    // 簡單的 Regex 找出 YYYY-MM-DD 或 YYYY/MM/DD
    const dateRegex = /^(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*$/gm;
    const matches = Array.from(text.matchAll(dateRegex));

    if (matches.length === 0) {
      setMessage('找不到符合格式的日期標記 (例如: 2026-06-19)。請確保每個日期都在獨立的一行。');
      setStatus('error');
      return;
    }

    const entries: { date: string, content: string }[] = [];
    
    for (let i = 0; i < matches.length; i++) {
      const dateStr = matches[i][1].replace(/\//g, '-');
      const startIdx = matches[i].index! + matches[i][0].length;
      const endIdx = i + 1 < matches.length ? matches[i + 1].index : text.length;
      
      const content = text.substring(startIdx, endIdx).trim();
      if (content) {
        entries.push({ date: dateStr, content });
      }
    }

    if (entries.length === 0) {
      setMessage('有找到日期，但沒有內容。');
      setStatus('error');
      return;
    }

    setIsProcessing(true);
    setStatus('processing');
    setProgress({ current: 0, total: entries.length });
    setMessage(`準備匯入 ${entries.length} 天的日記...`);

    let successCount = 0;
    let skipCount = 0;

    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      setProgress({ current: i + 1, total: entries.length });
      setMessage(`正在處理 ${entry.date}...`);

      try {
        const res = await fetch(`${API_BASE}/api/import/single`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({
            date_str: entry.date,
            content: entry.content
          })
        });

        const data = await res.json();
        if (data.success) {
          if (data.skipped) {
            skipCount++;
          } else {
            successCount += data.inserted_count || 1;
          }
        } else {
          console.error(`Error on ${entry.date}:`, data.error);
        }
      } catch (err) {
        console.error(`Request failed for ${entry.date}:`, err);
      }
    }

    setIsProcessing(false);
    setStatus('success');
    setMessage(`匯入完成！成功處理了 ${successCount} 筆新記憶 (略過 ${skipCount} 筆重複資料)。`);
    setText('');
  };

  return (
    <div className="w-full max-w-4xl mx-auto py-8 px-4 sm:px-6">
      <div className="rounded-2xl p-6 sm:p-8 shadow-xl" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 rounded-xl" style={{ backgroundColor: 'rgba(92,179,161,0.15)' }}>
            <UploadCloud className="w-6 h-6" style={{ color: 'var(--color-m-accent2)' }} />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-bold" style={{ color: 'var(--color-m-text)' }}>大量匯入記憶</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--color-m-muted)' }}>
              將你的歷史日記貼在下方。系統會自動根據日期進行切割，並使用 AI 萃取事件與情緒。
            </p>
          </div>
        </div>

        <div className="mb-6 rounded-xl p-4 text-sm" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-muted)' }}>
          <p className="font-medium mb-2" style={{ color: 'var(--color-m-text)' }}>📋 格式要求：</p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li>日期必須單獨佔一行，格式為 <code className="px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--color-m-panel)', color: 'var(--color-m-accent2)', border: '1px solid var(--color-m-border)' }}>YYYY-MM-DD</code> 或 <code className="px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--color-m-panel)', color: 'var(--color-m-accent2)', border: '1px solid var(--color-m-border)' }}>YYYY/MM/DD</code></li>
            <li>日期下方接著寫該天的日記內容</li>
            <li>系統會自動將下一個日期標記視為隔天日記的開始</li>
          </ul>
        </div>

        <textarea 
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`2026-06-18\n今天開了專題的會，進度滿順利的。\n\n2026-06-19\n好累的一天，都在寫程式，沒時間吃飯。`}
          className="w-full h-96 rounded-xl p-4 focus:outline-none resize-none mb-6 custom-scrollbar font-mono text-sm"
          style={{ backgroundColor: 'var(--color-m-base)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}
          disabled={isProcessing}
        />

        {status !== 'idle' && (
          <div className={`mb-6 p-4 rounded-xl flex items-start gap-3`} style={{ 
            backgroundColor: status === 'error' ? 'rgba(192,100,100,0.15)' : 'var(--color-m-panel-alt)',
            border: '1px solid',
            borderColor: status === 'error' ? 'rgba(192,100,100,0.3)' : 'var(--color-m-border)',
            color: status === 'error' ? '#c08080' : 'var(--color-m-text)'
          }}>
            {status === 'processing' && <RefreshCw className="w-5 h-5 animate-spin mt-0.5" style={{ color: 'var(--color-m-accent1)' }} />}
            {status === 'success' && <CheckCircle className="w-5 h-5 mt-0.5" style={{ color: 'var(--color-m-accent2)' }} />}
            {status === 'error' && <AlertCircle className="w-5 h-5 mt-0.5" />}
            
            <div className="flex-1">
              <p className="font-medium">{message}</p>
              {status === 'processing' && (
                <div className="mt-3">
                  <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-m-base)' }}>
                    <div 
                      className="h-full transition-all duration-300" 
                      style={{ width: `${(progress.current / progress.total) * 100}%`, background: 'linear-gradient(90deg, var(--color-m-accent1), var(--color-m-accent2))' }}
                    ></div>
                  </div>
                  <p className="text-xs mt-1 text-right" style={{ color: 'var(--color-m-muted)' }}>{progress.current} / {progress.total}</p>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={handleImport}
            disabled={isProcessing || !text.trim()}
            className="flex items-center gap-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/50 py-2.5 px-6 rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            {isProcessing ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                <span>處理中...</span>
              </>
            ) : (
              <>
                <UploadCloud className="w-5 h-5" />
                <span>開始匯入</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
