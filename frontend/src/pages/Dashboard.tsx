import { useEffect } from 'react';
import { useAppStore } from '../store';
import MultiIndexCards from '../components/dashboard/MultiIndexCards';
import IndexDetailPanel from '../components/dashboard/IndexDetailPanel';
import Top3Factors from '../components/dashboard/Top3Factors';
import SectorOverview from '../components/dashboard/SectorOverview';
import OpportunityRadar from '../components/dashboard/OpportunityRadar';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';

export default function Dashboard() {
  const {
    marketLoading,
    marketError,
    loadMultiIndex,
    selectedIndex,
  } = useAppStore();

  useEffect(() => {
    loadMultiIndex();
  }, [loadMultiIndex]);

  if (marketLoading) {
    return <LoadingSpinner size="lg" text="加载市场数据..." />;
  }

  if (marketError) {
    return <ErrorMessage message={marketError} onRetry={() => loadMultiIndex()} />;
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 md:space-y-6">
      {/* 页面标题 */}
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">大盘情绪仪表盘</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">实时监控市场情绪，辅助投资决策</p>
      </div>

      {/* 多指数卡片选择器 */}
      <MultiIndexCards />

      {/* 指数详情 + Top3因子 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <IndexDetailPanel indexCode={selectedIndex} />
        </div>
        <div>
          <Top3Factors indexCode={selectedIndex} />
        </div>
      </div>

      {/* 板块情绪 + 机会雷达 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectorOverview />
        <OpportunityRadar />
      </div>
    </div>
  );
}
