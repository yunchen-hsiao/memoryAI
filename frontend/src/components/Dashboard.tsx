import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, Brush } from 'recharts';
import { Brain, TrendingUp, PieChart as PieChartIcon, Calendar, Heart, User, Sparkles, Network } from 'lucide-react';
import MemoryGraph from './MemoryGraph';

export default function Dashboard() {
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
      const res = await fetch('http://localhost:8000/api/entities/build', { method: 'POST' });
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
    fetch('http://localhost:8000/api/dashboard/stats')
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

  const COLORS = ['#34d399', '#10b981', '#059669', '#047857', '#065f46', '#064e3b', '#6ee7b7', '#a7f3d0', '#d1fae5'];

  return (
    <div className="h-full flex flex-col gap-6 p-6 overflow-y-auto">
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-3">
          <Brain className="w-8 h-8 text-emerald-400" />
          <h2 className="text-2xl font-bold bg-gradient-to-r from-emerald-400 to-teal-500 bg-clip-text text-transparent">大腦記憶儀表板</h2>
        </div>
        <button 
          onClick={handleBuildEntities}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded-lg border border-amber-500/30 transition-colors shadow-[0_0_10px_rgba(251,191,36,0.1)] text-sm font-medium"
        >
          <span>⚡</span> 重新編譯核心人物網
        </button>
      </div>

      {/* Summary Stats Row */}
      {stats.summary_stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 flex items-center gap-4">
            <div className="p-3 bg-emerald-500/20 rounded-lg text-emerald-400">
              <Calendar className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm text-slate-400">紀錄天數</p>
              <p className="text-2xl font-bold text-slate-100">{stats.summary_stats.total_days} <span className="text-sm font-normal text-slate-500">天</span></p>
            </div>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 flex items-center gap-4">
            <div className="p-3 bg-pink-500/20 rounded-lg text-pink-400">
              <Heart className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm text-slate-400">平均心情</p>
              <p className="text-2xl font-bold text-slate-100">{stats.summary_stats.avg_score} <span className="text-sm font-normal text-slate-500">分</span></p>
            </div>
          </div>
        </div>
      )}

      {/* Phase 5.2 Core Entity Deep Dive */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 shadow-lg h-auto flex flex-col">
        
        <div className="flex items-center gap-2 mb-6 text-slate-200">
          <Sparkles className="w-5 h-5 text-emerald-400" />
          <h3 className="text-lg font-semibold">核心實體深度分析 (角色看板)</h3>
        </div>
        
        {/* Force Rendering */}
        {!stats.entity_analysis ? (
          <div className="p-4 bg-red-500/20 text-red-300 rounded">
            錯誤：stats.entity_analysis 是 undefined！
          </div>
        ) : stats.entity_analysis.length === 0 ? (
          <div className="p-4 bg-yellow-500/20 text-yellow-300 rounded">
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
                  className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-300 ${
                    selectedEntityIdx === idx
                      ? 'bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-950 shadow-[0_0_20px_rgba(16,185,129,0.4)] scale-105'
                      : 'bg-slate-900/80 text-slate-400 hover:text-emerald-300 border border-slate-700'
                  }`}
                >
                  {entity.name || "未命名"} <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-black/20">{entity.mentions}</span>
                </button>
              ))}
            </div>

            {/* Active Entity Report */}
            {stats.entity_analysis[selectedEntityIdx] && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 bg-slate-900/60 rounded-2xl p-6 border border-slate-700/50 shadow-inner">
                
                {/* Left Column: Emotion & Co-occurrences */}
                <div className="lg:col-span-1 space-y-8">
                  <div className="bg-slate-800/40 p-5 rounded-xl border border-slate-700/30">
                    <h4 className="text-slate-400 text-sm font-medium mb-3 flex items-center gap-2">
                      <Heart className="w-4 h-4 text-pink-400" />
                      情感影響力
                    </h4>
                    <div className="flex items-baseline gap-2">
                      <span className={`text-4xl font-black tracking-tight ${
                        stats.entity_analysis[selectedEntityIdx].avg_score >= 60 
                          ? 'text-emerald-400' 
                          : 'text-rose-400'
                      }`}>
                        {stats.entity_analysis[selectedEntityIdx].avg_score}
                      </span>
                      <span className="text-slate-500 font-medium">分</span>
                    </div>
                  </div>

                  <div className="bg-slate-800/40 p-5 rounded-xl border border-slate-700/30">
                    <h4 className="text-slate-400 text-sm font-medium mb-3 flex items-center gap-2">
                      <Brain className="w-4 h-4 text-purple-400" />
                      共現網路 (常伴隨出現)
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {(stats.entity_analysis[selectedEntityIdx].co_keywords || []).length > 0 ? (
                        stats.entity_analysis[selectedEntityIdx].co_keywords.map((kw, i) => (
                          <span key={i} className="px-3 py-1.5 bg-slate-700/50 text-emerald-100 rounded-lg text-xs font-medium border border-emerald-500/20 shadow-sm">
                            {kw}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-500 text-sm italic">無相關關鍵字</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right Column: Latest Events */}
                <div className="lg:col-span-2 bg-slate-800/40 p-5 rounded-xl border border-slate-700/30">
                  <h4 className="text-slate-400 text-sm font-medium mb-4 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-blue-400" />
                    最近互動回放 (包含提及此名字的記憶)
                  </h4>
                  <div className="space-y-4">
                    {(stats.entity_analysis[selectedEntityIdx].latest_events || []).length > 0 ? (
                      stats.entity_analysis[selectedEntityIdx].latest_events.map((evt, i) => (
                        <div key={i} className="group bg-slate-900/50 rounded-xl p-4 border-l-4 border-emerald-500 transition-colors shadow-sm">
                          <div className="text-xs font-bold text-emerald-400/80 mb-2 flex items-center gap-2">
                            <span className="bg-emerald-500/10 px-2 py-0.5 rounded text-emerald-400">{evt.date}</span>
                          </div>
                          <p className="text-sm text-slate-300 leading-relaxed">{evt.summary}</p>
                        </div>
                      ))
                    ) : (
                      <div className="flex flex-col items-center justify-center py-8 text-slate-500">
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
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 shadow-lg backdrop-blur-sm flex flex-col" style={{ minHeight: '600px' }}>
        <div className="flex items-center gap-2 mb-4 text-slate-200">
          <Network className="w-5 h-5 text-emerald-400" />
          <h3 className="text-lg font-semibold">記憶星系網路圖 (動態關聯)</h3>
        </div>
        <div className="flex-1 rounded-xl overflow-hidden relative">
          <MemoryGraph />
        </div>
      </div>

      <div className="flex flex-col gap-6">
        {/* Emotion Trend Card */}
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 shadow-lg backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-6 text-slate-200">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h3 className="text-lg font-semibold">情緒時光機 (最近情緒起伏)</h3>
          </div>
          <div className="h-[350px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats.emotion_trends} margin={{ top: 5, right: 20, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} tickMargin={10} />
                <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 100]} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                  itemStyle={{ color: '#34d399' }}
                  labelStyle={{ color: '#f8fafc', fontWeight: 'bold', marginBottom: '4px' }}
                  formatter={(value: any, name: any, props: any) => [
                    `${value} 分 (主要話題: ${props.payload.main_topic})`, '情緒分數'
                  ]}
                />
                <Line type="monotone" dataKey="score" stroke="#34d399" strokeWidth={3} dot={false} activeDot={{ r: 6, fill: '#059669', stroke: '#fff', strokeWidth: 2 }} />
                <Brush dataKey="date" height={30} stroke="#10b981" fill="#0f172a" travellerWidth={10} tickFormatter={() => ''} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Keyword Distribution Card */}
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 shadow-lg backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-6 text-slate-200">
            <PieChartIcon className="w-5 h-5 text-emerald-400" />
            <h3 className="text-lg font-semibold">記憶雷達 (最常出現的關鍵字)</h3>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.keyword_distribution} layout="vertical" margin={{ left: 40, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={true} vertical={false} />
                <XAxis type="number" stroke="#94a3b8" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#94a3b8" fontSize={12} width={80} />
                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }} itemStyle={{ color: '#34d399' }} formatter={(value: any) => [`${value} 次`, '出現次數']} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {stats.keyword_distribution.map((entry, index) => (
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
