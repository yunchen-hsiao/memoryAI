import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { X } from 'lucide-react';
import { emotionColor, EMOTION_GRADIENT } from '../lib/emotionColor';

interface PersonNode {
  id: string;
  label: string;
  size: number;
  event_count: number;
  avg_score: number | null;
  avg_importance: number | null;
  first_date: string | null;
  last_date: string | null;
  description: string;
  relationship: string;
  // d3-force 執行時會補上的座標
  x?: number;
  y?: number;
}

interface PersonLink {
  source: string | PersonNode;
  target: string | PersonNode;
  weight: number;
}

interface GraphData {
  nodes: PersonNode[];
  links: PersonLink[];
}

interface PersonEvent {
  date: string;
  topic: string;
  summary: string;
  emotion_score: number | null;
  importance_weight: number | null;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function MemoryGraph({ token }: { token: string | null }) {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [selectedPerson, setSelectedPerson] = useState<PersonNode | null>(null);
  const [personEvents, setPersonEvents] = useState<PersonEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/graph/persons`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(fetched => {
        if (fetched && fetched.success) {
          setData({ nodes: fetched.nodes || [], links: fetched.links || [] });
          setNotice(fetched.message || null);
        } else {
          console.error('Person graph fetch invalid data:', fetched);
          setNotice(fetched?.error || '無法載入人物關係圖。');
        }
      })
      .catch(err => {
        console.error('Person graph fetch error:', err);
        setNotice('無法連線至後端以載入人物關係圖。');
      });
  }, [token]);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // 情緒色階的範圍取自當前資料，讓少數幾位人物之間的差異能被看見
  const scoreRange = useMemo(() => {
    const scores = data.nodes
      .map(n => n.avg_score)
      .filter((s): s is number => s !== null && s !== undefined);
    if (scores.length === 0) return { min: 0, max: 100 };
    return { min: Math.min(...scores), max: Math.max(...scores) };
  }, [data.nodes]);

  // 節點半徑依互動次數縮放。互動次數落差極大（例如 456 vs 12），
  // 用 sqrt 壓縮，避免最大的節點吃掉整個畫面。
  const radiusOf = useCallback((node: PersonNode) => {
    const count = node.event_count || 1;
    return 10 + Math.sqrt(count) * 1.1;
  }, []);

  const linkWeightRange = useMemo(() => {
    const weights = data.links.map(l => l.weight || 1);
    if (weights.length === 0) return { min: 1, max: 1 };
    return { min: Math.min(...weights), max: Math.max(...weights) };
  }, [data.links]);

  const renderNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (node.x === undefined || node.y === undefined) return;

      const radius = radiusOf(node);
      const color = emotionColor(node.avg_score, scoreRange.min, scoreRange.max);
      const isSelected = selectedPerson?.id === node.id;

      ctx.beginPath();
      ctx.shadowColor = color;
      ctx.shadowBlur = isSelected ? 28 : 14;
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.shadowBlur = 0;

      if (isSelected) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI, false);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }

      // 人物名稱
      const fontSize = 13 / globalScale;
      ctx.font = `600 ${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
      ctx.fillText(node.label, node.x, node.y + radius + fontSize + 2);

      // 互動次數與平均情緒（縮太小時隱藏，避免畫面雜亂）
      if (globalScale > 0.7) {
        const metaSize = 10 / globalScale;
        ctx.font = `${metaSize}px Sans-Serif`;
        ctx.fillStyle = 'rgba(203, 213, 225, 0.75)';
        const scoreText = node.avg_score !== null ? ` · 情緒 ${node.avg_score}` : '';
        ctx.fillText(
          `${node.event_count} 次${scoreText}`,
          node.x,
          node.y + radius + fontSize + metaSize + 5
        );
      }
    },
    [radiusOf, scoreRange, selectedPerson]
  );

