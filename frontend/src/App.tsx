import { useState, useEffect, useRef } from 'react'
import './index.css'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Dashboard from './components/Dashboard'
import MemoryTimeline from './components/MemoryTimeline'
import { MessageSquare, LayoutDashboard, History } from 'lucide-react'

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
    fetch('http://localhost:8000/api/health')
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
      const res = await fetch('http://localhost:8000/api/chat', {
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
      const res = await fetch('http://localhost:8000/api/chat/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: "", history: messages })
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
        await fetch('http://localhost:8000/api/memories', {
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
    <div className="flex flex-col h-screen bg-stone-50 text-stone-800 font-sans">
      <header className="p-4 border-b border-stone-200 flex justify-between items-center bg-white shadow-sm z-10 relative">
        <div className="flex items-center gap-8">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <span className="text-amber-700 tracking-wide">MemoryAI</span>
            <span className="text-sm font-normal text-stone-400 hidden sm:inline">心靈伴侶</span>
          </h1>
          
          <div className="flex bg-stone-100 p-1 sm:p-1.5 rounded-2xl border border-stone-200/60 backdrop-blur-sm">
            <button
              onClick={() => setActiveTab('chat')}
              className={`lg:hidden flex items-center gap-1.5 sm:gap-2 px-3 sm:px-5 py-1.5 sm:py-2 rounded-xl text-sm font-medium transition-all ${
                activeTab === 'chat' 
                  ? 'bg-white text-amber-700 shadow-sm border border-stone-200/50' 
                  : 'text-stone-500 hover:text-stone-800 hover:bg-stone-200/50'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              <span className="hidden md:inline">記憶對話</span>
            </button>
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-5 py-1.5 sm:py-2 rounded-xl text-sm font-medium transition-all
                ${activeTab === 'dashboard' ? 'bg-white text-amber-700 shadow-sm border border-stone-200/50' : ''}
                ${activeTab !== 'dashboard' ? 'text-stone-500 hover:text-stone-800 hover:bg-stone-200/50' : ''}
                ${activeTab === 'chat' ? 'lg:bg-white lg:text-amber-700 lg:shadow-sm lg:border lg:border-stone-200/50' : ''}
              `}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span className="hidden md:inline">大腦儀表板</span>
            </button>
            <button
              onClick={() => setActiveTab('timeline')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-5 py-1.5 sm:py-2 rounded-xl text-sm font-medium transition-all ${
                activeTab === 'timeline' 
                  ? 'bg-white text-amber-700 shadow-sm border border-stone-200/50' 
                  : 'text-stone-500 hover:text-stone-800 hover:bg-stone-200/50'
              }`}
            >
              <History className="w-4 h-4" />
              <span className="hidden md:inline">記憶時光機</span>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={handleSummarize}
            disabled={isSummarizing || messages.length === 0}
            className="text-sm px-5 py-2.5 bg-stone-800 hover:bg-stone-700 text-stone-50 rounded-2xl transition-all flex items-center gap-2 shadow-md disabled:opacity-50 disabled:cursor-not-allowed border border-transparent hover:shadow-lg"
          >
            {isSummarizing ? (
              <><div className="w-4 h-4 border-2 border-stone-200/30 border-t-white rounded-full animate-spin"></div> 歸檔中...</>
            ) : (
              <><span>📦</span> 歸檔對話</>
            )}
          </button>
          <span className={`text-xs px-3 py-1.5 rounded-full hidden sm:block ${healthStatus.includes('running') ? 'bg-teal-100 text-teal-700' : 'bg-rose-100 text-rose-700'}`}>
            {healthStatus.includes('running') ? '連線正常' : '已斷線'}
          </span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden flex-col lg:flex-row">
        <div className={`flex-col border-r border-stone-200 ${['dashboard', 'timeline'].includes(activeTab) ? 'flex' : 'hidden lg:flex'} lg:w-[60%] h-full overflow-hidden bg-stone-50/50`}>
          {activeTab === 'timeline' ? <MemoryTimeline /> : <Dashboard />}
        </div>

        <div className={`flex-col flex-1 ${activeTab === 'chat' ? 'flex' : 'hidden lg:flex'} h-full bg-stone-50/30 relative`}>
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-white to-transparent pointer-events-none"></div>
          <main className="flex-1 overflow-y-auto p-6 flex flex-col gap-6 relative z-0">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-stone-400 space-y-4">
                <div className="w-16 h-16 rounded-full bg-orange-50 flex items-center justify-center text-3xl animate-pulse shadow-sm border border-orange-100">
                  🧠
                </div>
                <p className="font-medium tracking-wide">準備好分享你的心情了嗎？</p>
              </div>
            )}
            
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] lg:max-w-[75%] p-5 rounded-3xl leading-relaxed shadow-sm ${
                  msg.role === 'user' 
                    ? 'bg-amber-600 text-white rounded-br-sm shadow-md' 
                    : msg.role === 'error' 
                      ? 'bg-rose-50 text-rose-600 border border-rose-200' 
                      : 'bg-white text-stone-700 rounded-bl-sm border border-stone-200 relative overflow-hidden'
                }`}>
                  {msg.role === 'ai' && (
                    <div className="absolute top-0 left-0 w-1.5 h-full bg-amber-300"></div>
                  )}
                  {msg.role === 'ai' ? (
                    <div className="prose prose-stone prose-amber max-w-none prose-p:leading-relaxed prose-pre:bg-stone-50 prose-pre:border prose-pre:border-stone-200 prose-headings:text-stone-800 prose-strong:text-amber-700 prose-a:text-teal-600">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <span className="text-[15px]">{msg.content}</span>
                  )}
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="max-w-[75%] p-5 rounded-3xl bg-white text-stone-400 rounded-bl-sm border border-stone-200 flex items-center gap-3 shadow-sm">
                  <div className="w-2.5 h-2.5 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  <span className="ml-2 text-sm font-medium text-stone-400">大腦思考中...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </main>

          <footer className="p-5 border-t border-stone-200 bg-white shadow-[0_-4px_20px_rgba(0,0,0,0.02)] z-10 relative">
            <div className="flex gap-4 w-full relative max-w-4xl mx-auto">
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                disabled={isLoading}
                placeholder="告訴我今天發生了什麼事..."
                className="flex-1 bg-stone-50 border border-stone-200 rounded-2xl px-6 py-3.5 focus:outline-none focus:ring-2 focus:ring-amber-500/30 text-stone-800 placeholder-stone-400 shadow-inner transition-all disabled:opacity-50 text-[15px]"
              />
              <button 
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="bg-amber-600 hover:bg-amber-500 text-white rounded-2xl px-6 lg:px-8 py-3.5 font-bold transition-all shadow-md hover:shadow-lg border-b-4 border-amber-700 active:border-b-0 active:translate-y-[4px] disabled:border-b-0 disabled:translate-y-[4px] disabled:opacity-50 disabled:shadow-none flex items-center justify-center tracking-wider"
              >
                發送
              </button>
            </div>
          </footer>
        </div>
      </div>

      {summarizedEvents && (
        <div className="fixed inset-0 bg-stone-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-stone-200 rounded-[2rem] p-8 w-full max-w-4xl shadow-2xl flex flex-col max-h-[90vh]">
            <h3 className="text-3xl font-black text-stone-800 mb-3 flex items-center gap-3">
              <span className="text-4xl">💾</span> 預覽並確認歸檔
            </h3>
            <p className="text-stone-500 font-medium mb-8 text-sm bg-amber-50 p-3 rounded-xl border border-amber-100 inline-block">AI 已自動將你們的對話切分為 {summarizedEvents.length} 個獨立事件。您可以自由修改內容再儲存。</p>
            
            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
              {summarizedEvents.map((event, idx) => (
                <div key={idx} className="bg-stone-50 border border-stone-200 rounded-2xl p-6 shadow-sm space-y-5">
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center border-b border-stone-200 pb-4 gap-3">
                    <h4 className="text-xl font-black text-amber-600">事件 {idx + 1}</h4>
                    <div className="flex gap-3 sm:gap-4">
                      <input type="date" value={event.diary_date} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].diary_date = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="bg-white border border-stone-200 rounded-xl p-2.5 text-stone-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm font-medium" />
                      <input type="time" value={event.diary_time} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].diary_time = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="bg-white border border-stone-200 rounded-xl p-2.5 text-stone-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm font-medium" />
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                    <div className="col-span-2">
                      <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">主題 (Topic)</label>
                      <input type="text" value={event.topic} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].topic = e.target.value;
                        setSummarizedEvents(newEvents);
                      }} className="w-full bg-white border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm font-medium" />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">情緒分數 (0-100)</label>
                      <input type="number" value={isNaN(event.emotion_score) ? 0 : event.emotion_score} onChange={(e) => {
                        const newEvents = [...summarizedEvents];
                        newEvents[idx].emotion_score = parseInt(e.target.value) || 0;
                        setSummarizedEvents(newEvents);
                      }} className="w-full bg-white border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm font-medium" />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">關鍵字 (用逗號分隔)</label>
                    <input type="text" value={event.keywords.join(', ')} onChange={(e) => {
                      const newEvents = [...summarizedEvents];
                      newEvents[idx].keywords = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                      setSummarizedEvents(newEvents);
                    }} className="w-full bg-white border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm font-medium" />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">摘要總結</label>
                    <textarea value={event.summary} onChange={(e) => {
                      const newEvents = [...summarizedEvents];
                      newEvents[idx].summary = e.target.value;
                      setSummarizedEvents(newEvents);
                    }} className="w-full h-24 bg-white border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 resize-none custom-scrollbar shadow-sm font-medium leading-relaxed" />
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-4 mt-8 pt-6 border-t border-stone-100">
              <button onClick={() => setSummarizedEvents(null)} className="px-6 py-3 text-stone-500 hover:text-stone-800 bg-stone-100 hover:bg-stone-200 rounded-2xl font-bold transition-colors">
                取消
              </button>
              <button onClick={handleArchive} className="px-6 py-3 text-white bg-amber-600 hover:bg-amber-500 font-bold rounded-2xl transition-all shadow-md hover:shadow-lg border-b-4 border-amber-700 active:border-b-0 active:translate-y-[4px]">
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
