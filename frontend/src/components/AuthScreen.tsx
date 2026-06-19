import { useState } from 'react';
import { supabase } from '../supabase';
import { Globe } from 'lucide-react';

export default function AuthScreen() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin,
          queryParams: {
            prompt: 'select_account'
          }
        }
      });
      if (error) throw error;
    } catch (err: any) {
      setError(err.message || 'Google 登入發生錯誤');
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-50 font-sans items-center justify-center p-4">
      <div className="w-full max-w-md bg-slate-800/40 border border-slate-700/50 rounded-2xl p-8 shadow-2xl backdrop-blur-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold flex items-center justify-center gap-2 mb-2">
            <span className="bg-gradient-to-r from-emerald-400 to-teal-500 bg-clip-text text-transparent">MemoryAI</span>
          </h1>
          <p className="text-slate-400 text-sm">你的專屬心靈伴侶與記憶管家</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-rose-500/20 border border-rose-500/50 text-rose-300 rounded-xl text-sm text-center">
            {error}
          </div>
        )}

        <button
          onClick={handleGoogleLogin}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 bg-white hover:bg-slate-100 text-slate-900 py-3 px-4 rounded-xl font-medium transition-colors mb-2 shadow-sm disabled:opacity-50"
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin"></div>
          ) : (
            <Globe className="w-5 h-5 text-blue-500" />
          )}
          使用 Google 帳號登入
        </button>
        <p className="text-slate-500 text-xs text-center mt-4">
          安全登入，不留存密碼紀錄
        </p>
      </div>
    </div>
  );
}
