import React from 'react';
import { Database, Binary } from 'lucide-react';

interface StatisticalProfilePanelProps {
  profileData: any;
}

export const StatisticalProfilePanel: React.FC<StatisticalProfilePanelProps> = ({ profileData }) => {
  // Helper for rendering the vertical histogram bars using clean SVG pathing
  const renderHistogram = (histogram: { bin_start: number; bin_end: number; count: number }[]) => {
    if (!histogram || histogram.length === 0) return null;
    const counts = histogram.map(h => h.count);
    const maxCount = Math.max(...counts, 1);

    const svgWidth = 270;
    const svgHeight = 110;
    const paddingLeft = 30;
    const paddingRight = 15;
    const paddingTop = 10;
    const paddingBottom = 20;

    const graphWidth = svgWidth - paddingLeft - paddingRight;
    const graphHeight = svgHeight - paddingTop - paddingBottom;
    const barWidth = graphWidth / histogram.length;

    return (
      <div className="flex flex-col items-center select-none">
        <svg width={svgWidth} height={svgHeight} className="overflow-visible font-sans text-[8px]">
          {/* Horizontal gridlines */}
          {[0, 0.5, 1].map((ratio, idx) => {
            const y = paddingTop + graphHeight * (1 - ratio);
            return (
              <g key={idx}>
                <line 
                  x1={paddingLeft} 
                  y1={y} 
                  x2={svgWidth - paddingRight} 
                  y2={y} 
                  stroke="#f1f5f9" 
                  strokeWidth={1}
                />
                <text x={paddingLeft - 5} y={y + 3} textAnchor="end" className="fill-slate-400 font-medium">
                  {ratio === 0 ? '0%' : ratio === 0.5 ? '5%' : '10%'}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {histogram.map((bin, i) => {
            const barHeight = (bin.count / maxCount) * graphHeight;
            const x = paddingLeft + i * barWidth;
            const y = paddingTop + graphHeight - barHeight;

            return (
              <g key={i} className="group cursor-pointer">
                <rect
                  x={x + 1}
                  y={y}
                  width={barWidth - 2}
                  height={Math.max(barHeight, 1)}
                  fill="#3b82f6"
                  className="transition-colors hover:fill-blue-600"
                  rx={1.5}
                />
                <title>{`Range: ${bin.bin_start.toLocaleString(undefined, {maximumFractionDigits: 1})} to ${bin.bin_end.toLocaleString(undefined, {maximumFractionDigits: 1})}\nCount: ${bin.count}`}</title>
              </g>
            );
          })}

          {/* X Axis line */}
          <line 
            x1={paddingLeft} 
            y1={paddingTop + graphHeight} 
            x2={svgWidth - paddingRight} 
            y2={paddingTop + graphHeight} 
            stroke="#e2e8f0"
          />

          {/* X Axis Tick Labels (Show 5 milestones) */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
            const binIdx = Math.min(Math.floor(ratio * (histogram.length - 1)), histogram.length - 1);
            const val = histogram[binIdx].bin_start;
            const x = paddingLeft + ratio * graphWidth;
            return (
              <text key={idx} x={x} y={paddingTop + graphHeight + 12} textAnchor="middle" className="fill-slate-400 font-medium">
                {val > 1000000 ? `${(val / 1000000).toFixed(1)}M` : val > 1000 ? `${(val / 1000).toFixed(0)}k` : val.toFixed(0)}
              </text>
            );
          })}
        </svg>
      </div>
    );
  };

  // Helper for rendering categorical horizontal bar distributions
  const renderCategoricalChart = (frequencies: { value: string; count: number; pct: number }[]) => {
    if (!frequencies || frequencies.length === 0) return null;
    
    // Filter out "(Other)" or "Other" items from the frequencies list
    const filteredFrequencies = frequencies.filter(f => f.value !== '(Other)' && f.value !== 'Other');
    if (filteredFrequencies.length === 0) return null;
    
    const maxPct = Math.max(...filteredFrequencies.map(f => f.pct), 0.01);
    const maxPctVal = maxPct * 100;
    const formatPct = (val: number) => {
      if (val === 0) return '0%';
      return val % 1 === 0 ? `${val}%` : `${val.toFixed(1)}%`;
    };

    return (
      <div className="w-full flex flex-col space-y-2 text-xs font-sans text-muted-foreground pr-2">
        {/* Dynamic visual scale matching normalized max pct */}
        <div className="flex justify-between pl-[90px] border-b border-slate-100 pb-1 text-[8px] text-slate-400 font-semibold uppercase tracking-wider">
          <span>{formatPct(0)}</span>
          <span>{formatPct(maxPctVal * 0.25)}</span>
          <span>{formatPct(maxPctVal * 0.5)}</span>
          <span>{formatPct(maxPctVal * 0.75)}</span>
          <span>{formatPct(maxPctVal)}</span>
        </div>

        <div className="space-y-1.5 pt-1">
          {filteredFrequencies.map((freq, i) => {
            const relativeWidth = `${(freq.pct / maxPct) * 100}%`;
            return (
              <div key={i} className="flex items-center group cursor-pointer">
                {/* Brand / Label Name */}
                <span className="w-[85px] text-right pr-3 font-medium text-slate-600 truncate text-[11px]" title={freq.value}>
                  {freq.value}
                </span>
                
                {/* Track bar */}
                <div className="flex-1 bg-slate-50 h-5 rounded-md border border-slate-100/50 overflow-hidden relative flex items-center">
                  <div 
                    style={{ width: relativeWidth }}
                    className="bg-blue-500 h-full rounded hover:bg-blue-600 transition-all duration-500"
                    title={`${freq.value}: ${freq.count} (${(freq.pct * 100).toFixed(1)}%)`}
                  />
                  <span className="absolute right-2 text-[9px] font-bold text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    {(freq.pct * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {profileData.columns.map((col: any, index: number) => {
        const isNumeric = col.numeric_stats !== null;
        const stats = isNumeric ? col.numeric_stats : col.categorical_stats;
        
        return (
          <div 
            key={index} 
            className="bg-card rounded-xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow"
          >
            {/* Styled tab-like header matching the Car ID layout */}
            <div className="bg-slate-50/50 border-b border-slate-200/80 px-5 py-2.5 flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="bg-blue-50 text-blue-600 p-1.5 rounded">
                  {isNumeric ? (
                    <Binary className="h-4 w-4" />
                  ) : (
                    <Database className="h-4 w-4" />
                  )}
                </div>
                <h3 className="font-bold text-slate-800 text-sm tracking-tight">
                  {col.column_name}
                </h3>
              </div>
              <span className="text-[10px] font-bold text-slate-500 uppercase bg-slate-100/70 border border-slate-200/50 px-2 py-0.5 rounded-full select-none">
                {col.dtype}
              </span>
            </div>

            {/* Content Section */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 p-5 min-h-[140px]">
              {/* 1. Left Panel: General stats */}
              <div className="md:col-span-3 space-y-2.5 pr-2 border-r border-slate-100 flex flex-col justify-center text-left">
                <div className="flex justify-between items-baseline text-xs">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Values:</span>
                  <span className="text-blue-600 font-bold">
                    {stats.values_count.toLocaleString()} ({Math.round(stats.values_pct * 100)}%)
                  </span>
                </div>
                <div className="flex justify-between items-baseline text-xs">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Missing:</span>
                  <span className="text-slate-600 font-bold">
                    {stats.missing_count > 0 
                      ? `${stats.missing_count.toLocaleString()} (${Math.round(stats.missing_pct * 100)}%)` 
                      : '---'}
                  </span>
                </div>
                <div className="flex justify-between items-baseline text-xs">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Distinct:</span>
                  <span className="text-blue-600 font-bold">
                    {stats.distinct_count.toLocaleString()} ({stats.distinct_pct < 0.01 ? '<1%' : `${Math.round(stats.distinct_pct * 100)}%`})
                  </span>
                </div>
                {isNumeric && (
                  <div className="flex justify-between items-baseline text-xs">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Zeroes:</span>
                    <span className="text-slate-500 font-bold">
                      {stats.zeroes_count > 0 
                        ? `${stats.zeroes_count.toLocaleString()} (${Math.round(stats.zeroes_pct * 100)}%)` 
                        : '--'}
                    </span>
                  </div>
                )}
              </div>

              {/* 2. Center Panel: Numeric quantiles & spread */}
              {isNumeric ? (
                <div className="md:col-span-5 grid grid-cols-2 gap-4 px-2 border-r border-slate-100 text-[11px]">
                  {/* Quantiles column */}
                  <div className="space-y-1">
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">MAX</span>
                      <span className="text-slate-700 font-semibold">{stats.max.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">95%</span>
                      <span className="text-slate-700 font-semibold">{stats.p95.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">Q3</span>
                      <span className="text-slate-700 font-semibold">{stats.q3.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">MEDIAN</span>
                      <span className="text-blue-600 font-bold">{stats.median.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">AVG</span>
                      <span className="text-slate-700 font-semibold">{stats.avg.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">Q1</span>
                      <span className="text-slate-700 font-semibold">{stats.q1.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">5%</span>
                      <span className="text-slate-700 font-semibold">{stats.p5.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400 font-medium">MIN</span>
                      <span className="text-slate-700 font-semibold">{stats.min.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                  </div>

                  {/* Spread column */}
                  <div className="space-y-1">
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">RANGE</span>
                      <span className="text-slate-700 font-semibold">{stats.range.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">IQR</span>
                      <span className="text-slate-700 font-semibold">{stats.iqr.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">STD</span>
                      <span className="text-slate-700 font-semibold">{stats.std.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">VAR</span>
                      <span className="text-slate-700 font-semibold">
                        {stats.var > 1000 ? `${(stats.var / 1000).toFixed(0)}k` : stats.var.toLocaleString(undefined, {maximumFractionDigits: 2})}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">KURT.</span>
                      <span className="text-slate-700 font-semibold">{stats.kurt.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-slate-50 pb-0.5">
                      <span className="text-slate-400 font-medium">SKEW</span>
                      <span className="text-blue-600 font-bold">{stats.skew.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400 font-medium">SUM</span>
                      <span className="text-slate-700 font-semibold">
                        {stats.sum > 1000000 ? `${(stats.sum / 1000000).toFixed(1)}M` : stats.sum.toLocaleString(undefined, {maximumFractionDigits: 0})}
                      </span>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* 3. Right Panel: Visual chart distributions */}
              <div className={`${isNumeric ? 'md:col-span-4' : 'md:col-span-9'} flex items-center justify-center pl-2`}>
                {isNumeric ? (
                  renderHistogram(stats.histogram)
                ) : (
                  renderCategoricalChart(stats.frequencies)
                )}
              </div>
            </div>

            {/* Interpretation advice notes bar */}
            {col.interpretation && col.interpretation.length > 0 && (
              <div className="bg-slate-50/30 border-t border-slate-100 px-5 py-2 text-[11px] text-muted-foreground flex flex-col space-y-1 text-left">
                {col.interpretation.map((msg: string, idx: number) => (
                  <div key={idx} className="flex items-center space-x-2 text-slate-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                    <span>{msg}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
