import { useEffect, useMemo, useState } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { LayoutGrid, MessageCircle, Smile, Table2, TrendingDown, TrendingUp } from 'lucide-react';
import { emotionColor } from '../lib/emotionColor';

interface OverviewPerson {
  name: string;
  total_count: number;
  avg_score: number | null;
  first_date: string | null;
  last_date: string | null;
  trend_direction: 'up' | 'down' | 'flat' | 'unknown';
  trend_label: string;
  trend_delta: number | null;
}

interface OverviewData {
  persons: OverviewPerson[];
  message?: string;
}

interface ScatterPerson extends Omit<OverviewPerson, 'avg_score'> {
  avg_score: number;
  frequency_position: number;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type ViewMode = 'quadrant' | 'table';

// 對數座標保留「互動次數的倍數差」：10 → 100 的距離會和 1 → 10 相近，
// 避免一位高頻人物把所有低頻人物壓在圖表左側。
const compressFrequency = (count: number) => Math.log10(Math.max(0, count) + 1);
const formatFrequencyTick = (position: number) => {
  const count = Math.max(0, Math.round(10 ** position - 1));
  return count >= 1000 ? `${(count / 1000).toFixed(1).replace('.0', '')}k` : String(count);
};
const formatTrendDelta = (delta: number) => `${delta > 0 ? '+' : ''}${delta.toFixed(1)} 分`;

export default function PersonOverview({ token }: { token: string | null }) {
  const [data, setData] = useState<OverviewData>({ persons: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('quadrant');

  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/person_overview`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(fetched => {
        if (fetched && fetched.success) {
          setData({ persons: fetched.persons || [], message: fetched.message });
        } else {
          setError(fetched?.error || '無法載入人物總覽資料。');
        }
      })
      .catch(err => {
        console.error('Person overview fetch error:', err);
        setError('無法連線至後端以載入人物總覽。');
      })
      .finally(() => setLoading(false));
  }, [token]);

  const scoreRange = useMemo(() => {
    const scores = data.persons
      .map(person => person.avg_score)
      .filter((score): score is number => score !== null && score !== undefined);
    if (scores.length === 0) return { min: 0, max: 100 };
    return { min: Math.min(...scores), max: Math.max(...scores) };
  }, [data.persons]);

  // ScatterChart 需要數字座標；沒有情緒分數的人物仍會保留在洞察與表格裡。
  const scatterData = useMemo<ScatterPerson[]>(
    () => data.persons
      .filter(person => person.avg_score !== null)
      .map(person => ({
        ...person,
        avg_score: person.avg_score as number,
        frequency_position: compressFrequency(person.total_count),
      })),
    [data.persons]
  );

  const frequencyDomain = useMemo<[number, number]>(() => {
    if (scatterData.length === 0) return [0, 1];
    const positions = scatterData.map(person => person.frequency_position);
    const min = Math.min(...positions);
    const max = Math.max(...positions);
    if (min === max) return [Math.max(0, min - 0.25), min + 0.25];
    const padding = (max - min) * 0.12;
    return [Math.max(0, min - padding), max + padding];
  }, [scatterData]);

  const insights = useMemo(() => {
    const orderedByFrequency = [...data.persons].sort((a, b) => b.total_count - a.total_count);
    const orderedByScore = data.persons
      .filter((person): person is OverviewPerson & { avg_score: number } => person.avg_score !== null)
      .sort((a, b) => b.avg_score - a.avg_score);
    const warming = data.persons
      .filter((person): person is OverviewPerson & { trend_delta: number } => person.trend_direction === 'up' && person.trend_delta !== null)
      .sort((a, b) => b.trend_delta - a.trend_delta)[0];
    const cooling = data.persons
      .filter((person): person is OverviewPerson & { trend_delta: number } => person.trend_direction === 'down' && person.trend_delta !== null)
      .sort((a, b) => a.trend_delta - b.trend_delta)[0];

    return {
      mostFrequent: orderedByFrequency[0],
      happiest: orderedByScore[0],
      warming,
      cooling,
    };
  }, [data.persons]);

  if (loading) {
    return <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>載入人物總覽中...</p>;
  }

  if (error) {
    return <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>{error}</p>;
  }

  if (data.persons.length === 0) {
    return <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>{data.message || '目前沒有可分析的人物資料。'}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="人物關係洞察">
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-m-text)' }}>關係洞察</h3>
          <span className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>以互動紀錄的情緒分數推估</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2.5">
          <div className="rounded-xl p-3" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
            <MessageCircle className="w-4 h-4 mb-2" style={{ color: 'var(--color-m-accent1)' }} />
            <p className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>最常出現的人</p>
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--color-m-text)' }}>{insights.mostFrequent?.name || '—'}</p>
            <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>{insights.mostFrequent ? `共 ${insights.mostFrequent.total_count} 次互動` : '尚無資料'}</p>
          </div>
          <div className="rounded-xl p-3" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
            <Smile className="w-4 h-4 mb-2" style={{ color: 'var(--color-m-accent2)' }} />
            <p className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>平均情緒最高</p>
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--color-m-text)' }}>{insights.happiest?.name || '—'}</p>
            <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>{insights.happiest ? `平均 ${insights.happiest.avg_score} 分` : '尚無可比較分數'}</p>
          </div>
          <div className="rounded-xl p-3" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
            <TrendingUp className="w-4 h-4 mb-2" style={{ color: 'var(--color-m-accent2)' }} />
            <p className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>最明顯升溫</p>
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--color-m-text)' }}>{insights.warming?.name || '暫無'}</p>
            <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>{insights.warming ? `前後段情緒 ${formatTrendDelta(insights.warming.trend_delta)}` : '尚未有足夠差異'}</p>
          </div>
          <div className="rounded-xl p-3" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
            <TrendingDown className="w-4 h-4 mb-2" style={{ color: '#c08080' }} />
            <p className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>最明顯降溫</p>
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--color-m-text)' }}>{insights.cooling?.name || '暫無'}</p>
            <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>{insights.cooling ? `前後段情緒 ${formatTrendDelta(insights.cooling.trend_delta)}` : '尚未有足夠差異'}</p>
          </div>
        </div>
      </section>

      <div className="flex gap-2">
        <button
          onClick={() => setViewMode('quadrant')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          style={viewMode === 'quadrant'
            ? { background: 'linear-gradient(135deg, var(--color-m-accent1), var(--color-m-accent2))', color: 'white' }
            : { backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-muted)', border: '1px solid var(--color-m-border)' }
          }
        >
          <LayoutGrid className="w-3.5 h-3.5" /> 關係分布圖
        </button>
        <button
          onClick={() => setViewMode('table')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          style={viewMode === 'table'
            ? { background: 'linear-gradient(135deg, var(--color-m-accent1), var(--color-m-accent2))', color: 'white' }
            : { backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-muted)', border: '1px solid var(--color-m-border)' }
          }
        >
          <Table2 className="w-3.5 h-3.5" /> 總覽表
        </button>
      </div>

      {viewMode === 'quadrant' ? (
        <div className="h-[360px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 14, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-m-border)" />
              <XAxis
                type="number"
                dataKey="frequency_position"
                name="互動次數（壓縮刻度）"
                domain={frequencyDomain}
                tickFormatter={formatFrequencyTick}
                stroke="var(--color-m-muted)"
                fontSize={12}
                label={{ value: '互動次數（壓縮刻度）→', position: 'insideBottomRight', offset: -5, fill: 'var(--color-m-muted)', fontSize: 12 }}
              />
              <YAxis
                type="number"
                dataKey="avg_score"
                name="平均情緒"
                domain={[0, 100]}
                stroke="var(--color-m-muted)"
                fontSize={12}
                label={{ value: '平均情緒 →', angle: -90, position: 'insideLeft', fill: 'var(--color-m-muted)', fontSize: 12 }}
              />
              <ZAxis type="number" range={[80, 220]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (!active || !payload || payload.length === 0) return null;
                  const person = payload[0].payload as ScatterPerson;
                  return (
                    <div className="rounded-lg px-3 py-2 text-xs" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}>
                      <p className="font-semibold mb-1">{person.name}</p>
                      <p style={{ color: 'var(--color-m-muted)' }}>互動 {person.total_count} 次｜平均情緒 {person.avg_score}</p>
                      <p style={{ color: 'var(--color-m-muted)' }}>趨勢：{person.trend_label}{person.trend_delta !== null ? `（${formatTrendDelta(person.trend_delta)}）` : ''}</p>
                    </div>
                  );
                }}
              />
              <Scatter data={scatterData} shape={(props: any) => {
                const { cx, cy, payload } = props;
                const color = emotionColor(payload.avg_score, scoreRange.min, scoreRange.max);
                return (
                  <g>
                    <circle cx={cx} cy={cy} r={9} fill={color} fillOpacity={0.85} stroke="rgba(255,255,255,0.4)" strokeWidth={1} />
                    <text x={cx} y={cy - 13} textAnchor="middle" fontSize={11} fill="var(--color-m-text)">{payload.name}</text>
                  </g>
                );
              }} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate" style={{ borderSpacing: '0 6px' }}>
            <caption className="sr-only">每位人物的互動次數、平均情緒與趨勢方向總覽表</caption>
            <thead>
              <tr>
                <th scope="col" className="text-left text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>人物</th>
                <th scope="col" className="text-left text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>首次出現</th>
                <th scope="col" className="text-left text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>最近出現</th>
                <th scope="col" className="text-right text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>總互動次數</th>
                <th scope="col" className="text-right text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>平均情緒</th>
                <th scope="col" className="text-center text-xs font-medium px-3" style={{ color: 'var(--color-m-muted)' }}>趨勢</th>
              </tr>
            </thead>
            <tbody>
              {data.persons.map(person => (
                <tr key={person.name} style={{ backgroundColor: 'var(--color-m-panel-alt)' }}>
                  <td className="text-sm font-medium px-3 py-2 rounded-l-lg" style={{ color: 'var(--color-m-text)' }}>{person.name}</td>
                  <td className="text-xs px-3 py-2" style={{ color: 'var(--color-m-muted)' }}>{person.first_date || '—'}</td>
                  <td className="text-xs px-3 py-2" style={{ color: 'var(--color-m-muted)' }}>{person.last_date || '—'}</td>
                  <td className="text-sm text-right px-3 py-2" style={{ color: 'var(--color-m-text)' }}>{person.total_count} 次</td>
                  <td className="text-sm text-right font-semibold px-3 py-2" style={{ color: emotionColor(person.avg_score, scoreRange.min, scoreRange.max) }}>{person.avg_score ?? '—'}</td>
                  <td className="text-sm text-center px-3 py-2 rounded-r-lg" style={{ color: 'var(--color-m-text)' }}>{person.trend_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>
        {viewMode === 'quadrant'
          ? '分布圖：X 軸使用對數壓縮，讓 10～50 次互動的人物不會被 400 次以上的人物擠在一起；提示框與表格仍顯示原始次數。右上角代表高頻且正向。'
          : '趨勢幅度比較該人物前半段與後半段的平均情緒；差距小於 5 分時會歸為持平，資料少於兩筆則顯示資料不足。'}
      </p>
    </div>
  );
}
