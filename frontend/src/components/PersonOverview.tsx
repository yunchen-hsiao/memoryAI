import { useEffect, useMemo, useState } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { LayoutGrid, Table2 } from 'lucide-react';
import { emotionColor } from '../lib/emotionColor';

interface OverviewPerson {
  name: string;
  total_count: number;
  avg_score: number | null;
  first_date: string | null;
  last_date: string | null;
  trend_direction: 'up' | 'down' | 'flat' | 'unknown';
  trend_label: string;
}

interface OverviewData {
  persons: OverviewPerson[];
  message?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type ViewMode = 'quadrant' | 'table';

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

  // 情緒色階範圍取自當前資料，讓少數幾位人物之間的差異能被看見
  const scoreRange = useMemo(() => {
    const scores = data.persons
      .map(p => p.avg_score)
      .filter((s): s is number => s !== null && s !== undefined);
    if (scores.length === 0) return { min: 0, max: 100 };
    return { min: Math.min(...scores), max: Math.max(...scores) };
  }, [data.persons]);

  // ScatterChart 需要數字座標；沒有情緒分數的人物不畫進象限圖（表格仍會顯示）
  const scatterData = useMemo(
    () =>
      data.persons
        .filter(p => p.avg_score !== null)
        .map(p => ({ ...p, avg_score: p.avg_score as number })),
    [data.persons]
  );

  if (loading) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        載入人物總覽中...
      </p>
    );
  }

  if (error) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        {error}
      </p>
    );
  }

  if (data.persons.length === 0) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        {data.message || '目前沒有可分析的人物資料。'}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 象限圖 / 表格切換 */}
      <div className="flex gap-2">
        <button
          onClick={() => setViewMode('quadrant')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          style={viewMode === 'quadrant'
            ? { background: 'linear-gradient(135deg, var(--color-m-accent1), var(--color-m-accent2))', color: 'white' }
            : { backgroundColor: 'var(--color-m-panel-alt)', color: 'var(--color-m-muted)', border: '1px solid var(--color-m-border)' }
          }
        >
          <LayoutGrid className="w-3.5 h-3.5" /> 象限圖
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
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-m-border)" />
              <XAxis
                type="number"
                dataKey="total_count"
                name="互動次數"
                stroke="var(--color-m-muted)"
                fontSize={12}
                label={{ value: '互動次數 →', position: 'insideBottomRight', offset: -5, fill: 'var(--color-m-muted)', fontSize: 12 }}
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
                  const person = payload[0].payload as OverviewPerson;
                  return (
                    <div
                      className="rounded-lg px-3 py-2 text-xs"
                      style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}
                    >
                      <p className="font-semibold mb-1">{person.name}</p>
                      <p style={{ color: 'var(--color-m-muted)' }}>互動 {person.total_count} 次｜平均情緒 {person.avg_score}</p>
                      <p style={{ color: 'var(--color-m-muted)' }}>趨勢：{person.trend_label}</p>
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
                    <text x={cx} y={cy - 13} textAnchor="middle" fontSize={11} fill="var(--color-m-text)">
                      {payload.name}
                    </text>
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
                  <td className="text-sm font-medium px-3 py-2 rounded-l-lg" style={{ color: 'var(--color-m-text)' }}>
                    {person.name}
                  </td>
                  <td className="text-xs px-3 py-2" style={{ color: 'var(--color-m-muted)' }}>
                    {person.first_date || '—'}
                  </td>
                  <td className="text-xs px-3 py-2" style={{ color: 'var(--color-m-muted)' }}>
                    {person.last_date || '—'}
                  </td>
                  <td className="text-sm text-right px-3 py-2" style={{ color: 'var(--color-m-text)' }}>
                    {person.total_count} 次
                  </td>
                  <td
                    className="text-sm text-right font-semibold px-3 py-2"
                    style={{ color: emotionColor(person.avg_score, scoreRange.min, scoreRange.max) }}
                  >
                    {person.avg_score ?? '—'}
                  </td>
                  <td className="text-sm text-center px-3 py-2 rounded-r-lg" style={{ color: 'var(--color-m-text)' }}>
                    {person.trend_label}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>
        {viewMode === 'quadrant'
          ? '象限圖：X 軸是互動次數，Y 軸是平均情緒。右上角＝常聯絡且開心，左上角＝不常聯絡但每次都開心，右下角＝常聯絡但讓你不開心。'
          : '趨勢是比較該人物「前半段」與「後半段」互動的平均情緒：↑ 升溫、↓ 降溫、→ 持平（資料太少時顯示「資料不足」）。'}
      </p>
    </div>
  );
}
