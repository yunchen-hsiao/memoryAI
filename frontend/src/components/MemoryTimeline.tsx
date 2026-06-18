import React, { useState, useEffect } from 'react';
import { Search, Edit2, Trash2, Calendar, Hash, Smile, Frown, Activity, Plus } from 'lucide-react';

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
      const res = await fetch('http://localhost:8000/api/memories');
      const data = await res.json();
      if (data.memories) {
        setMemories(data.memories);
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
      const res = await fetch(`http://localhost:8000/api/memories/${id}`, { method: 'DELETE' });
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
        const res = await fetch(`http://localhost:8000/api/memories/${editingMemory.id}`, {
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
        const res = await fetch('http://localhost:8000/api/memories', {
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
  });

  return (
    <div className="flex flex-col h-full bg-stone-50/50 p-8 rounded-[2rem] border border-stone-200 shadow-sm backdrop-blur-md">
      {/* Header & Controls */}
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-amber-700 to-rose-500 flex items-center gap-3 tracking-tight">
          <Activity className="w-8 h-8 text-amber-600" />
          歷史記憶流
        </h2>
        <div className="flex items-center gap-5">
          <div className="relative">
            <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-stone-400" />
            <input 
              type="text" 
              placeholder="搜尋記憶、關鍵字..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-72 bg-white border border-stone-200 rounded-full py-2.5 pl-12 pr-5 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 placeholder:text-stone-400 shadow-sm transition-all focus:shadow-md"
            />
          </div>
          <button 
            onClick={openNewMemoryModal}
            className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-6 py-2.5 rounded-full font-bold transition-all shadow-md border-b-2 border-amber-700 active:border-b-0 active:translate-y-[2px]"
          >
            <Plus className="w-5 h-5" />
            新增記憶
          </button>
        </div>
      </div>

      {/* Timeline List */}
      <div className="flex-1 overflow-y-auto pr-4 custom-scrollbar space-y-6">
        {loading ? (
          <div className="text-stone-400 text-center py-10 flex flex-col items-center">
            <div className="w-10 h-10 border-4 border-amber-500/30 border-t-amber-500 rounded-full animate-spin mb-4"></div>
            正在讀取您的專屬記憶庫...
          </div>
        ) : filteredMemories.length === 0 ? (
          <div className="text-stone-400 text-center py-10 italic">翻遍了抽屜，找不到符合條件的記憶呢。</div>
        ) : (
          filteredMemories.map(memory => (
            <div key={memory.id} className="group relative bg-white border border-stone-200 rounded-3xl p-6 hover:bg-stone-50 transition-all hover:border-stone-300 shadow-sm hover:shadow-md">
              {/* Action Buttons */}
              <div className="absolute top-5 right-5 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                  onClick={() => { setEditingMemory(memory); setIsEditModalOpen(true); }}
                  className="p-2 bg-stone-100 hover:bg-teal-50 hover:text-teal-600 text-stone-400 rounded-xl transition-colors"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button 
                  onClick={() => handleDelete(memory.id)}
                  className="p-2 bg-stone-100 hover:bg-rose-50 hover:text-rose-600 text-stone-400 rounded-xl transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="flex gap-6">
                {/* Score Indicator */}
                <div className="flex flex-col items-center justify-center min-w-[80px]">
                  <div className={`w-16 h-16 rounded-[2rem] flex items-center justify-center text-xl font-black shadow-sm
                    ${memory.emotion_score >= 80 ? 'bg-teal-50 text-teal-600 border border-teal-200' : 
                      memory.emotion_score >= 60 ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' : 
                      memory.emotion_score >= 40 ? 'bg-stone-100 text-stone-500 border border-stone-200' : 
                      memory.emotion_score >= 20 ? 'bg-rose-50 text-rose-500 border border-rose-200' : 
                      'bg-rose-100 text-rose-600 border border-rose-300'}`}>
                    {memory.emotion_score}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="flex items-center gap-1.5 text-stone-500 font-bold tracking-wider text-xs bg-stone-100 px-3.5 py-1.5 rounded-xl border border-stone-200/50">
                      <Calendar className="w-3.5 h-3.5" />
                      {memory.diary_date} {memory.diary_time && <span className="text-stone-400 font-medium">| {memory.diary_time}</span>}
                    </span>
                    <h3 className="text-xl font-black text-stone-800">{memory.topic || '無主題'}</h3>
                  </div>
                  
                  <p className="text-stone-600 leading-relaxed mb-4 font-medium">{memory.summary}</p>
                  
                  <div className="flex flex-wrap gap-2">
                    {(memory.keywords || []).map((kw, idx) => (
                      <span key={idx} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl bg-stone-50 text-stone-600 border border-stone-200 font-bold shadow-sm">
                        <Hash className="w-3 h-3 text-stone-400" />
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
        <div className="fixed inset-0 bg-stone-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-stone-200 rounded-[2rem] p-8 w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
            <h3 className="text-2xl font-black text-stone-800 mb-6 flex items-center gap-3">
              <span className="text-3xl">📝</span> {editingMemory.id ? '編輯記憶' : '手動寫下回憶'}
            </h3>
            
            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">日期</label>
                  <input type="date" value={editingMemory.diary_date || ''} onChange={e => setEditingMemory({...editingMemory, diary_date: e.target.value})} className="w-full bg-stone-50 border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">時間 (選填)</label>
                  <input type="time" value={editingMemory.diary_time || ''} onChange={e => setEditingMemory({...editingMemory, diary_time: e.target.value})} className="w-full bg-stone-50 border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">情緒分數 (0-100)</label>
                <input type="number" min="0" max="100" value={editingMemory.emotion_score || 0} onChange={e => setEditingMemory({...editingMemory, emotion_score: parseInt(e.target.value)})} className="w-full bg-stone-50 border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm" />
              </div>

              <div>
                <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">主題</label>
                <input type="text" value={editingMemory.topic || ''} onChange={e => setEditingMemory({...editingMemory, topic: e.target.value})} className="w-full bg-stone-50 border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm" />
              </div>

              <div>
                <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">關鍵字 (請用逗號分隔)</label>
                <input type="text" value={(editingMemory.keywords || []).join(', ')} onChange={e => setEditingMemory({...editingMemory, keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} className="w-full bg-stone-50 border border-stone-200 rounded-xl p-3 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 shadow-sm" placeholder="陳政煒, 專案, ..." />
              </div>

              <div>
                <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">摘要</label>
                <textarea value={editingMemory.summary || ''} onChange={e => setEditingMemory({...editingMemory, summary: e.target.value})} className="w-full h-28 bg-stone-50 border border-stone-200 rounded-2xl p-4 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 resize-none custom-scrollbar shadow-sm" />
              </div>
              
              <div>
                <label className="block text-xs font-bold text-stone-400 mb-1.5 uppercase tracking-wider">原始日記文本</label>
                <textarea value={editingMemory.original_text || ''} onChange={e => setEditingMemory({...editingMemory, original_text: e.target.value})} className="w-full h-36 bg-stone-50 border border-stone-200 rounded-2xl p-4 text-stone-800 focus:outline-none focus:ring-2 focus:ring-teal-500/30 resize-none custom-scrollbar shadow-sm" placeholder="如果需要，請貼上原始的日記..." />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-8 pt-5 border-t border-stone-100">
              <button onClick={() => setIsEditModalOpen(false)} className="px-6 py-3 text-stone-500 hover:text-stone-800 bg-stone-100 hover:bg-stone-200 font-bold rounded-2xl transition-colors">取消</button>
              <button onClick={handleSave} className="px-6 py-3 text-white bg-amber-600 hover:bg-amber-500 font-bold rounded-2xl transition-all shadow-md hover:shadow-lg border-b-2 border-amber-700 active:border-b-0 active:translate-y-[2px]">儲存記憶</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
