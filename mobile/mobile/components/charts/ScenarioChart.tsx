// 30 / 120 gün senaryo grafiği: son 60 günün fiyatı + iyimser / temel / kötümser üç yol.
// Çizgiler yalnızca renkle değil, desen (düz / kesik / noktalı) ve uç etiketleriyle de ayrılır.
import Svg, { Circle, G, Line, Path, Text as SvgText } from 'react-native-svg';

import type { AssetType, Scenario } from '@/api/types';
import { formatPrice } from '@/lib/format';
import { font } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

interface Props {
  closes: number[]; // son ~60 günün kapanışları
  scenario: Scenario;
  type: AssetType;
  width: number;
  height?: number;
}

const PAD = { top: 16, bottom: 22, right: 96 };

/** Bugünden hedef fiyata yumuşak eğri (smoothstep) */
function scenarioPath(last: number, target: number, days: number) {
  return Array.from({ length: days + 1 }, (_, i) => {
    const t = i / days;
    return last + (target - last) * t * t * (3 - 2 * t);
  });
}

export function ScenarioChart({ closes, scenario, type, width, height = 200 }: Props) {
  const p = useTheme();
  if (width <= 0 || closes.length < 2) return null;

  const last = closes[closes.length - 1];
  const days = scenario.horizon;
  const lines = [
    { key: 'bull', label: 'İyimser', value: scenario.bull, color: p.up, dash: undefined as string | undefined },
    { key: 'base', label: 'Temel', value: scenario.base, color: p.accent, dash: '6 4' },
    { key: 'bear', label: 'Kötümser', value: scenario.bear, color: p.down, dash: '2 4' },
  ];
  const paths = lines.map((l) => scenarioPath(last, l.value, days));

  const all = [...closes, ...paths.flat()];
  let min = Math.min(...all);
  let max = Math.max(...all);
  const pad = (max - min) * 0.06;
  min -= pad;
  max += pad;

  const plotW = width - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const pastW = plotW * 0.38; // geçmiş solda dar, gelecek geniş
  const futureW = plotW - pastW;
  const yAt = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * plotH;
  const xPast = (i: number) => (i / (closes.length - 1)) * pastW;
  const xFut = (i: number) => pastW + (i / days) * futureW;

  const past = closes.map((v, i) => `${i ? 'L' : 'M'}${xPast(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ');

  // Uç etiketleri üst üste binmesin
  const labelY = lines.map((l) => yAt(l.value));
  for (let i = 1; i < labelY.length; i++) if (labelY[i] - labelY[i - 1] < 26) labelY[i] = labelY[i - 1] + 26;

  return (
    <Svg width={width} height={height}>
      <Path d={past} stroke={p.textMuted} strokeWidth={1.8} fill="none" strokeLinejoin="round" />
      <Line x1={pastW} x2={pastW} y1={PAD.top} y2={height - PAD.bottom} stroke={p.textFaint} strokeDasharray="2 4" />
      <SvgText x={pastW} y={height - 6} fontSize={10} fontFamily={font.medium} fill={p.textFaint} textAnchor="middle">
        bugün
      </SvgText>
      <SvgText x={plotW} y={height - 6} fontSize={10} fontFamily={font.medium} fill={p.textFaint} textAnchor="end">
        +{days} gün
      </SvgText>

      {lines.map((l, li) => {
        const d = paths[li].map((v, i) => `${i ? 'L' : 'M'}${xFut(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ');
        return (
          <G key={l.key}>
            <Path d={d} stroke={l.color} strokeWidth={2.2} strokeDasharray={l.dash} fill="none" strokeLinecap="round" />
            <Circle cx={plotW} cy={yAt(l.value)} r={3.5} fill={l.color} />
            <SvgText x={plotW + 8} y={labelY[li] - 2} fontSize={10.5} fontFamily={font.semibold} fill={l.color}>
              {l.label}
            </SvgText>
            <SvgText x={plotW + 8} y={labelY[li] + 11} fontSize={10.5} fontFamily={font.medium} fill={p.textMuted}>
              {formatPrice(l.value, type)}
            </SvgText>
          </G>
        );
      })}
    </Svg>
  );
}
