import { useState, useEffect } from 'react';
import { Search, Edit2, Trash2, Calendar, Hash, Activity, Plus } from 'lucide-react';

interface Memory {
  id: string;
  diary_date: string;
  diary_time?: string;
  topic: string;
  summary: string;
  emotion_score: number;
  keywords: string[];
  original_text: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function MemoryTimeline() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Modal state
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Partial<Memory>>({});

  const fetchMemories = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/memories`);
      const data = await res.json();
      if (data.memories) {
        const sorted = data.memories.sort((a: Memory, b: Memory) => {
          const dateA = a.diary_date || '';
          const dateB = b.diary_date || '';
          if (dateA !== dateB) return dateB.localeCompare(dateA);
          const timeA = a.diary_time || '';
          const timeB = b.diary_time || '';
          return timeB.localeCompare(timeA);
        });
        setMemories(sorted);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMemories();
  }, []);

  const handleDelete = async (id: string) => {
    if (!window.confirm('確定要刪除這段記憶嗎？此動作無法復原。')) return;
    try {
      const res = await fetch(`${API_BASE}/api/memories/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setMemories(memories.filter(m => m.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSave = async () => {
    try {
      if (editingMemory.id) {
        // Update
        const res = await fetch(`${API_BASE}/api/memories/${editingMemory.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(editingMemory)
        });
        if (res.ok) {
          fetchMemories();
          setIsEditModalOpen(false);
        }
      } else {
        // Create
        const res = await fetch(`${API_BASE}/api/memories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(editingMemory)
        });
        if (res.ok) {
          fetchMemories();
          setIsEditModalOpen(false);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const openNewMemoryModal = () => {
    setEditingMemory({
      diary_date: new Date().toISOString().split('T')[0],
      diary_time: '',
      topic: '',
      summary: '',
      emotion_score: 50,
      keywords: [],
      original_text: ''
    });
    setIsEditModalOpen(true);
  };

  const filteredMemories = memories.filter(m => {
    const q = searchQuery.toLowerCase();
    return (
      (m.topic || '').toLowerCase().includes(q) ||
      (m.summary || '').toLowerCase().includes(q) ||
      (m.keywords || []).some(k => k.toLowerCase().includes(q))
    );
  }).sort((a, b) => {
    const timeA = a.diary_time || '00:00:00';
    const timeB = b.diary_time || '00:00:00';
    const datetimeA = `${a.diary_date} ${timeA}`;
    const datetimeB = `${b.diary_date} ${timeB}`;
    return datetimeB.localeCompare(datetimeA);
  });

  return (
    <div className="flex flex-col h-full bg-slate-900/50 p-6 rounded-3xl border border-slate-700/50 backdrop-blur-md">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0 mb-8">
        <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 flex items-center gap-3">
          <Activity className="w-6 h-6 text-blue-400" />
          歷史記憶流
        </h2>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full sm:w-auto">
          <div className="relative w-full sm:w-auto">
            <Search className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="搜尋記憶、關鍵字..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full sm:w-64 bg-slate-800/80 border border-slate-600/50 rounded-full py-2 pl-10 pr-4 text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50 placeholder:text-slate-500"
            />
          </div>
          <button 
            onClick={openNewMemoryModal}
            className="flex items-center justify-center gap-2 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-400 hover:to-indigo-500 text-white px-4 py-2 rounded-full font-medium transition-all shadow-lg shadow-blue-500/20 w-full sm:w-auto shrink-0"
          >
            <Plus className="w-4 h-4" />
            新增記憶
          </button>
        </div>
      </div>

      {/* Timeline List */}
      <div className="flex-1 overflow-y-auto pr-4 custom-scrollbar space-y-6">
        {loading ? (
          <div className="text-slate-400 text-center py-10 flex flex-col items-center">
            <div className="w-8 h-8 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-4"></div>
            正在讀取您的記憶庫...
          </div>
        ) : filteredMemories.length === 0 ? (
          <div className="text-slate-500 text-center py-10">找不到符合條件的記憶。</div>
        ) : (
          filteredMemories.map(memory => (
            <div key={memory.id} className="group relative bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6 hover:bg-slate-800/60 transition-all hover:border-slate-600 shadow-sm hover:shadow-xl">
              {/* Action Buttons */}
              <div className="absolute top-4 right-4 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                  onClick={() => { setEditingMemory(memory); setIsEditModalOpen(true); }}
                  className="p-2 bg-slate-700/50 hover:bg-blue-500/20 hover:text-blue-400 text-slate-300 rounded-lg transition-colors"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button 
                  onClick={() => handleDelete(memory.id)}
                  className="p-2 bg-slate-700/50 hover:bg-rose-500/20 hover:text-rose-400 text-slate-300 rounded-lg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="flex gap-4 sm:gap-6">
                {/* Score Indicator */}
                <div className="flex flex-col items-center justify-start sm:justify-center shrink-0 w-12 sm:w-auto sm:min-w-[80px]">
                  <div className={`w-12 h-12 sm:w-16 sm:h-16 rounded-full flex items-center justify-center text-lg sm:text-xl font-bold shadow-lg
                    ${memory.emotion_score >= 80 ? 'bg-teal-500/20 text-teal-400 border border-teal-500/50 shadow-teal-500/10' : 
                      memory.emotion_score >= 60 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50 shadow-emerald-500/10' : 
                      memory.emotion_score >= 40 ? 'bg-slate-500/20 text-slate-400 border border-slate-500/50' : 
                      memory.emotion_score >= 20 ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50 shadow-blue-500/10' : 
                      'bg-indigo-500/20 text-indigo-400 border border-indigo-500/50 shadow-indigo-500/10'}`}>
                    {memory.emotion_score}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="flex items-center gap-1.5 text-slate-400 text-sm bg-slate-900/50 px-3 py-1 rounded-full">
                      <Calendar className="w-3.5 h-3.5" />
                      {memory.diary_date} {memory.diary_time && <span className="text-slate-500 font-medium">| {memory.diary_time}</span>}
                    </span>
                    <h3 className="text-xl font-bold text-slate-100">{memory.topic || '無主題'}</h3>
                  </div>
                  
                  <p className="text-slate-300 leading-relaxed mb-4">{memory.summary}</p>
                  
                  <div className="flex flex-wrap gap-2">
                    {(memory.keywords || []).map((kw, idx) => (
                      <span key={idx} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-slate-700/30 text-slate-300 border border-slate-600/30">
                        <Hash className="w-3 h-3 text-slate-500" />
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Edit/Create Modal */}
      {isEditModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
            <h3 className="text-xl font-bold text-slate-100 mb-6">{editingMemory.id ? '編輯記憶' : '手動新增記憶'}</h3>
            
            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1">日期</label>
                  <input type="date" value={editingMemory.diary_date || ''} onChange={e => setEditingMemory({...editingMemory, diary_date: e.target.value})} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-1">時間 (選填)</label>
                  <input type="time" value={editingMemory.diary_time || ''} onChange={e => setEditingMemory({...editingMemory, diary_time: e.target.value})} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500" />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">情緒分數 (0-100)</label>
                <input type="number" min="0" max="100" value={editingMemory.emotion_score || 0} onChange={e => setEditingMemory({...editingMemory, emotion_score: parseInt(e.target.value)})} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500" />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">主題</label>
                <input type="text" value={editingMemory.topic || ''} onChange={e => setEditingMemory({...editingMemory, topic: e.target.value})} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500" />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">關鍵字 (請用逗號分隔)</label>
                <input type="text" value={(editingMemory.keywords || []).join(', ')} onChange={e => setEditingMemory({...editingMemory, keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500" placeholder="陳政煒, 專案, ..." />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">摘要</label>
                <textarea value={editingMemory.summary || ''} onChange={e => setEditingMemory({...editingMemory, summary: e.target.value})} className="w-full h-24 bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500 resize-none custom-scrollbar" />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">原始日記文本</label>
                <textarea value={editingMemory.original_text || ''} onChange={e => setEditingMemory({...editingMemory, original_text: e.target.value})} className="w-full h-32 bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500 resize-none custom-scrollbar" placeholder="如果需要，請貼上原始的日記..." />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-700/50">
              <button onClick={() => setIsEditModalOpen(false)} className="px-5 py-2.5 text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-xl transition-colors">取消</button>
              <button onClick={handleSave} className="px-5 py-2.5 text-white bg-blue-600 hover:bg-blue-500 rounded-xl transition-colors shadow-lg shadow-blue-500/20 font-medium">儲存記憶</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
