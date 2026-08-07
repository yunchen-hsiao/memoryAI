import { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { ArrowLeftRight, Sparkles } from 'lucide-react';
import { emotionColor } from '../lib/emotionColor';

interface PersonEvent {
  date: string;
  topic: string;
  summary: string;
  emotion_score: number | null;
  importance_weight: number | null;
}

interface MonthlyPoint {
  month: string;
  event_count: number;
  avg_score: number;
}

interface KeyMoment extends PersonEvent {
  score_delta: number;
}

interface ComparePerson {
  name: string;
  event_count: number;
  avg_score: number | null;
  avg_importance: number | null;
  monthly_series: MonthlyPoint[];
  key_moments: KeyMoment[];
}

interface OverviewPersonName {
  name: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** 2026-03 -> 26/03 */
function formatMonth(month: string): string {
  const [y, m] = month.split('-');
  return `${y?.slice(2)}/${m}`;
}

/** 把兩人的月度序列合併成同一個時間軸，供雙線圖使用 */
function mergeMonthlySeries(a: MonthlyPoint[], b: MonthlyPoint[]) {
  const months = Array.from(new Set([...a.map(p => p.month), ...b.map(p => p.month)])).sort();
  const aByMonth = new Map(a.map(p => [p.month, p.avg_score]));
  const bByMonth = new Map(b.map(p => [p.month, p.avg_score]));
  return months.map(month => ({
    month,
    a: aByMonth.get(month) ?? null,
    b: bByMonth.get(month) ?? null,
  }));
}

export default function PersonCompare({ token }: { token: string | null }) {
  const [names, setNames] = useState<string[]>([]);
  const [personA, setPersonA] = useState('');
  const [personB, setPersonB] = useState('');
  const [persons, setPersons] = useState<ComparePerson[]>([]);
  const [loading, setLoading] = useState(false);
  const [namesLoading, setNamesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 用人物總覽 API 取得可選的人物清單，跟總覽頁共用同一份「已編譯人物」白名單
  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/person_overview`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(fetched => {
        if (fetched && fetched.success) {
          const fetchedNames = (fetched.persons || []).map((p: OverviewPersonName) => p.name);
          setNames(fetchedNames);
          if (fetchedNames.length >= 2) {
            setPersonA(fetchedNames[0]);
            setPersonB(fetchedNames[1]);
          }
        }
      })
      .catch(err => console.error('Person names fetch error:', err))
      .finally(() => setNamesLoading(false));
  }, [token]);

  useEffect(() => {
    if (!personA || !personB) return;
    if (personA === personB) {
      setError('請選擇兩位不同的人物。');
      setPersons([]);
      return;
    }

    setLoading(true);
    setError(null);
    fetch(
      `${API_BASE}/api/graph/compare?person_a=${encodeURIComponent(personA)}&person_b=${encodeURIComponent(personB)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    )
      .then(res => res.json())
      .then(fetched => {
        if (fetched && fetched.success) {
          setPersons(fetched.persons || []);
        } else {
          setError(fetched?.error || '無法載入對比資料。');
        }
      })
      .catch(err => {
        console.error('Person compare fetch error:', err);
        setError('無法連線至後端以載入人物對比。');
      })
      .finally(() => setLoading(false));
  }, [personA, personB, token]);

  const scoreRange = useMemo(() => {
    const scores = persons.map(p => p.avg_score).filter((s): s is number => s !== null);
    if (scores.length === 0) return { min: 0, max: 100 };
    return { min: Math.min(...scores), max: Math.max(...scores) };
  }, [persons]);

  const mergedSeries = useMemo(() => {
    if (persons.length !== 2) return [];
    return mergeMonthlySeries(persons[0].monthly_series, persons[1].monthly_series);
  }, [persons]);

  if (namesLoading) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        載入人物清單中...
      </p>
    );
  }

  if (names.length < 2) {
    return (
      <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>
        需要至少 2 位已編譯的核心人物才能進行對比。
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 人物選擇器 */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={personA}
          onChange={e => setPersonA(e.target.value)}
          className="rounded-lg px-3 py-1.5 text-sm focus:outline-none"
          style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}
        >
          {names.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        <ArrowLeftRight className="w-4 h-4 shrink-0" style={{ color: 'var(--color-m-muted)' }} />
        <select
          value={personB}
          onChange={e => setPersonB(e.target.value)}
          className="rounded-lg px-3 py-1.5 text-sm focus:outline-none"
          style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}
        >
          {names.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </div>

      {error && (
        <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>{error}</p>
      )}

      {loading && (
        <p className="text-sm italic" style={{ color: 'var(--color-m-muted)' }}>載入對比資料中...</p>
      )}

      {!loading && !error && persons.length === 2 && (
        <>
          {/* 三格統計並排比較 */}
          <div className="grid grid-cols-2 gap-4">
            {persons.map(person => (
              <div key={person.name} className="rounded-xl p-4" style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}>
                <h4 className="text-sm font-semibold mb-3 truncate" style={{ color: 'var(--color-m-text)' }}>{person.name}</h4>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-lg font-semibold" style={{ color: 'var(--color-m-text)' }}>{person.event_count}</div>
                    <div className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>互動次數</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold" style={{ color: emotionColor(person.avg_score, scoreRange.min, scoreRange.max) }}>
                      {person.avg_score ?? '—'}
                    </div>
                    <div className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>平均情緒</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold" style={{ color: 'var(--color-m-text)' }}>{person.avg_importance ?? '—'}</div>
                    <div className="text-[11px]" style={{ color: 'var(--color-m-muted)' }}>平均重要度</div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* 雙人情緒生命週期並排線圖 */}
          {mergedSeries.length >= 2 && (
            <div>
              <h4 className="text-sm font-semibold mb-2" style={{ color: 'var(--color-m-text)' }}>情緒趨勢對比</h4>
              <div className="h-[220px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mergedSeries} margin={{ top: 5, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-m-border)" vertical={false} />
                    <XAxis dataKey="month" tickFormatter={(m: any) => formatMonth(String(m))} stroke="var(--color-m-muted)" fontSize={11} />
                    <YAxis domain={[0, 100]} stroke="var(--color-m-muted)" fontSize={11} width={32} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'var(--color-m-panel-alt)', borderColor: 'var(--color-m-border)', borderRadius: '8px' }}
                      labelFormatter={(m: any) => formatMonth(String(m))}
                    />
                    <Legend formatter={(value: any) => (value === 'a' ? persons[0].name : persons[1].name)} />
                    <Line type="monotone" dataKey="a" name={persons[0].name} stroke="#5cb3a1" strokeWidth={2} dot={{ r: 2 }} connectNulls />
                    <Line type="monotone" dataKey="b" name={persons[1].name} stroke="#8a88cc" strokeWidth={2} dot={{ r: 2 }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* 雙人關鍵時刻並排 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {persons.map(person => (
              <div key={person.name}>
                <h4 className="text-sm font-semibold mb-2 flex items-center gap-1.5" style={{ color: 'var(--color-m-text)' }}>
                  <Sparkles className="w-3.5 h-3.5" style={{ color: 'var(--color-m-accent3)' }} /> {person.name} 的關鍵時刻
                </h4>
                {person.key_moments.length === 0 ? (
                  <p className="text-xs italic" style={{ color: 'var(--color-m-muted)' }}>暫無明顯轉折點。</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {person.key_moments.map((moment, idx) => (
                      <li
                        key={`${moment.date}-${idx}`}
                        className="rounded-lg p-2.5"
                        style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)' }}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium" style={{ color: 'var(--color-m-muted)' }}>
                            {moment.date}{moment.topic ? `｜${moment.topic}` : ''}
                          </span>
                          <span
                            className="text-xs font-semibold shrink-0"
                            style={{ color: moment.score_delta > 0 ? 'var(--color-m-accent2)' : '#c08080' }}
                          >
                            {moment.score_delta > 0 ? '+' : ''}{moment.score_delta}
                          </span>
                        </div>
                        {moment.summary && (
                          <p className="text-xs leading-snug mt-1 break-words" style={{ color: 'var(--color-m-text)' }}>
                            {moment.summary}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
