import { useState } from 'react';
import { supabase } from '../supabase';
import { MoonIcon, SunIcon, ShieldIcon } from './Icons';

interface AuthScreenProps {
  isDark: boolean;
  onToggleTheme: () => void;
}

export default function AuthScreen({ isDark, onToggleTheme }: AuthScreenProps) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin,
          queryParams: { prompt: 'select_account' }
        }
      });
      if (error) throw error;
    } catch (err: any) {
      setError(err.message || 'Google 登入發生錯誤');
      setLoading(false);
    }
  };

  return (
    <div
      className="flex flex-col h-screen items-center justify-center p-4 font-sans"
      style={{ backgroundColor: 'var(--color-m-base)', color: 'var(--color-m-text)' }}
    >
      {/* Theme toggle at top-right */}
      <div className="absolute top-4 right-4">
        <button
          onClick={onToggleTheme}
          className="p-2 rounded-md transition-all"
          style={{ color: 'var(--color-m-muted)', backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}
          title={isDark ? '切換亮色模式' : '切換深色模式'}
        >
          {isDark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
        </button>
      </div>

      <div
        className="w-full max-w-sm rounded-2xl p-8 shadow-xl"
        style={{ backgroundColor: 'var(--color-m-panel)', border: '1px solid var(--color-m-border)' }}
      >
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">
            <span className="text-morandi-gradient">MemoryAI</span>
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-m-muted)' }}>你的專屬心靈伴侶與記憶管家</p>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-xl text-sm text-center" style={{ backgroundColor: 'rgba(192,100,100,0.15)', border: '1px solid rgba(192,100,100,0.3)', color: '#c09090' }}>
            {error}
          </div>
        )}

        <button
          onClick={handleGoogleLogin}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl font-medium transition-colors mb-4 disabled:opacity-50"
          style={{ backgroundColor: 'var(--color-m-panel-alt)', border: '1px solid var(--color-m-border)', color: 'var(--color-m-text)' }}
        >
          {loading ? (
            <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--color-m-border)', borderTopColor: 'var(--color-m-accent1)' }}></div>
          ) : (
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
          )}
          使用 Google 帳號登入
        </button>

        <div className="flex items-center gap-2 justify-center">
          <ShieldIcon size={12} />
          <p className="text-xs" style={{ color: 'var(--color-m-muted)' }}>安全登入，不留存密碼紀錄</p>
        </div>
      </div>
    </div>
  );
}
