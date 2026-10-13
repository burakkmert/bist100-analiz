// Fiyat grafiği: çizgi ya da mum + isteğe bağlı tahmin bandı (p10–p90 gölge, p50 kesik çizgi).
// • Parmağı yatay kaydırınca o günün tarihi ve fiyatı görünür; dikey kaydırma sayfayı kaydırır.
// • 1Y'de haftalık, 5Y'de aylık mumlar (çok sayıda ince mum okunmaz).
// • Statik çizim memo'lanır; kaydırırken yalnızca imleç katmanı yeniden çizilir.
import * as Haptics from 'expo-haptics';
import { memo, useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from 'react-native-svg';

import { mid as bandMidOf, type AssetType, type ForecastBand, type PricePoint } from '@/api/types';
import { AppText } from '@/components/ui';
import { formatAxis, formatDate, formatPct, formatPrice } from '@/lib/format';
import { font } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

export type Range = '1A' | '3A' | '1Y' | '5Y';
export type ChartMode = 'line' | 'candle';

const RANGE_DAYS: Record<Range, number> = { '1A': 22, '3A': 66, '1Y': 252, '5Y': 1260 };
const CANDLE_GROUP: Record<Range, number> = { '1A': 1, '3A': 1, '1Y': 5, '5Y': 21 };
const MAX_LINE_POINTS = 260;

interface Props {
  history: PricePoint[];
  range: Range;
  mode: ChartMode;
  type: AssetType;
  width: number;
  height?: number;
  band?: ForecastBand | null;
}

interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

const PAD = { top: 12, bottom: 18, left: 0, right: 52 };

export function PriceChart({ history, range, mode, type, width, height = 220, band }: Props) {
  const p = useTheme();
  const [idx, setIdx] = useState<number | null>(null);
  const lastIdx = useRef<number | null>(null);

  // ---- Veri hazırlığı ----
  const bars = useMemo<Bar[]>(() => {
    const slice = history.slice(-RANGE_DAYS[range]);
    const toBar = (pt: PricePoint): Bar => ({
      date: pt.date,
      open: pt.open ?? pt.close,
      high: pt.high ?? pt.close,
      low: pt.low ?? pt.close,
      close: pt.close,
    });
    if (mode === 'candle') return group(slice.map(toBar), CANDLE_GROUP[range]);
    const step = Math.max(1, Math.ceil(slice.length / MAX_LINE_POINTS));
    const thinned = slice.filter((_, i) => i % step === 0 || i === slice.length - 1);
    return thinned.map(toBar);
  }, [history, range, mode]);

  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  // Tahmin bandı varsa sağdaki %22'lik alan geleceğe ayrılır
  const futureW = band ? plotW * 0.22 : 0;
  const pastW = plotW - futureW;

  const geo = useMemo(() => {
    let min = Math.min(...bars.map((b) => (mode === 'candle' ? b.low : b.close)));
    let max = Math.max(...bars.map((b) => (mode === 'candle' ? b.high : b.close)));
    if (band) {
      min = Math.min(min, band.p10);
      max = Math.max(max, band.p90);
    }
    const pad = (max - min) * 0.08 || max * 0.01;
    min -= pad;
    max += pad;
    const n = bars.length;
    const xAt = (i: number) => PAD.left + (n <= 1 ? pastW : (i / (n - 1)) * pastW);
    const yAt = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * plotH;
    return { min, max, n, xAt, yAt };
  }, [bars, band, mode, pastW, plotH]);

  const first = bars[0]?.close ?? 0;
  const last = bars[bars.length - 1]?.close ?? 0;
  const up = last >= first;
  const lineColor = up ? p.up : p.down;

  // ---- Dokunma ----
  const pick = (x: number) => {
    const rel = Math.min(Math.max(x - PAD.left, 0), pastW);
    const i = Math.round((rel / pastW) * (geo.n - 1));
    if (i !== lastIdx.current) {
      lastIdx.current = i;
      setIdx(i);
      Haptics.selectionAsync().catch(() => {});
    }
  };
  const release = () => {
    lastIdx.current = null;
    setIdx(null);
  };
  const pan = Gesture.Pan()
    .runOnJS(true)
    .activeOffsetX([-6, 6])
    .failOffsetY([-14, 14])
    .onStart((e) => pick(e.x))
    .onUpdate((e) => pick(e.x))
    .onFinalize(release);
  const press = Gesture.LongPress()
    .runOnJS(true)
    .minDuration(180)
    .onStart((e) => pick(e.x))
    .onFinalize(release);
  const gesture = Gesture.Race(pan, press);

  if (bars.length < 2 || width <= 0) return <View style={{ height }} />;

  const sel = idx !== null ? bars[idx] : null;
  const selChange = sel ? ((sel.close - first) / first) * 100 : null;

  return (
    <View>
      {/* Seçili nokta bilgisi (kaydırırken) ya da aralık değişimi */}
      <View style={styles.info}>
        {sel ? (
          <>
            <AppText variant="caption" color="textMuted">
              {formatDate(sel.date)}
              {mode === 'candle' && CANDLE_GROUP[range] > 1 ? (range === '1Y' ? ' haftası' : ' ayı') : ''}
            </AppText>
            <AppText variant="caption" color="textMuted">
              {mode === 'candle' && type === 'stock'
                ? `A ${formatPrice(sel.open)} · Y ${formatPrice(sel.high)} · D ${formatPrice(sel.low)} · K ${formatPrice(sel.close)}`
                : `${formatPrice(sel.close, type)} · ${formatPct(selChange ?? 0)}`}
            </AppText>
          </>
        ) : (
          <AppText variant="caption" color="textMuted">
            {range} değişim:{' '}
            <AppText variant="caption" style={{ color: lineColor }}>
              {formatPct(((last - first) / first) * 100)}
            </AppText>
          </AppText>
        )}
      </View>

      <GestureDetector gesture={gesture}>
        <View>
          <StaticChart
            bars={bars}
            mode={mode}
            width={width}
            height={height}
            geo={geo}
            pastW={pastW}
            band={band ?? null}
            type={type}
            lineColor={lineColor}
          />
          {sel && idx !== null ? (
            <Svg width={width} height={height} style={StyleSheet.absoluteFill} pointerEvents="none">
              <Line
                x1={geo.xAt(idx)}
                x2={geo.xAt(idx)}
                y1={PAD.top}
                y2={height - PAD.bottom}
                stroke={p.textMuted}
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              <Circle cx={geo.xAt(idx)} cy={geo.yAt(sel.close)} r={5} fill={lineColor} stroke={p.bgGradient[0]} strokeWidth={2} />
            </Svg>
          ) : null}
        </View>
      </GestureDetector>
    </View>
  );
}

interface StaticProps {
  bars: Bar[];
  mode: ChartMode;
  width: number;
  height: number;
  geo: { min: number; max: number; n: number; xAt: (i: number) => number; yAt: (v: number) => number };
  pastW: number;
  band: ForecastBand | null;
  type: AssetType;
  lineColor: string;
}

const StaticChart = memo(function StaticChart({ bars, mode, width, height, geo, pastW, band, type, lineColor }: StaticProps) {
  const p = useTheme();
  const { xAt, yAt, min, max, n } = geo;
  const bottom = height - PAD.bottom;
  const lastX = xAt(n - 1);
  const last = bars[n - 1].close;

  // Izgara: 4 yatay çizgi + sağda fiyat etiketleri
  const ticks = [0, 1, 2, 3].map((i) => min + ((max - min) * (i + 0.5)) / 4);

  const linePath = bars.map((b, i) => `${i ? 'L' : 'M'}${xAt(i).toFixed(1)},${yAt(b.close).toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${lastX.toFixed(1)},${bottom} L${xAt(0).toFixed(1)},${bottom} Z`;

  // Tahmin konisi: son fiyattan başlayıp ufka doğru genişler (belirsizlik √t ile büyür)
  let bandArea = '';
  let bandMid = '';
  let bandEndX = 0;
  if (band) {
    const futureW = width - PAD.right - lastX;
    bandEndX = lastX + futureW;
    const steps = 16;
    const upper: string[] = [];
    const lower: string[] = [];
    const mid: string[] = [];
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const x = lastX + futureW * t;
      const spread = Math.sqrt(t);
      const m = last + (bandMidOf(band) - last) * t;
      upper.push(`${x.toFixed(1)},${yAt(m + (band.p90 - bandMidOf(band)) * spread).toFixed(1)}`);
      lower.push(`${x.toFixed(1)},${yAt(m - (bandMidOf(band) - band.p10) * spread).toFixed(1)}`);
      mid.push(`${s ? 'L' : 'M'}${x.toFixed(1)},${yAt(m).toFixed(1)}`);
    }
    bandArea = `M${upper.join(' L')} L${lower.reverse().join(' L')} Z`;
    bandMid = mid.join(' ');
  }

  const candleW = Math.max(1.5, Math.min(10, (pastW / n) * 0.62));
  const id = `area-${lineColor.replace('#', '')}`;

  return (
    <Svg width={width} height={height}>
      <Defs>
        <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={lineColor} stopOpacity={0.28} />
          <Stop offset="1" stopColor={lineColor} stopOpacity={0} />
        </LinearGradient>
      </Defs>

      {ticks.map((v) => (
        <G key={v}>
          <Line x1={0} x2={width - PAD.right + 4} y1={yAt(v)} y2={yAt(v)} stroke={p.separator} strokeWidth={1} />
          <SvgText x={width - PAD.right + 8} y={yAt(v) + 4} fontSize={10} fontFamily={font.medium} fill={p.textFaint}>
            {formatAxis(v)}
          </SvgText>
        </G>
      ))}

      {mode === 'line' ? (
        <>
          <Path d={areaPath} fill={`url(#${id})`} />
          <Path d={linePath} stroke={lineColor} strokeWidth={2} fill="none" strokeLinejoin="round" strokeLinecap="round" />
        </>
      ) : (
        bars.map((b, i) => {
          const rising = b.close >= b.open;
          const c = rising ? p.up : p.down;
          const x = xAt(i);
          const yO = yAt(b.open);
          const yC = yAt(b.close);
          return (
            <G key={b.date}>
              <Line x1={x} x2={x} y1={yAt(b.high)} y2={yAt(b.low)} stroke={c} strokeWidth={1} />
              <Rect
                x={x - candleW / 2}
                y={Math.min(yO, yC)}
                width={candleW}
                height={Math.max(1, Math.abs(yC - yO))}
                fill={c}
                rx={candleW > 4 ? 1.5 : 0}
              />
            </G>
          );
        })
      )}

      {band ? (
        <>
          {/* Bugün çizgisi */}
          <Line x1={lastX} x2={lastX} y1={PAD.top} y2={bottom} stroke={p.textFaint} strokeWidth={1} strokeDasharray="2 4" />
          <Path d={bandArea} fill={p.accent} fillOpacity={0.16} stroke={p.accent} strokeOpacity={0.35} strokeWidth={1} />
          <Path d={bandMid} stroke={p.accent} strokeWidth={2} strokeDasharray="5 4" fill="none" />
          <SvgText x={lastX + 4} y={height - 4} fontSize={10} fontFamily={font.medium} fill={p.textFaint}>
            bugün
          </SvgText>
          <SvgText x={bandEndX} y={height - 4} fontSize={10} fontFamily={font.semibold} fill={p.accent} textAnchor="end">
            +{band.horizon} gün
          </SvgText>
        </>
      ) : null}

      {/* Son fiyat noktası */}
      <Circle cx={lastX} cy={yAt(last)} r={3.5} fill={lineColor} />
    </Svg>
  );
});

function group(bars: Bar[], size: number): Bar[] {
  if (size <= 1) return bars;
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i += size) {
    const chunk = bars.slice(i, i + size);
    out.push({
      date: chunk[0].date,
      open: chunk[0].open,
      close: chunk[chunk.length - 1].close,
      high: Math.max(...chunk.map((b) => b.high)),
      low: Math.min(...chunk.map((b) => b.low)),
    });
  }
  return out;
}

const styles = StyleSheet.create({
  info: { minHeight: 34, justifyContent: 'center', gap: 1, marginBottom: 4 },
});
