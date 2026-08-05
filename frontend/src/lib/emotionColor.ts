/**
 * 情緒分數的共用色階，供關係圖與關係熱力圖使用，確保兩處配色一致。
 *
 * 配色取自專案既有的莫蘭迪色盤（見 index.css）：
 *   低分 → --color-m-accent3 霧紫 #8a88cc
 *   中間 → --color-m-accent1 霧藍 #648db8
 *   高分 → --color-m-accent2 霧青綠 #5cb3a1
 *
 * 刻意避開高彩度的黃色/琥珀色，避免與整體柔和色調衝突。
 */

const LOW: [number, number, number] = [138, 136, 204]; // accent3 霧紫
const MID: [number, number, number] = [100, 141, 184]; // accent1 霧藍
const HIGH: [number, number, number] = [92, 179, 161]; // accent2 霧青綠

/** 沒有資料時使用的中性灰 */
export const NO_DATA_COLOR = 'rgb(148, 163, 184)';

/** CSS 漸層字串，給圖例使用 */
export const EMOTION_GRADIENT =
  'linear-gradient(to right, rgb(138,136,204), rgb(100,141,184), rgb(92,179,161))';

function lerp(a: [number, number, number], b: [number, number, number], t: number): string {
  const rgb = a.map((c, i) => Math.round(c + (b[i] - c) * t));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

/**
 * 將情緒分數轉換為顏色。
 *
 * 使用「相對於傳入範圍」的正規化，而非絕對的 0-100 門檻：
 * 實際資料的平均情緒往往集中在很窄的區間（例如 58~67），
 * 若用絕對門檻，所有節點/格子會是同一個顏色，差異完全看不出來。
 *
 * @param score 情緒分數，null 代表沒有資料
 * @param min   當前資料集的最低分
 * @param max   當前資料集的最高分
 */
export function emotionColor(score: number | null, min: number, max: number): string {
  if (score === null || score === undefined) return NO_DATA_COLOR;

  const range = max - min;
  // 範圍過窄（或只有單一資料點）時給中間色，避免除以 0 或誇大微小差異
  const t = range < 0.5 ? 0.5 : Math.min(1, Math.max(0, (score - min) / range));

  // 兩段線性插值：低→中→高
  return t < 0.5 ? lerp(LOW, MID, t * 2) : lerp(MID, HIGH, (t - 0.5) * 2);
}
