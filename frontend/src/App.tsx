import { useState, useEffect, useRef } from 'react'
import './index.css'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Dashboard from './components/Dashboard'
import MemoryTimeline from './components/MemoryTimeline'
import { MessageSquare, LayoutDashboard, History, Trash2 } from 'lucide-react'

interface SummarizedEvent {
  summary: string;
  topic: string;
  keywords: string[];
  emotion_score: number;
  importance_weight: number;
  content_chunk: string;
  diary_date: string;
  diary_time: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'dashboard' | 'timeline'>('chat')
  const [healthStatus, setHealthStatus] = useState<string>('Checking backend...')
  const [messages, setMessages] = useState<{role: string, content: string}[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSummarizing, setIsSummarizing] = useState(false)
  const [summarizedEvents, setSummarizedEvents] = useState<SummarizedEvent[] | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    if (activeTab === 'chat') {
      scrollToBottom()
    }
  }, [messages, isLoading, activeTab])

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then(res => res.json())
      .then(data => setHealthStatus(data.message))
      .catch(() => setHealthStatus('Backend is offline'))
  }, [])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const userMsg = { role: 'user', content: input }
    const currentHistory = [...messages]
    
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: input,
          history: currentHistory.map(m => ({
             role: m.role === 'ai' ? 'model' : 'user', 
             content: m.content 
          }))
        })
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'ai', content: data.reply }])
    } catch {
      setMessages(prev => [...prev, { role: 'error', content: 'Failed to connect to backend' }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSummarize = async () => {
    if (messages.length === 0) {
      alert('沒有可以歸檔的對話');
      return;
    }
    setIsSummarizing(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: "", history: messages.filter(m => m.role === 'user') })
      });
      const data = await res.json();
      if (data.success) {
        setSummarizedEvents(data.events);
      } else {
        alert('歸檔失敗：' + data.error);
      }
    } catch (err) {
      alert('網路錯誤：' + err);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleArchive = async () => {
    if (!summarizedEvents) return;
    
    try {
      for (const event of summarizedEvents) {
        await fetch(`${API_BASE}/api/memories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            diary_date: event.diary_date,
            diary_time: event.diary_time,
            topic: event.topic,
            summary: event.summary,
            emotion_score: event.emotion_score,
            importance_weight: event.importance_weight,
            keywords: event.keywords,
            content: event.content_chunk
          })
        });
      }
      alert('✅ 對話已成功歸檔至大腦中！');
      setSummarizedEvents(null);
      setMessages([]);
    } catch (err) {
      alert('歸檔過程發生錯誤：' + err);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-50 font-sans">
      <header className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950 shadow-md">
        <div className="flex items-center gap-8">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <span className="bg-gradient-to-r from-emerald-400 to-teal-500 bg-clip-text text-transparent">MemoryAI</span>
            <span className="text-sm font-normal text-slate-400 hidden sm:inline">心靈伴侶</span>
          </h1>
          
          <div className="flex bg-slate-800/50 p-1 rounded-lg border border-slate-700/50 backdrop-blur-sm">
            <button
              onClick={() => setActiveTab('chat')}
              className={`lg:hidden flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                activeTab === 'chat' 
                  ? 'bg-slate-700 text-emerald-400 shadow-sm' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              記憶對話
            </button>
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all
                ${activeTab === 'dashboard' ? 'bg-slate-700 text-emerald-400 shadow-sm' : ''}
                ${activeTab !== 'dashboard' ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50' : ''}
                ${activeTab === 'chat' ? 'lg:bg-slate-700 lg:text-emerald-400 lg:shadow-sm lg:hover:bg-slate-700' : ''}
              `}
            >
              <LayoutDashboard className="w-4 h-4" />
              大腦儀表板
            </button>
            <button
              onClick={() => setActiveTab('timeline')}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                activeTab === 'timeline' 
                  ? 'bg-slate-700 text-emerald-400 shadow-sm' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`}
            >
              <History className="w-4 h-4" />
              記憶時光機
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={handleSummarize}
            disabled={isSummarizing || messages.length === 0}
            className="text-sm px-4 py-2 bg-slate-800 hover:bg-slate-700 text-emerald-400 rounded-lg border border-emerald-500/30 transition-colors flex items-center gap-2 shadow-[0_0_10px_rgba(52,211,153,0.1)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSummarizing ? (
              <><div className="w-4 h-4 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"></div> 歸檔中...</>
            ) : (
              <><span>📦</span> 歸檔對話</>
            )}
          </button>
          <span className={`text-xs px-2 py-1 rounded-full hidden sm:block ${healthStatus.includes('running') ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
            {healthStatus.includes('running') ? '連線正常' : '已斷線'}
          </span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden flex-col lg:flex-row">
        <div className={`flex-col border-r border-slate-800 ${['dashboard', 'timeline'].includes(activeTab) ? 'flex' : 'hidden lg:flex'} lg:w-[60%] h-full overflow-hidden bg-slate-900/50`}>
          {activeTab === 'timeline' ? <MemoryTimeline /> : <Dashboard />}
        </div>

        <div className={`flex-col flex-1 ${activeTab === 'chat' ? 'flex' : 'hidden lg:flex'} h-full bg-slate-900`}>
          <main className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 space-y-4">
                <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center text-2xl animate-pulse shadow-[0_0_20px_rgba(52,211,153,0.1)]">
                  🧠
                </div>
                <p>準備好分享你的心情了嗎？</p>
              </div>
            )}
            
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] lg:max-w-[75%] p-4 rounded-2xl leading-relaxed shadow-sm ${
                  msg.role === 'user' 
                    ? 'bg-slate-700 text-slate-50 rounded-br-sm' 
                    : msg.role === 'error' 
                      ? 'bg-red-900/50 text-red-200 border border-red-800' 
                      : 'bg-slate-800 text-slate-200 rounded-bl-sm border border-slate-700/50 relative overflow-hidden'
                }`}>
                  {msg.role === 'ai' && (
                    <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500/50"></div>
                  )}
                  {msg.role === 'ai' ? (
                    <div className="prose prose-invert prose-emerald max-w-none prose-p:leading-relaxed prose-pre:bg-slate-800/50 prose-pre:border prose-pre:border-slate-700/50">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="max-w-[75%] p-4 rounded-2xl bg-slate-800 text-slate-400 rounded-bl-sm border border-slate-700/50 flex items-center gap-2">
                  <div className="w-2 h-2 bg-emerald-500/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-emerald-500/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-emerald-500/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  <span className="ml-2 text-sm text-emerald-500/70">大腦檢索中...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </main>

          <footer className="p-4 border-t border-slate-800 bg-slate-950">
            <div className="flex gap-3 w-full relative">
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                disabled={isLoading}
                placeholder="告訴我今天發生了什麼事..."
                className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-5 py-3 focus:outline-none focus:ring-1 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all disabled:opacity-50"
              />
              <button 
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="bg-emerald-600/90 hover:bg-emerald-500 text-white rounded-xl px-4 lg:px-6 py-3 font-medium transition-all transform active:scale-95 disabled:opacity-50 disabled:active:scale-100 shadow-[0_0_15px_rgba(52,211,153,0.15)] flex items-center justify-center"
              >
                發送
              </button>
            </div>
          </footer>
        </div>
      </div>

      {summarizedEvents && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-4xl shadow-2xl flex flex-col max-h-[90vh]">
            <h3 className="text-2xl font-bold text-slate-100 mb-2 flex items-center gap-2">
              <span>💾</span> 預覽並確認歸檔
            </h3>
            <p className="text-slate-400 mb-6 text-sm">AI 已自動將你們的對話切分為 {summarizedEvents.length} 個獨立事件。您可以自由修改內容再儲存。</p>
            
            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
              {summarizedEvents.map((event, idx) => (
                <div key={idx} className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5 space-y-4">
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center border-b border-slate-700 pb-3 gap-2">
                    <div className="flex items-center gap-3">
                      <h4 className="text-lg font-semibold text-emerald-400">事件 {idx + 1}</h4>
                      <button 
                        onClick={() => {
                          if (window.confirm('確定要刪除這個事件嗎？')) {
                            setSummarizedEvents(summarizedEvents.filter((_, i) => i !== idx));
                          }
                        }}
                        className="p-1.5 bg-slate-700/50 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 rounded-lg transition-colors"
                        title="刪除此事件"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="flex gap-2 sm:gap-4">
                      <input type="date" value={event.diary_date} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].diary_date = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 text-sm focus:outline-none focus:border-emerald-500" />
                      <input type="time" value={event.diary_time} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].diary_time = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 text-sm focus:outline-none focus:border-emerald-500" />
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="col-span-2">
                      <label className="block text-xs font-medium text-slate-500 mb-1">主題 (Topic)</label>
                      <input type="text" value={event.topic} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].topic = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">情緒分數 (0-100)</label>
                      <input type="number" value={isNaN(event.emotion_score) ? 0 : event.emotion_score} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].emotion_score = parseInt(e.target.value) || 0;
                        setSummarizedEvents(newEvents);
                      }} className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">關鍵字 (用逗號分隔)</label>
                    <input type="text" value={event.keywords.join(', ')} onChange={(e) => {
                      const newEvents = [...summarizedEvents];
                      newEvents[idx].keywords = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                      setSummarizedEvents(newEvents);
                    }} className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">摘要總結</label>
                    <textarea value={event.summary} onChange={(e) => {
                      const newEvents = [...summarizedEvents];
                      newEvents[idx].summary = e.target.value;
                      setSummarizedEvents(newEvents);
                    }} className="w-full h-20 bg-slate-900 border border-slate-700 rounded p-2 text-slate-200 focus:outline-none focus:border-emerald-500 resize-none custom-scrollbar" />
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-800">
              <button onClick={() => setSummarizedEvents(null)} className="px-5 py-2.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-xl transition-colors">
                取消
              </button>
              <button onClick={handleArchive} className="px-5 py-2.5 text-slate-900 bg-emerald-500 hover:bg-emerald-400 font-bold rounded-xl transition-colors shadow-[0_0_15px_rgba(52,211,153,0.3)]">
                確定歸檔並清空對話
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
