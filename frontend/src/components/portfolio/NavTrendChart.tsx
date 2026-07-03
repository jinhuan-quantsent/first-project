/**
 * NavTrendChart — SVG 净值走势图组件
 */
import { useMemo } from 'react';

export default function NavTrendChart({ data }: { data: { date: string; nav: number }[] }) {
  const width = 680;
  const height = 140;
  const padX = 40;
  const padY = 20;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const validData = useMemo(() => {
    if (!data || data.length < 2) return [];
    return data.filter(d => d.nav > 0);
  }, [data]);

  if (validData.length < 2) {
    return (
      <div className="flex items-center justify-center h-24 text-xs text-gray-300">
        暂无走势数据
      </div>
    );
  }

  const navs = validData.map(d => d.nav);
  const minNav = Math.min(...navs);
  const maxNav = Math.max(...navs);
  const rangeNav = maxNav - minNav || 1;

  const points = validData.map((d, i) => {
    const x = padX + (i / (validData.length - 1)) * innerW;
    const y = padY + innerH - ((d.nav - minNav) / rangeNav) * innerH;
    return { x, y, date: d.date, nav: d.nav };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaPath = `M${points[0].x},${padY + innerH} ` +
    points.map(p => `L${p.x},${p.y}`).join(' ') +
    ` L${points[points.length - 1].x},${padY + innerH} Z`;

  const strokeColor = '#14B8A6';

  const xLabels = points.filter((_, i) => i % Math.max(1, Math.floor(points.length / 5)) === 0 || i === points.length - 1);

  const ySteps = 4;
  const yLabels = Array.from({ length: ySteps + 1 }, (_, i) => {
    const val = minNav + (rangeNav * i) / ySteps;
    const y = padY + innerH - (i / ySteps) * innerH;
    return { val, y };
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
      <defs>
        <linearGradient id="navAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {yLabels.map((yl, i) => (
        <g key={i}>
          <line x1={padX} y1={yl.y} x2={width - padX} y2={yl.y} stroke="#E2E8F0" strokeWidth="0.5" />
          <text x={padX - 4} y={yl.y + 3} textAnchor="end" fill="#94A3B8" fontSize="8">{yl.val.toFixed(4)}</text>
        </g>
      ))}
      <path d={areaPath} fill="url(#navAreaGrad)" />
      <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="1.5" />
      {points.length > 0 && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={strokeColor} />
      )}
      {xLabels.map((p, i) => (
        <text key={i} x={p.x} y={height - 2} textAnchor="middle" fill="#94A3B8" fontSize="7">
          {p.date.slice(5)}
        </text>
      ))}
    </svg>
  );
}
