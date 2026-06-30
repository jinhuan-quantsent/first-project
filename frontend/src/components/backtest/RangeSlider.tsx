/** 范围滑块 */
export function RangeSlider({ label, value, min, max, step = 1, unit = '', onChange }: {
  label?: string; value: number; min: number; max: number; step?: number; unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {label && <span className="w-24 shrink-0 text-gray-500 text-xs">{label}</span>}
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                   [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                   [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                   [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
      <span className="w-16 text-right text-xs font-mono text-gray-600 tabular-nums">
        {typeof value === 'number' ? value.toFixed(step < 1 ? 2 : 0) : value}{unit}
      </span>
    </div>
  );
}
