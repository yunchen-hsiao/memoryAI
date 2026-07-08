import { useState, useEffect, useRef } from 'react'
import './index.css'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Dashboard from './components/Dashboard'
import MemoryTimeline from './components/MemoryTimeline'
import { Trash2, Menu, X, AlertCircle } from 'lucide-react'
import { BrainIcon, DashboardIcon, TimelineIcon, UploadIcon, ShieldIcon, LogoutIcon, MoonIcon, SunIcon } from './components/Icons'
import AuthScreen from './components/AuthScreen'
import BatchImport from './components/BatchImport'
import { supabase } from './supabase'

interface SummarizedEvent {
  summary: string;
  topic: string;
  keywords: string[];
  emotion_score: number;
  importance_weight: number;
  diary_date: string;
  diary_time: string;
  timezone?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'dashboard' | 'timeline' | 'import'>('dashboard')
  const [healthStatus, setHealthStatus] = useState<string>('Checking backend...')
  const [messages, setMessages] = useState<{ role: string, content: string }[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSummarizing, setIsSummarizing] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [showPrivacyModal, setShowPrivacyModal] = useState(false)
  const [summarizedEvents, setSummarizedEvents] = useState<SummarizedEvent[] | null>(null)
  const [session, setSession] = useState<any>(null)
  const [isAuthLoading, setIsAuthLoading] = useState(true)
  const [isDark, setIsDark] = useState(() => {
    const stored = localStorage.getItem('theme');
    return stored ? stored === 'dark' : true; // 預設深色
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 套用主題至 HTML root
  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.remove('light');
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
      root.classList.add('light');
    }
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark])

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

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setIsAuthLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    return () => subscription.unsubscribe()
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
        headers: {
          'Content-Type': 'application/json',
          ...(session ? { 'Authorization': `Bearer ${session.access_token}` } : {})
        },
        body: JSON.stringify({
          message: input,
          history: currentHistory
        })
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'ai', content: data.reply || data.error || '無法取得回應' }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'error', content: '網路錯誤，請稍後再試。' }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSummarize = async () => {
    if (messages.length === 0) return;
    setIsSummarizing(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat/summarize`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session ? { 'Authorization': `Bearer ${session.access_token}` } : {})
        },
        body: JSON.stringify({ history: messages })
      });
      const data = await res.json();
      if (data.events) {
        setSummarizedEvents(data.events);
      } else {
        alert('摘要失敗：' + (data.error || '未知錯誤'));
      }
    } catch (err) {
      alert('網路錯誤：' + err);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleArchive = async () => {
    if (!summarizedEvents) return;

    // 重建完整對話原文作為 content，確保原始內容不被 AI 改寫版本取代
    const fullChatText = messages.map(m => {
      const role = m.role === 'user' ? '我' : 'AI';
      return `${role}: ${m.content}`;
    }).join('\n');

    try {
      for (const event of summarizedEvents) {
        await fetch(`${API_BASE}/api/memories`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(session ? { 'Authorization': `Bearer ${session.access_token}` } : {})
          },
          body: JSON.stringify({
            diary_date: event.diary_date,
            diary_time: event.diary_time,
            topic: event.topic,
            summary: event.summary,
            emotion_score: event.emotion_score,
            importance_weight: event.importance_weight,
            keywords: event.keywords,
            content: fullChatText,  // 儲存完整對話原文，不使用 AI 改寫的 content_chunk
            timezone: event.timezone
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

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  if (isAuthLoading) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ backgroundColor: 'var(--color-m-base)', color: 'var(--color-m-muted)' }}>
        Loading...
      </div>
    );
  }

  if (!session) {
    return <AuthScreen isDark={isDark} onToggleTheme={() => setIsDark(d => !d)} />;
  }

  // 共用 inline style tokens
  const s = {
    base: { backgroundColor: 'var(--color-m-base)', color: 'var(--color-m-text)' },
    panel: { backgroundColor: 'var(--color-m-panel)' },
    header: { backgroundColor: 'var(--color-m-header)', borderBottom: '1px solid var(--color-m-border)' },
    border: { borderColor: 'var(--color-m-border)' },
    muted: { color: 'var(--color-m-muted)' },
    accent1: { color: 'var(--color-m-accent1)' },
    panelAlt: { backgroundColor: 'var(--color-m-panel-alt)' },
    userBubble: { backgroundColor: 'var(--color-m-user-bubble)', color: 'var(--color-m-text)' },
    aiBubble: { backgroundColor: 'var(--color-m-ai-bubble)', color: 'var(--color-m-text)', borderLeft: '3px solid var(--color-m-accent2)' },
    input: { backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' },
    btnPrimary: { background: 'linear-gradient(135deg, var(--color-m-accent1), var(--color-m-accent2))', color: isDark ? '#1e2228' : '#fff' },
    navActive: { backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-accent1)' },
    navInactive: { color: 'var(--color-m-muted)' },
  }

  const navBtnClass = (_tab?: string) =>
    `flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all`;

  return (
    <div className="flex flex-col h-screen font-sans" style={s.base}>
      {/* ===== Header ===== */}
      <header className="p-3 flex justify-between items-center shadow-sm z-40 shrink-0" style={s.header}>
        <div className="flex items-center gap-4 lg:gap-6">
          <div className="flex items-center gap-3">
            {/* Mobile Hamburger */}
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="lg:hidden p-2 -ml-1 rounded-md transition-colors"
              style={{ color: 'var(--color-m-muted)' }}
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            <h1 className="text-xl font-bold">
              <span className="text-morandi-gradient">MemoryAI</span>
              <span className="text-sm font-normal ml-2 hidden sm:inline" style={s.muted}>心靈伴侶</span>
            </h1>
          </div>

          {/* Desktop Nav */}
          <nav className="hidden lg:flex items-center p-1 rounded-lg gap-1" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
            <button onClick={() => setActiveTab('dashboard')} className={navBtnClass('dashboard')} style={activeTab === 'dashboard' ? s.navActive : s.navInactive}>
              <DashboardIcon size={16} /> 大腦儀表板
            </button>
            <button onClick={() => setActiveTab('timeline')} className={navBtnClass('timeline')} style={activeTab === 'timeline' ? s.navActive : s.navInactive}>
              <TimelineIcon size={16} /> 記憶時光機
            </button>
            <button onClick={() => setActiveTab('import')} className={navBtnClass('import')} style={activeTab === 'import' ? s.navActive : s.navInactive}>
              <UploadIcon size={16} /> 批次匯入
            </button>
          </nav>

          <div className="hidden lg:flex items-center gap-2">
            <button
              onClick={() => setShowPrivacyModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all"
              style={{ color: 'var(--color-m-accent2)', border: '1px solid var(--color-m-border)' }}
            >
              <ShieldIcon size={14} /> 隱私防護中
            </button>
            {/* Theme Toggle */}
            <button
              onClick={() => setIsDark(d => !d)}
              className="p-2 rounded-md transition-all"
              style={{ color: 'var(--color-m-muted)', backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}
              title={isDark ? '切換亮色模式' : '切換深色模式'}
            >
              {isDark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            </button>
            <button
              onClick={handleLogout}
              className="p-2 rounded-md transition-all"
              style={{ color: 'var(--color-m-muted)' }}
              title="登出"
            >
              <LogoutIcon size={18} />
            </button>
          </div>
        </div>

        {/* Right: Archive + Status */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSummarize}
            disabled={isSummarizing || messages.length === 0}
            className="text-sm px-4 py-2 rounded-lg border transition-all flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ ...s.input, color: 'var(--color-m-accent2)' }}
          >
            {isSummarizing ? (
              <><div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--color-m-border)', borderTopColor: 'var(--color-m-accent2)' }}></div> 歸檔中...</>
            ) : (
              <><span>📦</span> 歸檔對話</>
            )}
          </button>
          <span className={`text-xs px-2 py-1 rounded-full hidden sm:block`} style={{
            backgroundColor: healthStatus.includes('running') ? 'rgba(122,148,144,0.15)' : 'rgba(200,100,100,0.15)',
            color: healthStatus.includes('running') ? 'var(--color-m-accent2)' : '#c08080'
          }}>
            {healthStatus.includes('running') ? '連線正常' : '已斷線'}
          </span>
        </div>
      </header>

      {/* ===== Mobile Menu ===== */}
      {isMobileMenuOpen && (
        <div className="lg:hidden absolute top-[57px] left-0 right-0 z-50 p-4 flex flex-col gap-1 shadow-2xl" style={{ ...s.header, top: '57px' }}>
          {[
            { tab: 'chat', label: '記憶對話', Icon: BrainIcon },
            { tab: 'dashboard', label: '大腦儀表板', Icon: DashboardIcon },
            { tab: 'timeline', label: '記憶時光機', Icon: TimelineIcon },
            { tab: 'import', label: '批次匯入', Icon: UploadIcon },
          ].map(({ tab, label, Icon }) => (
            <button
              key={tab}
              onClick={() => { setActiveTab(tab as any); setIsMobileMenuOpen(false); }}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-base font-medium transition-all text-left"
              style={activeTab === tab ? s.navActive : s.navInactive}
            >
              <Icon size={20} /> {label}
            </button>
          ))}
          <div className="h-px my-1" style={{ backgroundColor: 'var(--color-m-border)' }}></div>
          <button
            onClick={() => { setShowPrivacyModal(true); setIsMobileMenuOpen(false); }}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-base font-medium transition-all text-left"
            style={{ color: 'var(--color-m-accent2)' }}
          >
            <ShieldIcon size={20} /> 隱私與安全防護聲明
          </button>
          <button
            onClick={() => { setIsDark(d => !d); setIsMobileMenuOpen(false); }}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-base font-medium transition-all text-left"
            style={s.navInactive}
          >
            {isDark ? <SunIcon size={20} /> : <MoonIcon size={20} />}
            {isDark ? '切換至亮色模式' : '切換至深色模式'}
          </button>
          <button
            onClick={() => { handleLogout(); setIsMobileMenuOpen(false); }}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-base font-medium transition-all text-left"
            style={{ color: '#c08080' }}
          >
            <LogoutIcon size={20} /> 登出
          </button>
        </div>
      )}

      {/* ===== Main Content ===== */}
      <div className="flex-1 flex overflow-hidden flex-col lg:flex-row">
        {activeTab === 'import' ? (
          <div className="flex-1 overflow-y-auto w-full h-full">
            <BatchImport token={session?.access_token || null} />
          </div>
        ) : (
          <>
            {/* Left Panel: Dashboard / Timeline */}
            <div
              className={`flex-col border-r ${['dashboard', 'timeline'].includes(activeTab) ? 'flex' : 'hidden lg:flex'} lg:w-[60%] h-full overflow-hidden`}
              style={{ borderColor: 'var(--color-m-border)', backgroundColor: 'var(--color-m-base)' }}
            >
              {activeTab === 'timeline'
                ? <MemoryTimeline token={session?.access_token || null} />
                : <Dashboard token={session?.access_token || null} />
              }
            </div>

            {/* Right Panel: Chat */}
            <div className={`flex-col flex-1 ${activeTab === 'chat' ? 'flex' : 'hidden lg:flex'} h-full`} style={s.base}>
              <main className="flex-1 overflow-y-auto p-5 flex flex-col gap-5 custom-scrollbar">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full space-y-4" style={s.muted}>
                    <div className="w-16 h-16 rounded-full flex items-center justify-center animate-pulse" style={s.panel}>
                      <BrainIcon size={32} />
                    </div>
                    <p>準備好分享你的心情了嗎？</p>
                  </div>
                )}

                {messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] lg:max-w-[75%] p-4 rounded-2xl leading-relaxed shadow-sm ${
                        msg.role === 'user' ? 'rounded-br-sm' :
                        msg.role === 'error' ? 'rounded-bl-sm' :
                        'rounded-bl-sm pl-5'
                      }`}
                      style={
                        msg.role === 'user' ? s.userBubble :
                        msg.role === 'error' ? { backgroundColor: 'rgba(180,80,80,0.15)', color: '#c09090', border: '1px solid rgba(180,80,80,0.3)' } :
                        s.aiBubble
                      }
                    >
                      {msg.role === 'ai' ? (
                        <div className="prose max-w-none prose-p:leading-relaxed" style={{ color: 'var(--color-m-text)' }}>
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
                    <div className="p-4 rounded-2xl rounded-bl-sm flex items-center gap-2 pl-5" style={s.aiBubble}>
                      {[0, 150, 300].map(delay => (
                        <div key={delay} className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: 'var(--color-m-accent1)', animationDelay: `${delay}ms` }}></div>
                      ))}
                      <span className="ml-2 text-sm" style={s.muted}>大腦檢索中...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </main>

              <footer className="p-4 shrink-0" style={{ borderTop: '1px solid var(--color-m-border)', backgroundColor: 'var(--color-m-header)' }}>
                <div className="flex gap-3 w-full">
                  <textarea
                    rows={5}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    disabled={isLoading}
                    placeholder="告訴我今天發生了什麼事... (按 Enter 發送，Shift+Enter 換行)"
                    className="flex-1 rounded-xl px-5 py-3 focus:outline-none transition-all disabled:opacity-50 resize-none custom-scrollbar"
                    style={{
                      ...s.input,
                      outline: 'none',
                    }}
                    onFocus={e => e.target.style.borderColor = 'var(--color-m-accent1)'}
                    onBlur={e => e.target.style.borderColor = 'var(--color-m-border)'}
                  />
                  <button
                    onClick={handleSend}
                    disabled={isLoading || !input.trim()}
                    className="rounded-xl px-5 py-3 font-medium transition-all transform active:scale-95 disabled:opacity-40 disabled:active:scale-100 flex items-center justify-center"
                    style={s.btnPrimary}
                  >
                    發送
                  </button>
                </div>
              </footer>
            </div>
          </>
        )}
      </div>

      {/* ===== Archive Preview Modal ===== */}
      {summarizedEvents && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-2xl p-6 w-full max-w-4xl shadow-2xl flex flex-col max-h-[90vh]" style={s.panel}>
            <h3 className="text-2xl font-bold mb-2 flex items-center gap-2" style={{ color: 'var(--color-m-text)' }}>
              <span>💾</span> 預覽並確認歸檔
            </h3>
            <p className="mb-6 text-sm" style={s.muted}>AI 已自動將你們的對話切分為 {summarizedEvents.length} 個獨立事件。您可以自由修改內容再儲存。</p>

            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
              {summarizedEvents.map((event, idx) => (
                <div key={idx} className="rounded-xl p-5 space-y-4" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center pb-3 gap-2" style={{ borderBottom: '1px solid var(--color-m-border)' }}>
                    <div className="flex items-center gap-3">
                      <h4 className="text-lg font-semibold" style={s.accent1}>事件 {idx + 1}</h4>
                      <button
                        onClick={() => { if (window.confirm('確定要刪除這個事件嗎？')) { setSummarizedEvents(summarizedEvents.filter((_, i) => i !== idx)); } }}
                        className="p-1.5 rounded-lg transition-colors"
                        style={{ backgroundColor: 'var(--color-m-hover)', color: 'var(--color-m-muted)' }}
                        title="刪除此事件"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="flex gap-2 sm:gap-4">
                      <input type="date" value={event.diary_date} onChange={(e) => { const n = [...summarizedEvents]; n[idx].diary_date = e.target.value; setSummarizedEvents(n); }} className="rounded p-1.5 text-sm focus:outline-none" style={s.input} />
                      <input type="time" value={event.diary_time} onChange={(e) => { const n = [...summarizedEvents]; n[idx].diary_time = e.target.value; setSummarizedEvents(n); }} className="rounded p-1.5 text-sm focus:outline-none" style={s.input} />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="col-span-2">
                      <label className="block text-xs font-medium mb-1" style={s.muted}>主題 (Topic)</label>
                      <input type="text" value={event.topic} onChange={(e) => { const n = [...summarizedEvents]; n[idx].topic = e.target.value; setSummarizedEvents(n); }} className="w-full rounded p-2 focus:outline-none" style={s.input} />
                    </div>
                    <div>
                      <label className="block text-xs font-medium mb-1" style={s.muted}>情緒分數 (0-100)</label>
                      <input type="number" value={isNaN(event.emotion_score) ? 0 : event.emotion_score} onChange={(e) => { const n = [...summarizedEvents]; n[idx].emotion_score = parseInt(e.target.value) || 0; setSummarizedEvents(n); }} className="w-full rounded p-2 focus:outline-none" style={s.input} />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium mb-1" style={s.muted}>關鍵字 (用逗號分隔)</label>
                    <input type="text" value={event.keywords.join(', ')} onChange={(e) => { const n = [...summarizedEvents]; n[idx].keywords = e.target.value.split(',').map(s => s.trim()).filter(Boolean); setSummarizedEvents(n); }} className="w-full rounded p-2 focus:outline-none" style={s.input} />
                  </div>

                  <div>
                    <label className="block text-xs font-medium mb-1" style={s.muted}>摘要總結</label>
                    <textarea value={event.summary} onChange={(e) => { const n = [...summarizedEvents]; n[idx].summary = e.target.value; setSummarizedEvents(n); }} className="w-full h-20 rounded p-2 focus:outline-none resize-none custom-scrollbar" style={s.input} />
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-3 mt-6 pt-4" style={{ borderTop: '1px solid var(--color-m-border)' }}>
              <button onClick={() => setSummarizedEvents(null)} className="px-5 py-2.5 rounded-xl transition-colors" style={{ color: 'var(--color-m-muted)', backgroundColor: 'var(--color-m-panel-alt)' }}>
                取消
              </button>
              <button onClick={handleArchive} className="px-5 py-2.5 font-bold rounded-xl transition-colors" style={s.btnPrimary}>
                確定歸檔並清空對話
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Privacy Modal ===== */}
      {showPrivacyModal && (
        <div className="fixed inset-0 flex items-center justify-center p-4 z-[60]" style={{ backgroundColor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col" style={s.panel}>
            <div className="px-6 py-4 flex justify-between items-center" style={{ borderBottom: '1px solid var(--color-m-border)', backgroundColor: 'var(--color-m-panel-alt)' }}>
              <h3 className="text-lg font-bold flex items-center gap-2" style={{ color: 'var(--color-m-text)' }}>
                <ShieldIcon size={20} /> 隱私與資料安全聲明
              </h3>
              <button onClick={() => setShowPrivacyModal(false)} className="p-1 rounded-lg transition-colors" style={{ color: 'var(--color-m-muted)' }}>
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto custom-scrollbar text-sm leading-relaxed space-y-4" style={{ color: 'var(--color-m-text)' }}>
              <p>我們極度重視您的個人隱私與資料安全。為了確保您的記憶與日記內容不被未經授權的第三方（包含資料庫管理員）窺探，我們採取了以下措施：</p>
              <div className="p-4 rounded-xl space-y-2" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                <h4 className="font-bold flex items-center gap-2" style={{ color: 'var(--color-m-accent1)' }}>
                  <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: 'var(--color-m-accent1)' }}></span>
                  端到端應用層加密 (E2E Application-Level Encryption)
                </h4>
                <p style={s.muted}>所有您輸入的敏感文字內容，在離開伺服器並寫入資料庫之前，都會被自動轉換為不可讀的加密亂碼。即使資料庫管理員也無法肉眼解讀您的真實資料。</p>
              </div>
              <div className="p-4 rounded-xl space-y-2" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                <h4 className="font-bold flex items-center gap-2" style={{ color: 'var(--color-m-accent2)' }}>
                  <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: 'var(--color-m-accent2)' }}></span>
                  AI 僅作分析用途
                </h4>
                <p style={s.muted}>只有當您進行對話檢索或編譯核心人物時，系統才會短暫解密並傳遞給 AI 分析。所有分析結果僅供您的帳號存取。</p>
              </div>
              <p className="text-xs text-center pt-2" style={s.muted}>感謝您的信任，MemoryAI 致力於提供一個安全可靠的數位大腦環境。</p>
            </div>

            <div className="px-6 py-4 flex justify-end" style={{ borderTop: '1px solid var(--color-m-border)', backgroundColor: 'var(--color-m-panel-alt)' }}>
              <button onClick={() => setShowPrivacyModal(false)} className="px-5 py-2 font-bold rounded-xl transition-colors" style={s.btnPrimary}>
                我了解了
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Backend Offline Modal ===== */}
      {healthStatus === 'Backend is offline' && (
        <div className="fixed inset-0 flex items-center justify-center p-4 z-[70]" style={{ backgroundColor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-2xl w-full max-w-sm sm:max-w-md overflow-hidden flex flex-col" style={{ ...s.panel, border: '1px solid rgba(192,128,128,0.4)' }}>
            <div className="px-6 py-4 flex items-center gap-3" style={{ borderBottom: '1px solid var(--color-m-border)', backgroundColor: 'rgba(192,100,100,0.08)' }}>
              <div className="p-2 rounded-full" style={{ backgroundColor: 'rgba(192,100,100,0.15)' }}>
                <AlertCircle className="w-6 h-6" style={{ color: '#c08080' }} />
              </div>
              <h3 className="text-lg font-bold" style={{ color: 'var(--color-m-text)' }}>大腦核心連線中斷</h3>
            </div>
            <div className="p-6 text-sm leading-relaxed space-y-4" style={{ color: 'var(--color-m-text)' }}>
              <p>我們暫時無法連線至後端伺服器 (Backend Offline)。</p>
              <p style={s.muted}>伺服器可能因為閒置過久而進入了自動休眠狀態，或者正在重新啟動中。</p>
              <div className="p-4 rounded-xl" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                <p className="font-medium mb-1" style={{ color: 'var(--color-m-accent2)' }}>💡 解決方式：</p>
                <p style={s.muted}>目前無法寫入或檢索記憶。請聯絡系統管理員為您喚醒伺服器或進行除錯，以恢復正常功能。</p>
              </div>
            </div>
            <div className="px-6 py-4 flex justify-end" style={{ borderTop: '1px solid var(--color-m-border)' }}>
              <button onClick={() => setHealthStatus('Dismissed')} className="px-5 py-2 rounded-xl transition-colors font-medium" style={{ backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-muted)', border: '1px solid var(--color-m-border)' }}>
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
