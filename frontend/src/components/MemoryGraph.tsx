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

export default function MemoryGraph() {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [selectedMemory, setSelectedMemory] = useState<Node | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('http://localhost:8000/api/dashboard/graph')
      .then(res => res.json())
      .then(fetchedData => {
        if (fetchedData && fetchedData.nodes && fetchedData.links) {
          setData(fetchedData);
        } else {
          console.error("Graph fetch invalid data:", fetchedData);
        }
      })
      .catch(err => console.error("Graph fetch error:", err));
  }, []);

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
    const radius = isEntity ? Math.sqrt(node.val || 1) * 3 : 13; // Memory balls are now fixed radius 7
    
    let rgb = '';
    if (isEntity) {
      rgb = '245, 158, 11'; // amber-500 for entities
    } else {
      const score = node.score || 50;
      if (score >= 80) rgb = '45, 212, 191'; // teal-400 (Very Happy)
      else if (score >= 60) rgb = '153, 246, 228'; // teal-200 (Happy)
      else if (score >= 40) rgb = '214, 211, 209'; // stone-300 (Neutral)
      else if (score >= 20) rgb = '251, 113, 133'; // rose-400 (Sad)
      else rgb = '225, 29, 72'; // rose-600 (Very Sad/Angry)
    }

    ctx.beginPath();
    if (isEntity) {
      // Use shadowBlur to create a true glowing optical halo around a solid core
      ctx.shadowColor = `rgba(${rgb}, 0.6)`;
      ctx.shadowBlur = 15; // Glow intensity/spread
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
      ctx.font = `bold ${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(28, 25, 23, 0.8)'; // stone-900
      ctx.fillText(node.name, node.x, node.y + radius + 15 + (10 / globalScale));
    }
  }, []);

  // Custom link rendering to avoid drawing lines inside the halos
  const renderLink = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const start = link.source;
    const end = link.target;
    if (start.x === undefined || end.x === undefined) return;

    // Calculate node visual boundaries. For entity, start outside the solid core.
    const startR = start.group === 'entity' ? Math.sqrt(start.val || 1) * 3 + 5 : 7;
    const endR = end.group === 'entity' ? Math.sqrt(end.val || 1) * 3 + 5 : 7;

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
    ctx.strokeStyle = 'rgba(168, 162, 158, 0.3)'; // stone-400
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
    <div ref={containerRef} className="w-full h-full bg-stone-50/50 rounded-[2rem] overflow-hidden relative">
      {!data.nodes || data.nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-stone-400">
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
      <div className="absolute bottom-6 left-6 bg-white/90 backdrop-blur-md p-4 rounded-2xl border border-stone-200 shadow-sm flex flex-col gap-3 text-sm">
        <div className="flex items-center gap-3">
          <div className="w-3.5 h-3.5 rounded-full bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.6)]"></div>
          <span className="text-stone-600 font-medium">核心人物 / 事物</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-3.5 h-3.5 rounded-full bg-teal-400 opacity-90"></div>
          <span className="text-stone-500">正向記憶</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-3.5 h-3.5 rounded-full bg-rose-500 opacity-90"></div>
          <span className="text-stone-500">負向記憶</span>
        </div>
      </div>

      {/* Selected Memory Detail Card */}
      {selectedMemory && (
        <div className="absolute top-6 right-6 w-80 bg-white/95 backdrop-blur-md p-6 rounded-3xl border border-stone-200 shadow-xl z-10 animate-in fade-in slide-in-from-top-4 duration-300">
          <button 
            onClick={() => setSelectedMemory(null)}
            className="absolute top-4 right-4 p-1.5 rounded-full text-stone-400 hover:bg-stone-100 hover:text-stone-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
          <h4 className="text-amber-600 font-bold mb-1.5 text-xs uppercase tracking-widest">{selectedMemory.name.split(' ')[0]}</h4>
          <h3 className="text-stone-800 font-black mb-4 text-xl leading-tight">{selectedMemory.name.substring(11)}</h3>
          <p className="text-stone-600 text-sm leading-relaxed max-h-60 overflow-y-auto pr-2 custom-scrollbar font-medium">
            {selectedMemory.summary || "目前沒有這段記憶的詳細摘要。"}
          </p>
        </div>
      )}
    </div>
  );
}
