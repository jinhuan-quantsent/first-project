/**
 * NavHistoryList — 净值历史列表组件
 */
import { useMemo } from 'react';

export default function NavHistoryList({ data }: { data: { date: string; nav: number; daily_return?: number }[] }) {
  const sorted = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data].reverse().slice(0, 15);
  }, [data]);

  if (sorted.length === 0) {
    return (
      <p className="text-[10px] text-gray-300 text-center py-2">暂无净值明细</p>
    );
  }

  return (
    <div className="max-h-[180px] overflow-y-auto">
      <table className="w-full text-[10px]">
        <thead className="sticky top-0 bg-gray-50">
          <tr className="text-gray-400 border-b border-gray-100">
            <th className="py-1 text-left font-medium">日期</th>
            <th className="py-1 text-right font-medium">净值</th>
            <th className="py-1 text-right font-medium">涨跌幅</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, i) => {
            const ret = item.daily_return ?? 0;
            const retCls = ret > 0 ? 'text-red-500' : ret < 0 ? 'text-green-500' : 'text-gray-400';
            const retSign = ret > 0 ? '+' : '';
            const dateStr = item.date.length === 8
              ? `${item.date.slice(4, 6)}-${item.date.slice(6, 8)}`
              : item.date.slice(5);
            return (
              <tr key={i} className="border-b border-gray-50">
                <td className="py-1 text-gray-500 font-mono">{dateStr}</td>
                <td className="py-1 text-right text-gray-600 font-mono">{item.nav.toFixed(4)}</td>
                <td className={`py-1 text-right font-mono ${retCls}`}>
                  {retSign}{ret.toFixed(2)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
