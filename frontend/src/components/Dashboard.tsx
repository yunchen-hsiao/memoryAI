import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, Brush } from 'recharts';
import { Brain, TrendingUp, PieChart as PieChartIcon, Calendar, Heart, Sparkles, Network } from 'lucide-react';
import MemoryGraph from './MemoryGraph';
import { DashboardIcon } from './Icons';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface DashboardProps {
  token: string | null;
}

export default function Dashboard({ token }: DashboardProps) {
  const [stats, setStats] = useState<{
    emotion_trends: any[], 
    keyword_distribution: any[],
    summary_stats?: { total_days: number, avg_score: number, top_keyword: string },
    entity_analysis?: {
      name: string;
      mentions: number;
      avg_score: number;
      co_keywords: string[];
      latest_events: {date: string, summary: string}[];
    }[]
  }>({ emotion_trends: [], keyword_distribution: [] });
  const [loading, setLoading] = useState(true);
  const [selectedEntityIdx, setSelectedEntityIdx] = useState(0);

  const handleBuildEntities = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/entities/build`, { 
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      const data = await res.json();
      if (data.success) {
        alert('⚡ ' + data.message);
      } else {
        alert('❌ 編譯失敗：' + data.error);
      }
    } catch (err) {
      alert('❌ 網路錯誤：' + err);
    }
  };

  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/stats`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 space-y-4">
        <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center text-2xl animate-spin shadow-[0_0_20px_rgba(52,211,153,0.1)]">
          ⏳
        </div>
        <p>正在載入大腦數據...</p>
      </div>
    );
  }

  const COLORS = ['#7f94a8', '#7a9490', '#8e8fb0', '#9ba8a0', '#8a9099', '#6d8090', '#85a098', '#7c8eaa', '#9698b8'];

  return (
    <div className="h-full flex flex-col gap-6 p-6 overflow-y-auto custom-scrollbar" style={{ backgroundColor: 'var(--color-m-base)', color: 'var(--color-m-text)' }}>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-3 sm:gap-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <DashboardIcon size={28} />
          <h2 className="text-xl sm:text-2xl font-bold text-morandi-gradient whitespace-nowrap">大腦記憶儀表板</h2>
        </div>
        <button
          onClick={handleBuildEntities}
          className="w-full sm:w-auto flex justify-center items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-lg border transition-colors text-xs sm:text-sm font-medium whitespace-nowrap"
          style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-accent3)' }}
        >
          重新編譯核心人物網
        </button>
      </div>

      {/* Summary Stats Row */}
      {stats.summary_stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl p-4 flex items-center gap-4" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
            <div className="p-3 rounded-lg" style={{ backgroundColor: 'rgba(127,148,168,0.15)', color: 'var(--color-m-accent1)' }}>
              <Calendar className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm" style={{ color: 'var(--color-m-muted)' }}>紀錄天數</p>
              <p className="text-2xl font-bold" style={{ color: 'var(--color-m-text)' }}>{stats.summary_stats.total_days} <span className="text-sm font-normal" style={{ color: 'var(--color-m-muted)' }}>天</span></p>
            </div>
          </div>
          <div className="rounded-xl p-4 flex items-center gap-4" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
            <div className="p-3 rounded-lg" style={{ backgroundColor: 'rgba(142,143,176,0.15)', color: 'var(--color-m-accent3)' }}>
              <Heart className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm" style={{ color: 'var(--color-m-muted)' }}>平均心情</p>
              <p className="text-2xl font-bold" style={{ color: 'var(--color-m-text)' }}>{stats.summary_stats.avg_score} <span className="text-sm font-normal" style={{ color: 'var(--color-m-muted)' }}>分</span></p>
            </div>
          </div>
        </div>
      )}

      {/* Phase 5.2 Core Entity Deep Dive */}
      <div className="rounded-2xl p-6 shadow-lg h-auto flex flex-col" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
        <div className="flex items-center gap-2 mb-6" style={{ color: 'var(--color-m-text)' }}>
          <Sparkles className="w-5 h-5" style={{ color: 'var(--color-m-accent3)' }} />
          <h3 className="text-lg font-semibold">核心實體深度分析 (角色看板)</h3>
        </div>
        
        {/* Force Rendering */}
        {!stats.entity_analysis ? (
          <div className="p-4 rounded" style={{ backgroundColor: 'rgba(192,100,100,0.15)', color: '#c09090' }}>
            錯誤：stats.entity_analysis 是 undefined！
          </div>
        ) : stats.entity_analysis.length === 0 ? (
          <div className="p-4 rounded" style={{ backgroundColor: 'rgba(192,160,100,0.15)', color: 'var(--color-m-accent3)' }}>
            警告：stats.entity_analysis 是空陣列！
          </div>
        ) : (
          <div>
            {/* Entity Tabs */}
            <div className="flex flex-wrap gap-3 mb-6">
              {stats.entity_analysis.map((entity, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedEntityIdx(idx)}
                  className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-300"
                  style={selectedEntityIdx === idx
                    ? { background: 'linear-gradient(135deg, var(--color-m-accent1), var(--color-m-accent2))', color: 'white', transform: 'scale(1.05)' }
                    : { backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-muted)', border: '1px solid var(--color-m-border)' }
                  }
                >
                  {entity.name || "未命名"} <span className="ml-1 text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}>{entity.mentions}</span>
                </button>
              ))}
            </div>

            {/* Active Entity Report */}
            {stats.entity_analysis[selectedEntityIdx] && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 rounded-2xl p-6" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                <div className="lg:col-span-1 space-y-8">
                  <div className="p-5 rounded-xl" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2" style={{ color: 'var(--color-m-muted)' }}>
                      <Heart className="w-4 h-4" style={{ color: 'var(--color-m-accent3)' }} />
                      情感影響力
                    </h4>
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-black tracking-tight"
                        style={{ color: stats.entity_analysis[selectedEntityIdx].avg_score >= 60 ? 'var(--color-m-accent2)' : '#c08080' }}
                      >
                        {stats.entity_analysis[selectedEntityIdx].avg_score}
                      </span>
                      <span style={{ color: 'var(--color-m-muted)' }}>分</span>
                    </div>
                  </div>
                  <div className="p-5 rounded-xl" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2" style={{ color: 'var(--color-m-muted)' }}>
                      <Brain className="w-4 h-4" style={{ color: 'var(--color-m-accent1)' }} />
                      共現網路 (常伴隨出現)
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {(stats.entity_analysis[selectedEntityIdx].co_keywords || []).length > 0 ? (
                        stats.entity_analysis[selectedEntityIdx].co_keywords.map((kw, i) => (
                          <span key={i} className="px-3 py-1.5 rounded-lg text-xs font-medium" style={{ backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-accent1)', border: '1px solid var(--color-m-border)' }}>
                            {kw}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>無相關關鍵字</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="lg:col-span-2 p-5 rounded-xl" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
                  <h4 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--color-m-muted)' }}>
                    <Calendar className="w-4 h-4" style={{ color: 'var(--color-m-accent1)' }} />
                    最近互動回放 (包含提及此名字的記憶)
                  </h4>
                  <div className="space-y-4">
                    {(stats.entity_analysis[selectedEntityIdx].latest_events || []).length > 0 ? (
                      stats.entity_analysis[selectedEntityIdx].latest_events.map((evt, i) => (
                        <div key={i} className="rounded-xl p-4 transition-colors shadow-sm" style={{ backgroundColor: 'var(--color-m-panel-alt)', borderLeft: '3px solid var(--color-m-accent1)' }}>
                          <div className="text-xs font-bold mb-2 flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded" style={{ backgroundColor: 'rgba(127,148,168,0.15)', color: 'var(--color-m-accent1)' }}>{evt.date}</span>
                          </div>
                          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-m-text)' }}>{evt.summary}</p>
                        </div>
                      ))
                    ) : (
                      <div className="flex flex-col items-center justify-center py-8" style={{ color: 'var(--color-m-muted)' }}>
                        <p className="italic">無最近記憶</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Memory Graph Card */}
      <div className="rounded-2xl p-6 shadow-lg flex flex-col" style={{ minHeight: '600px', backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
        <div className="flex items-center gap-2 mb-4" style={{ color: 'var(--color-m-text)' }}>
          <Network className="w-5 h-5" style={{ color: 'var(--color-m-accent2)' }} />
          <h3 className="text-lg font-semibold">記憶星系網路圖 (動態關聯)</h3>
        </div>
        <div className="flex-1 rounded-xl overflow-hidden relative">
          <MemoryGraph token={token} />
        </div>
      </div>

      <div className="flex flex-col gap-6">
        <div className="rounded-2xl p-6 shadow-lg" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
          <div className="flex items-center gap-2 mb-6" style={{ color: 'var(--color-m-text)' }}>
            <TrendingUp className="w-5 h-5" style={{ color: 'var(--color-m-accent2)' }} />
            <h3 className="text-lg font-semibold">情緒時光機 (最近情緒起伏)</h3>
          </div>
          <div className="h-[350px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats.emotion_trends} margin={{ top: 5, right: 20, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-m-border)" vertical={false} />
                <XAxis dataKey="date" stroke="var(--color-m-muted)" fontSize={12} tickMargin={10} />
                <YAxis stroke="var(--color-m-muted)" fontSize={12} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--color-m-panel-alt)', borderColor: 'var(--color-m-border)', borderRadius: '8px', color: 'var(--color-m-text)' }}
                  itemStyle={{ color: 'var(--color-m-accent2)' }}
                  labelStyle={{ color: 'var(--color-m-text)', fontWeight: 'bold', marginBottom: '4px' }}
                  formatter={(value: any, _name: any, props: any) => [
                    `${value} 分 (主要話題: ${props.payload.main_topic})`, '情緒分數'
                  ]}
                />
                <Line type="monotone" dataKey="score" stroke="var(--color-m-accent1)" strokeWidth={2.5} dot={false} activeDot={{ r: 5, fill: 'var(--color-m-accent2)', stroke: 'var(--color-m-panel)', strokeWidth: 2 }} />
                <Brush dataKey="date" height={28} stroke="var(--color-m-border)" fill="var(--color-m-panel-alt)" travellerWidth={8} tickFormatter={() => ''} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl p-6 shadow-lg" style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}>
          <div className="flex items-center gap-2 mb-6" style={{ color: 'var(--color-m-text)' }}>
            <PieChartIcon className="w-5 h-5" style={{ color: 'var(--color-m-accent1)' }} />
            <h3 className="text-lg font-semibold">記憶雷達 (最常出現的關鍵字)</h3>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.keyword_distribution} layout="vertical" margin={{ left: 40, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-m-border)" horizontal={true} vertical={false} />
                <XAxis type="number" stroke="var(--color-m-muted)" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="var(--color-m-muted)" fontSize={12} width={80} />
                <Tooltip cursor={{ fill: 'var(--color-m-hover)' }} contentStyle={{ backgroundColor: 'var(--color-m-panel-alt)', borderColor: 'var(--color-m-border)', borderRadius: '8px' }} itemStyle={{ color: 'var(--color-m-accent2)' }} formatter={(value: any) => [`${value} 次`, '出現次數']} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {(stats.keyword_distribution || []).map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
