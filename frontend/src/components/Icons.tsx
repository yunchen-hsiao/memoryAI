// Icons.tsx — 莫蘭迪冷調漸層 SVG icon 集
// 每個 icon 都有內建 <defs> 漸層，霧藍 → 鼠尾草綠色系

interface IconProps {
  size?: number;
  className?: string;
}

const GRAD_ID_CHAT = 'mg-chat';
const GRAD_ID_DASH = 'mg-dash';
const GRAD_ID_TL = 'mg-timeline';
const GRAD_ID_IMPORT = 'mg-import';
const GRAD_ID_SHIELD = 'mg-shield';
const GRAD_ID_LOGOUT = 'mg-logout';
const GRAD_ID_BRAIN = 'mg-brain';

// 共用漸層 defs（淺色模式下 from/to 可由 CSS var 覆蓋）
function GradDef({ id, from = '#7f94a8', to = '#7a9490' }: { id: string; from?: string; to?: string }) {
  return (
    <defs>
      <linearGradient id={id} x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor={from} />
        <stop offset="100%" stopColor={to} />
      </linearGradient>
    </defs>
  );
}

/** 🧠 大腦神經網路 icon（聊天頁） */
export function BrainIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_BRAIN;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} />
      {/* 大腦輪廓 — 左半部 */}
      <path d="M9 3C6.24 3 4 5.24 4 8c0 1.1.36 2.12.97 2.94C4.36 11.5 4 12.46 4 13.5 4 15.98 5.57 18.1 7.8 18.8 8.5 20.62 10.12 22 12 22" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" fill="none"/>
      {/* 大腦輪廓 — 右半部 */}
      <path d="M15 3c2.76 0 5 2.24 5 5 0 1.1-.36 2.12-.97 2.94.61.56.97 1.52.97 2.56 0 2.48-1.57 4.6-3.8 5.3C15.5 20.62 13.88 22 12 22" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" fill="none"/>
      {/* 中線 */}
      <line x1="12" y1="3" x2="12" y2="22" stroke={`url(#${id})`} strokeWidth="1" strokeDasharray="2 2" opacity="0.5"/>
      {/* 神經連結點 */}
      <circle cx="8.5" cy="9" r="1" fill={`url(#${id})`} opacity="0.8"/>
      <circle cx="15.5" cy="9" r="1" fill={`url(#${id})`} opacity="0.8"/>
      <circle cx="7" cy="14" r="1" fill={`url(#${id})`} opacity="0.8"/>
      <circle cx="17" cy="14" r="1" fill={`url(#${id})`} opacity="0.8"/>
      {/* 連結線 */}
      <line x1="8.5" y1="9" x2="12" y2="12" stroke={`url(#${id})`} strokeWidth="0.8" opacity="0.5"/>
      <line x1="15.5" y1="9" x2="12" y2="12" stroke={`url(#${id})`} strokeWidth="0.8" opacity="0.5"/>
      <line x1="7" y1="14" x2="12" y2="12" stroke={`url(#${id})`} strokeWidth="0.8" opacity="0.5"/>
      <line x1="17" y1="14" x2="12" y2="12" stroke={`url(#${id})`} strokeWidth="0.8" opacity="0.5"/>
      <circle cx="12" cy="12" r="1.2" fill={`url(#${id})`}/>
    </svg>
  );
}

/** 💬 對話泡泡 icon（聊天頁備用） */
export function ChatIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_CHAT;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} />
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="9" y1="10" x2="15" y2="10" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
      <line x1="9" y1="13" x2="13" y2="13" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.5"/>
    </svg>
  );
}

/** 🌐 軌道儀表板 icon */
export function DashboardIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_DASH;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} />
      {/* 外圓 */}
      <circle cx="12" cy="12" r="9" stroke={`url(#${id})`} strokeWidth="1.5"/>
      {/* 橢圓軌道 */}
      <ellipse cx="12" cy="12" rx="9" ry="4" stroke={`url(#${id})`} strokeWidth="1" opacity="0.6" transform="rotate(30 12 12)"/>
      <ellipse cx="12" cy="12" rx="9" ry="4" stroke={`url(#${id})`} strokeWidth="1" opacity="0.4" transform="rotate(-30 12 12)"/>
      {/* 核心點 */}
      <circle cx="12" cy="12" r="2" fill={`url(#${id})`}/>
      {/* 小衛星點 */}
      <circle cx="19.5" cy="10.5" r="1" fill={`url(#${id})`} opacity="0.8"/>
      <circle cx="4.5" cy="13.5" r="1" fill={`url(#${id})`} opacity="0.8"/>
    </svg>
  );
}

/** ⏳ 時間軸 icon（歷史記憶） */
export function TimelineIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_TL;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} />
      {/* 垂直時間軸線 */}
      <line x1="8" y1="3" x2="8" y2="21" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round"/>
      {/* 時間節點 */}
      <circle cx="8" cy="6" r="2" fill={`url(#${id})`}/>
      <circle cx="8" cy="12" r="2" fill={`url(#${id})`} opacity="0.7"/>
      <circle cx="8" cy="18" r="2" fill={`url(#${id})`} opacity="0.5"/>
      {/* 說明線條 */}
      <line x1="11" y1="6" x2="20" y2="6" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.8"/>
      <line x1="11" y1="9" x2="17" y2="9" stroke={`url(#${id})`} strokeWidth="1" strokeLinecap="round" opacity="0.4"/>
      <line x1="11" y1="12" x2="20" y2="12" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.6"/>
      <line x1="11" y1="15" x2="16" y2="15" stroke={`url(#${id})`} strokeWidth="1" strokeLinecap="round" opacity="0.3"/>
      <line x1="11" y1="18" x2="20" y2="18" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.5"/>
    </svg>
  );
}

/** ☁️ 雲端上傳 icon（批次匯入） */
export function UploadIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_IMPORT;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} from="#7a9490" to="#7f94a8"/>
      {/* 雲朵 */}
      <path d="M18 15a4 4 0 0 0-7.74-1.5A3 3 0 1 0 6 18h12a3 3 0 0 0 0-6z" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinejoin="round"/>
      {/* 上傳箭頭 */}
      <line x1="12" y1="7" x2="12" y2="13" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round"/>
      <polyline points="9 10 12 7 15 10" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

/** 🛡 隱私盾牌 icon */
export function ShieldIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_SHIELD;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} from="#8e8fb0" to="#7a9490"/>
      <path d="M12 3L4 7v5c0 4.97 3.5 9.1 8 10 4.5-.9 8-5.03 8-10V7L12 3z" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinejoin="round"/>
      <polyline points="9 12 11 14 15 10" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

/** 🚪 登出 icon */
export function LogoutIcon({ size = 20, className = '' }: IconProps) {
  const id = GRAD_ID_LOGOUT;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <GradDef id={id} from="#8a9099" to="#7f94a8"/>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <polyline points="16 17 21 12 16 7" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="21" y1="12" x2="9" y2="12" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

/** 🌙 深色模式 icon */
export function MoonIcon({ size = 20, className = '' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

/** ☀️ 亮色模式 icon */
export function SunIcon({ size = 20, className = '' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.5"/>
      <line x1="12" y1="1" x2="12" y2="3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="12" y1="21" x2="12" y2="23" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="1" y1="12" x2="3" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="21" y1="12" x2="23" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
