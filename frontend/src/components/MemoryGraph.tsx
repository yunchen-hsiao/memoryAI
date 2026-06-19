import { useEffect, useState, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { X } from 'lucide-react';

interface Node {
  id: string;
  name: string;
  group: 'entity' | 'memory';
  val: number;
  score?: number;
  summary?: string;
}

interface Link {
  source: string;
  target: string;
  value: number;
}

interface GraphData {
  nodes: Node[];
  links: Link[];
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function MemoryGraph({ token }: { token: string | null }) {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [selectedMemory, setSelectedMemory] = useState<Node | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/graph`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(fetchedData => {
        if (fetchedData && fetchedData.nodes && fetchedData.links) {
          setData(fetchedData);
        } else {
          console.error("Graph fetch invalid data:", fetchedData);
        }
      })
      .catch(err => console.error("Graph fetch error:", err));
  }, [token]);

  useEffect(() => {
    // Measure container size for graph
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

  // Custom node rendering for soft edges
  const renderNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    if (node.x === undefined || node.y === undefined) return; // Prevent canvas crash before layout initializes
    
    const isEntity = node.group === 'entity';
    const radius = isEntity ? 15 + Math.sqrt(node.val || 1) * 3 : 6; // Entity: 基礎15+權重, Memory: 固定6
    
    let rgb = '';
    if (isEntity) {
      rgb = '248, 250, 252'; // White for entities
    } else {
      const score = node.score || 50;
      if (score >= 80) rgb = '96, 165, 250'; // blue-400 (Very Happy)
      else if (score >= 60) rgb = '147, 197, 253'; // blue-300 (Happy)
      else if (score >= 40) rgb = '148, 163, 184'; // slate-400 (Neutral)
      else if (score >= 20) rgb = '244, 63, 94'; // rose-500 (Sad)
      else rgb = '190, 18, 60'; // rose-700 (Very Sad/Angry)
    }

    ctx.beginPath();
    if (isEntity) {
      // Use shadowBlur to create a true glowing optical halo around a solid core
      ctx.shadowColor = `rgba(${rgb}, 0.8)`;
      ctx.shadowBlur = 25; // Glow intensity/spread
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = `rgb(${rgb})`;
      ctx.fill();
      ctx.shadowBlur = 0; // Reset shadow so it doesn't affect other elements
    } else {
      // Solid circle for memories
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = `rgb(${rgb})`;
      ctx.fill();
    }

    // Draw text label only for entities
    if (isEntity) {
      const fontSize = 14 / globalScale; 
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.fillText(node.name, node.x, node.y + radius + 15 + (10 / globalScale));
    }
  }, []);

  // Custom link rendering to avoid drawing lines inside the halos
  const renderLink = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const start = link.source;
    const end = link.target;
    if (start.x === undefined || end.x === undefined) return;

    // Calculate node visual boundaries. For entity, start outside the solid core.
    const startR = start.group === 'entity' ? 15 + Math.sqrt(start.val || 1) * 3 + 5 : 6;
    const endR = end.group === 'entity' ? 15 + Math.sqrt(end.val || 1) * 3 + 5 : 6;

    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // If nodes are too close and overlapping, don't draw the line at all
    if (dist <= startR + endR) return;

    // Calculate start and end points on the edge
    const startX = start.x + (dx * startR) / dist;
    const startY = start.y + (dy * startR) / dist;
    const endX = end.x - (dx * endR) / dist;
    const endY = end.y - (dy * endR) / dist;

    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(endX, endY);
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }, []);

  const fgRef = useRef<any>(null);

  useEffect(() => {
    // 調整引力引擎，讓節點互相排斥得更遠，並拉長連線距離
    if (fgRef.current) {
      // 針對「核心人物/事物」給予極大的排斥力 (-1500)，讓它們一開始就會強烈互相彈開
      // 一般的記憶行星則維持 -250 的排斥力
      fgRef.current.d3Force('charge').strength((node: any) => {
        return node.group === 'entity' ? -1500 : -250;
      });
      fgRef.current.d3Force('link').distance(100);
    }
  }, [data]);

  return (
    <div ref={containerRef} className="w-full h-full bg-slate-900/40 rounded-2xl border border-slate-700/50 shadow-inner overflow-hidden relative">
      {!data.nodes || data.nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500">
          <p>等待星系資料... (若持續未顯示，請確認後端是否已重新啟動)</p>
        </div>
      ) : (
        <ForceGraph2D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={data}
          nodeLabel={node => node.group === 'memory' ? node.name : ''} 
          nodeCanvasObject={renderNode}
          linkCanvasObject={renderLink}
          backgroundColor="transparent"
          onNodeClick={node => {
            if (node.group === 'memory') {
              setSelectedMemory(node as Node);
            } else {
              setSelectedMemory(null);
            }
          }}
          onNodeDragEnd={node => {
            node.fx = node.x;
            node.fy = node.y;
          }}
        />
      )}
      
      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-slate-900/80 backdrop-blur-md p-3 rounded-xl border border-slate-700/50 flex flex-col gap-2 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-slate-50 shadow-[0_0_12px_rgba(248,250,252,1)]"></div>
          <span className="text-slate-300">核心人物 / 事物</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-400 opacity-80"></div>
          <span className="text-slate-400">正向記憶</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-rose-500 opacity-80"></div>
          <span className="text-slate-400">負向記憶</span>
        </div>
      </div>

      {/* Selected Memory Detail Card */}
      {selectedMemory && (
        <div className="absolute top-4 right-4 w-80 bg-slate-800/95 backdrop-blur-md p-5 rounded-xl border border-slate-600/50 shadow-2xl z-10 animate-in fade-in slide-in-from-top-4 duration-300">
          <button 
            onClick={() => setSelectedMemory(null)}
            className="absolute top-3 right-3 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
          <h4 className="text-emerald-400 font-semibold mb-1 text-sm">{selectedMemory.name.split(' ')[0]}</h4>
          <h3 className="text-slate-100 font-bold mb-3 text-lg leading-tight">{selectedMemory.name.substring(11)}</h3>
          <p className="text-slate-300 text-sm leading-relaxed max-h-60 overflow-y-auto pr-2">
            {selectedMemory.summary || "目前沒有這段記憶的詳細摘要。"}
          </p>
        </div>
      )}
    </div>
  );
}
