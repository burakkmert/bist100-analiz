// Küçük çizgi grafik (gölgeli alanla). Ayrıntılı grafikler 3–4. haftada ayrı bileşen olacak.
import Svg, { Defs, LinearGradient as SvgLinearGradient, Path, Stop } from 'react-native-svg';

interface Props {
  data: number[];
  width: number;
  height: number;
  color: string;
}

export function Sparkline({ data, width, height, color }: Props) {
  if (data.length < 2 || width <= 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * width, height - ((v - min) / span) * (height - 4) - 2]);
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height} L0,${height} Z`;
  const id = `spark-${color.replace('#', '')}`;

  return (
    <Svg width={width} height={height}>
      <Defs>
        <SvgLinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color} stopOpacity={0.35} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </SvgLinearGradient>
      </Defs>
      <Path d={area} fill={`url(#${id})`} />
      <Path d={line} stroke={color} strokeWidth={2} fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}
