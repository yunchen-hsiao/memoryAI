import { useEffect, useMemo, useState } from 'react';

interface HeatmapCell {
  month: string;
  count: number;
  avg_score: number;
}

interface HeatmapPerson {
  name: string;
  total_count: number;
  avg_score: number | null;
  cells: HeatmapCell[];
}

interface HeatmapData {
  months: string[];
  persons: HeatmapPerson[];
  message?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * 依情緒分數取得格子顏色（冷色=偏低，暖色=偏高）。
 * 色階範圍由實際資料決定，避免所有格子看起來同一個顏色。
 */
function cellColor(score: number, min: number, max: number): string {
  const range = max - min;
  const t = range < 0.5 ? 0.5 : (score - min) / range;
  const cold = [129, 140, 248]; // indigo-400
  const warm = [251, 191, 36]; // amber-400
  const rgb = cold.map((c, i) => Math.round(c + (warm[i] - c) * t));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

/** 2026-03 -> 26/03 */
function formatMonth(month: string): string {
  const [y, m] = month.split('-');
  return `${y?.slice(2)}/${m}`;
}

export default function RelationshipHeatmap({ token }: { token: string | null }) {
  const [data, setData] = useState<HeatmapData>({ months: [], persons: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/relationship_heatmap`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(fetched => {
        if (fetched && fetched.success) {
          setData({
            months: fetched.months || [],
            persons: fetched.persons || [],
            message: fetched.message
          });
        } else {
          setError(fetched?.error || '無法載入關係熱力圖資料。');
        }
      })
      .catch(err => {
        console.error('Heatmap fetch error:', err);
        setError('無法連線至後端以載入關係熱力圖。');
      })
      .finally(() => setLoading(false));
  }, [token]);

  // 色階範圍取自所有格子的實際分數
  const scoreRange = useMemo(() => {
    const scores = data.persons.flatMap(p => p.cells.map(c => c.avg_score));
    if (scores.length === 0) return { min: 0, max: 100 };
    return { min: Math.min(...scores), max: Math.max(...scores) };
  }, [data.persons]);

  // 以人物 + 月份建立快速查表，方便渲染時對齊欄位
  const cellLookup = useMemo(() => {
    const map = new Map<string, HeatmapCell>();
    data.persons.forEach(p => {
      p.cells.forEach(c => map.set(`${p.name}|${c.month}`, c));
    });
    return map;
  }, [data.persons]);

  if (loading) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        載入關係熱力圖中...
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
      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: '3px' }}>
          <caption className="sr-only">
            每位人物在各月份的平均情緒分數與互動次數熱力圖
          </caption>
          <thead>
            <tr>
              <th
                scope="col"
                className="text-left text-xs font-medium sticky left-0 pr-3"
                style={{ color: 'var(--color-m-muted)', backgroundColor: 'var(--color-m-panel)' }}
              >
                人物
              </th>
              {data.months.map(month => (
                <th
                  key={month}
                  scope="col"
                  className="text-xs font-medium px-1"
                  style={{ color: 'var(--color-m-muted)', minWidth: '46px' }}
                >
                  {formatMonth(month)}
                </th>
              ))}
              <th
                scope="col"
                className="text-xs font-medium pl-3"
                style={{ color: 'var(--color-m-muted)' }}
              >
                總計
              </th>
            </tr>
          </thead>
          <tbody>
            {data.persons.map(person => (
              <tr key={person.name}>
                <th
                  scope="row"
                  className="text-left text-sm font-medium whitespace-nowrap sticky left-0 pr-3"
                  style={{ color: 'var(--color-m-text)', backgroundColor: 'var(--color-m-panel)' }}
                >
                  {person.name}
                </th>
                {data.months.map(month => {
                  const cell = cellLookup.get(`${person.name}|${month}`);
                  if (!cell) {
                    return (
                      <td
                        key={month}
                        className="rounded-md"
                        style={{
                          height: '34px',
                          backgroundColor: 'var(--color-m-panel-alt)',
                          opacity: 0.4
                        }}
                        title={`${person.name}｜${month}：沒有互動記錄`}
                      >
                        <span className="sr-only">
                          {person.name} {month} 沒有互動記錄
                        </span>
                      </td>
                    );
                  }
                  return (
                    <td
                      key={month}
                      className="rounded-md text-center text-[11px] font-semibold"
                      style={{
                        height: '34px',
                        backgroundColor: cellColor(cell.avg_score, scoreRange.min, scoreRange.max),
                        color: 'rgba(15, 18, 22, 0.85)'
                      }}
                      title={`${person.name}｜${month}：平均情緒 ${cell.avg_score}，互動 ${cell.count} 次`}
                    >
                      {cell.count}
                      <span className="sr-only">
                        {person.name} {month} 平均情緒 {cell.avg_score} 分，互動 {cell.count} 次
                      </span>
                    </td>
                  );
                })}
                <td
                  className="text-center text-xs pl-3 whitespace-nowrap"
                  style={{ color: 'var(--color-m-muted)' }}
                >
                  {person.total_count} 次
                  {person.avg_score !== null && (
                    <span style={{ color: 'var(--color-m-text)' }}>｜{person.avg_score}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 圖例 */}
      <div className="flex flex-wrap items-center gap-4 text-xs" style={{ color: 'var(--color-m-muted)' }}>
        <div className="flex items-center gap-2">
          <span>情緒 {scoreRange.min}</span>
          <div
            className="h-2.5 w-28 rounded-full"
            style={{
              background: 'linear-gradient(to right, rgb(129,140,248), rgb(251,191,36))'
            }}
          />
          <span>{scoreRange.max}</span>
        </div>
        <span>格子中的數字＝該月互動次數</span>
        <div className="flex items-center gap-2">
          <div
            className="w-4 h-3 rounded"
            style={{ backgroundColor: 'var(--color-m-panel-alt)', opacity: 0.4 }}
          />
          <span>該月無互動</span>
        </div>
      </div>
    </div>
  );
}