  const renderLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D) => {
      const start = link.source;
      const end = link.target;
      if (!start || !end || start.x === undefined || end.x === undefined) return;

      const startR = radiusOf(start) + 3;
      const endR = radiusOf(end) + 3;
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= startR + endR) return;

      const startX = start.x + (dx * startR) / dist;
      const startY = start.y + (dy * startR) / dist;
      const endX = end.x - (dx * endR) / dist;
      const endY = end.y - (dy * endR) / dist;

      // 共現次數越多線越粗、越亮
      const { min, max } = linkWeightRange;
      const range = max - min;
      const t = range < 0.5 ? 0.5 : ((link.weight || 1) - min) / range;
      const isRelated =
        selectedPerson && (start.id === selectedPerson.id || end.id === selectedPerson.id);

      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      // 選中人物的相關連線用色盤中的霧青綠高亮（accent2），其餘用低對比灰
      ctx.strokeStyle = isRelated
        ? `rgba(92, 179, 161, ${0.4 + t * 0.45})`
        : `rgba(148, 163, 184, ${0.08 + t * 0.22})`;
      ctx.lineWidth = 0.8 + t * 3;
      ctx.stroke();
    },
    [radiusOf, linkWeightRange, selectedPerson]
  );

  useEffect(() => {
    if (!fgRef.current) return;
    // 人物數量少，把排斥力調大、連線拉長，讓節點清楚散開
    fgRef.current.d3Force('charge')?.strength(-1200);
    fgRef.current.d3Force('link')?.distance(180);
  }, [data, dimensions]);

  const handleNodeClick = useCallback(
    (node: any) => {
      const person = node as PersonNode;
      setSelectedPerson(person);
      setPersonEvents([]);
      setEventsLoading(true);
      fetch(`${API_BASE}/api/graph/person/${encodeURIComponent(person.id)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      })
        .then(res => res.json())
        .then(fetched => {
          if (fetched && fetched.success) {
            const events: PersonEvent[] = (fetched.events || [])
              .slice()
              .sort((a: PersonEvent, b: PersonEvent) => (a.date < b.date ? 1 : -1));
            setPersonEvents(events);
          }
        })
        .catch(err => console.error('Person events fetch error:', err))
        .finally(() => setEventsLoading(false));
    },
    [token]
  );

  const isEmpty = !data.nodes || data.nodes.length === 0;
  const notReady = dimensions.width === 0 || dimensions.height === 0;

  return (
    <div
      ref={containerRef}
      className="w-full h-full rounded-2xl shadow-inner overflow-hidden relative"
      style={{ backgroundColor: '#1a1e24', border: '1px solid #353e49' }}
    >
      {isEmpty || notReady ? (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-slate-500">
          <p>{notice || '等待人物關係資料...'}</p>
        </div>
      ) : (
        <ForceGraph2D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={data}
          nodeLabel={(node: any) =>
            `${node.label}｜${node.relationship || '關係未編譯'}｜${node.event_count} 次互動`
          }
          nodeCanvasObject={renderNode}
          linkCanvasObject={renderLink}
          backgroundColor="transparent"
          onNodeClick={handleNodeClick}
          onBackgroundClick={() => setSelectedPerson(null)}
          onNodeDragEnd={(node: any) => {
            node.fx = node.x;
            node.fy = node.y;
          }}
        />
      )}

      {/* 圖例：選中人物時隱藏，避免與詳情面板互相干擾 */}
      {!isEmpty && !selectedPerson && (
        <div
          className="absolute bottom-4 left-4 backdrop-blur-md p-3 rounded-xl flex flex-col gap-2 text-xs max-w-[calc(100%-2rem)]"
          style={{ backgroundColor: 'rgba(35, 41, 49, 0.85)', border: '1px solid #353e49' }}
        >
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 rounded-full shrink-0" style={{ background: EMOTION_GRADIENT }} />
            <span style={{ color: '#e2e8f0' }}>情緒偏低 → 偏高</span>
          </div>
          <div style={{ color: '#94a3b8' }}>圓圈大小＝互動次數，連線粗細＝共同出現次數</div>
          <div style={{ color: '#94a3b8' }}>點擊人物可查看關係檔案與事件時間軸</div>
        </div>
      )}

      {/* 人物詳情面板：整個內容區可滾動，避免長篇人物側寫被裁掉 */}
      {selectedPerson && (
        <div
          className="absolute top-4 right-4 bottom-4 w-[22rem] max-w-[calc(100%-2rem)] flex flex-col rounded-xl shadow-2xl z-10 overflow-hidden"
          style={{ backgroundColor: 'rgba(35, 41, 49, 0.96)', border: '1px solid #353e49' }}
        >
          {/* 固定標題列 */}
          <div
            className="flex items-start justify-between gap-2 px-5 pt-4 pb-3 shrink-0"
            style={{ borderBottom: '1px solid #353e49' }}
          >
            <div className="min-w-0">
              <h3 className="font-bold text-xl truncate" style={{ color: '#e2e8f0' }}>
                {selectedPerson.label}
              </h3>
              <p className="text-sm mt-0.5 break-words" style={{ color: '#5cb3a1' }}>
                {selectedPerson.relationship || '關係尚未編譯'}
              </p>
            </div>
            <button
              onClick={() => setSelectedPerson(null)}
              className="shrink-0 p-1 rounded-lg transition-colors hover:text-white"
              style={{ color: '#94a3b8' }}
              aria-label="關閉人物詳情"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* 可滾動內容區 */}
          <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-4">
            <div className="grid grid-cols-3 gap-2 mb-4 text-center">
              <div className="rounded-lg py-2 px-1" style={{ backgroundColor: 'rgba(15, 18, 22, 0.6)' }}>
                <div className="text-lg font-semibold" style={{ color: '#e2e8f0' }}>
                  {selectedPerson.event_count}
                </div>
                <div className="text-[11px]" style={{ color: '#94a3b8' }}>互動次數</div>
              </div>
              <div className="rounded-lg py-2 px-1" style={{ backgroundColor: 'rgba(15, 18, 22, 0.6)' }}>
                <div
                  className="text-lg font-semibold"
                  style={{
                    color: emotionColor(selectedPerson.avg_score, scoreRange.min, scoreRange.max)
                  }}
                >
                  {selectedPerson.avg_score ?? '—'}
                </div>
                <div className="text-[11px]" style={{ color: '#94a3b8' }}>平均情緒</div>
              </div>
              <div className="rounded-lg py-2 px-1" style={{ backgroundColor: 'rgba(15, 18, 22, 0.6)' }}>
                <div className="text-lg font-semibold" style={{ color: '#e2e8f0' }}>
                  {selectedPerson.avg_importance ?? '—'}
                </div>
                <div className="text-[11px]" style={{ color: '#94a3b8' }}>平均重要度</div>
              </div>
            </div>

            {(selectedPerson.first_date || selectedPerson.last_date) && (
              <p className="text-xs mb-3" style={{ color: '#94a3b8' }}>
                互動期間：{selectedPerson.first_date} ~ {selectedPerson.last_date}
              </p>
            )}

            {selectedPerson.description && (
              <p
                className="text-sm leading-relaxed mb-4 pb-4 break-words"
                style={{ color: '#cbd5e1', borderBottom: '1px solid #353e49' }}
              >
                {selectedPerson.description}
              </p>
            )}

            <h4 className="text-sm font-semibold mb-3" style={{ color: '#e2e8f0' }}>
              事件時間軸
            </h4>
            {eventsLoading ? (
              <p className="text-sm" style={{ color: '#94a3b8' }}>載入事件中...</p>
            ) : personEvents.length === 0 ? (
              <p className="text-sm" style={{ color: '#94a3b8' }}>沒有找到相關事件。</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {personEvents.map((ev, idx) => (
                  <li
                    key={`${ev.date}-${idx}`}
                    className="pl-3"
                    style={{ borderLeft: `3px solid ${emotionColor(ev.emotion_score, 20, 90)}` }}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-xs font-medium" style={{ color: '#94a3b8' }}>
                        {ev.date}
                      </span>
                      {ev.emotion_score !== null && (
                        <span
                          className="text-xs shrink-0"
                          style={{ color: emotionColor(ev.emotion_score, 20, 90) }}
                        >
                          {ev.emotion_score}
                        </span>
                      )}
                    </div>
                    {ev.topic && (
                      <div className="text-xs mb-0.5 break-words" style={{ color: '#5cb3a1' }}>
                        {ev.topic}
                      </div>
                    )}
                    <p className="text-sm leading-snug break-words" style={{ color: '#cbd5e1' }}>
                      {ev.summary || '（無摘要）'}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
