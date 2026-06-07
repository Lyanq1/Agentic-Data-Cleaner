import React, { useMemo, useState } from 'react';
import { Database, Binary, Hash, Columns, Copy, Key, AlertTriangle, ListFilter } from 'lucide-react';

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

  const semanticProfile = profileData.semantic_profile;
  const [showThinking, setShowThinking] = useState(false);

  const logicalGroups = useMemo(() => {
    const groups: Record<string, string[]> = {};
    if (semanticProfile?.columns) {
      Object.entries(semanticProfile.columns).forEach(([colName, detail]: [string, any]) => {
        const grp = detail.logical_group || 'Uncategorized';
        if (!groups[grp]) {
          groups[grp] = [];
        }
        groups[grp].push(colName);
      });
    }
    return groups;
  }, [semanticProfile]);

  const columns = Array.isArray(profileData.columns) 
    ? profileData.columns 
    : Object.values(profileData.columns || {});

  return (
    <div className="space-y-4">
      {/* Dataset Profile Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card rounded-xl border border-slate-200 p-5 shadow-sm text-left flex items-center space-x-4">
          <div className="p-3 rounded-lg bg-blue-50 text-blue-600">
            <Hash className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-800">
              {profileData.total_rows?.toLocaleString() ?? 0}
            </div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Total Rows
            </div>
          </div>
        </div>

        <div className="bg-card rounded-xl border border-slate-200 p-5 shadow-sm text-left flex items-center space-x-4">
          <div className="p-3 rounded-lg bg-indigo-50 text-indigo-600">
            <Columns className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-800">
              {profileData.total_columns ?? 0}
            </div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Total Columns
            </div>
          </div>
        </div>

        <div className="bg-card rounded-xl border border-slate-200 p-5 shadow-sm text-left flex items-center space-x-4">
          <div className={`p-3 rounded-lg ${(profileData.duplicate_rows ?? 0) > 0 ? 'bg-amber-50 text-amber-600' : 'bg-slate-50 text-slate-500'}`}>
            <Copy className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-800">
              {profileData.duplicate_rows?.toLocaleString() ?? 0}
            </div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Duplicate Rows
            </div>
          </div>
        </div>
      </div>

      {/* Dataset Structural Highlights */}
      {((profileData.pk_candidates && profileData.pk_candidates.length > 0) ||
        (profileData.near_unique_columns && profileData.near_unique_columns.length > 0) ||
        (profileData.categorical_columns && profileData.categorical_columns.length > 0) ||
        (profileData.high_null_columns && profileData.high_null_columns.length > 0)) && (
        <div className="bg-card rounded-xl border border-slate-200 p-6 text-left shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-800 tracking-tight border-b border-slate-100 pb-2">
            Dataset Structural Highlights
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            {profileData.pk_candidates && profileData.pk_candidates.length > 0 && (
              <div className="space-y-1.5 p-3 rounded-lg bg-slate-50/50 border border-slate-100">
                <div className="flex items-center space-x-1.5 text-slate-700 font-semibold">
                  <Key className="h-4 w-4 text-amber-500" />
                  <span>Primary Key Candidates</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {profileData.pk_candidates.map((col: string, idx: number) => (
                    <span key={idx} className="font-mono text-[10px] bg-amber-50 text-amber-800 border border-amber-200/50 px-1.5 py-0.5 rounded">
                      {col}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {profileData.near_unique_columns && profileData.near_unique_columns.length > 0 && (
              <div className="space-y-1.5 p-3 rounded-lg bg-slate-50/50 border border-slate-100">
                <div className="flex items-center space-x-1.5 text-slate-700 font-semibold">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <span>Near-Unique Columns (with duplicates)</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {profileData.near_unique_columns.map((col: string, idx: number) => (
                    <span key={idx} className="font-mono text-[10px] bg-slate-100 text-slate-700 border border-slate-200/50 px-1.5 py-0.5 rounded">
                      {col}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {profileData.categorical_columns && profileData.categorical_columns.length > 0 && (
              <div className="space-y-1.5 p-3 rounded-lg bg-slate-50/50 border border-slate-100">
                <div className="flex items-center space-x-1.5 text-slate-700 font-semibold">
                  <ListFilter className="h-4 w-4 text-blue-500" />
                  <span>Categorical Columns</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {profileData.categorical_columns.map((col: string, idx: number) => (
                    <span key={idx} className="font-mono text-[10px] bg-blue-50 text-blue-800 border border-blue-200/50 px-1.5 py-0.5 rounded">
                      {col}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {profileData.high_null_columns && profileData.high_null_columns.length > 0 && (
              <div className="space-y-1.5 p-3 rounded-lg bg-slate-50/50 border border-slate-100">
                <div className="flex items-center space-x-1.5 text-slate-700 font-semibold">
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                  <span>High Null Columns (&gt; 50% missing)</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {profileData.high_null_columns.map((col: string, idx: number) => (
                    <span key={idx} className="font-mono text-[10px] bg-red-50 text-red-800 border border-red-200/50 px-1.5 py-0.5 rounded">
                      {col}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Dataset Semantic Context */}
      {semanticProfile && (
        <div className="bg-card rounded-xl border border-slate-200 overflow-hidden shadow-sm p-6 text-left space-y-4">
          <h2 className="text-base font-bold text-slate-800 tracking-tight border-b border-slate-100 pb-2">
            Dataset Semantic Context
          </h2>
          
          {/* Table Summary */}
          {semanticProfile.table_summary && (
            <div className="space-y-1">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Table Summary
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed font-sans">
                {semanticProfile.table_summary}
              </p>
            </div>
          )}

          {/* Detected Logical Groups */}
          {Object.keys(logicalGroups).length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Detected Logical Groups
              </h3>
              <div className="border rounded-lg overflow-hidden bg-white">
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/75 border-b border-slate-200">
                      <th className="text-left p-2.5 font-semibold text-slate-500 w-[220px]">Logical Group</th>
                      <th className="text-left p-2.5 font-semibold text-slate-500">Associated Columns</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {Object.entries(logicalGroups).map(([groupName, cols], i) => (
                      <tr key={i} className="hover:bg-slate-50/30">
                        <td className="p-2.5 align-top font-medium text-slate-600">{groupName}</td>
                        <td className="p-2.5 align-top">
                          <div className="flex flex-wrap gap-1.5">
                            {cols.map((colName, idx) => (
                              <span key={idx} className="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                                {colName}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* LLM Thinking (Chain of Thought) */}
          {semanticProfile.thinking && (
            <div className="space-y-2 pt-2">
              <button
                type="button"
                onClick={() => setShowThinking(!showThinking)}
                className="text-xs font-medium text-blue-600 hover:text-blue-500 cursor-pointer"
              >
                {showThinking ? 'Hide LLM Chain of Thought' : 'Show LLM Chain of Thought'}
              </button>
              {showThinking && (
                <div className="bg-slate-950 text-white rounded-lg p-4 font-mono text-md leading-relaxed max-h-64 overflow-y-auto custom-scrollbar">
                  {semanticProfile.thinking.split('\n').map((line: string, i: number) => (
                    <div key={i} className="min-h-[1.2rem]">
                      {line}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {columns.map((col: any, index: number) => {
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

            {/* Sample Values & Detected Patterns */}
            {((col.sample_values && col.sample_values.length > 0) || (col.detected_patterns && col.detected_patterns.length > 0)) && (
              <div className="border-t border-slate-100 px-5 py-4 bg-slate-50/10 text-left space-y-3">
                {col.detected_patterns && col.detected_patterns.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                      Detected Patterns
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {col.detected_patterns.map((pat: string, idx: number) => (
                        <span key={idx} className="font-mono text-[11px] bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded">
                          {pat}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {col.sample_values && col.sample_values.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                      Representative Samples
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {col.sample_values.map((val: any, idx: number) => (
                        <span key={idx} className="font-mono text-[11px] bg-slate-100/65 text-slate-600 border border-slate-200 px-2 py-0.5 rounded max-w-xs truncate" title={val === null || val === undefined ? 'null' : String(val)}>
                          {val === null || val === undefined ? <em className="text-slate-400 font-sans">null</em> : String(val)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Semantic Profile Parallel Reason Table */}
            {(() => {
              const semanticDetail = profileData.semantic_profile?.columns?.[col.column_name];
              if (!semanticDetail) return null;
              
              return (
                <div className="border-t border-slate-100 px-5 py-4 bg-slate-50/20 text-left">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                    Semantic Analysis
                  </h4>
                  <div className="border rounded-lg overflow-hidden bg-white">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-slate-50/75 border-b border-slate-200">
                          <th className="text-left p-2.5 font-semibold text-slate-500 w-[220px]">Property & Expected Value</th>
                          <th className="text-left p-2.5 font-semibold text-slate-500">Business Context / Reason</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {semanticDetail.description && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600">Description</td>
                            <td className="p-2.5 align-top text-slate-600">{semanticDetail.description}</td>
                          </tr>
                        )}

                        {semanticDetail.allow_missing !== undefined && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600 flex items-center gap-2">
                              <span>Allow Missing</span>
                              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                semanticDetail.allow_missing 
                                  ? 'bg-slate-100 text-slate-700' 
                                  : 'bg-slate-200 text-slate-800'
                              }`}>
                                {semanticDetail.allow_missing ? 'True' : 'False'}
                              </span>
                            </td>
                            <td className="p-2.5 align-top text-slate-600">
                              {semanticDetail.allow_missing_reason || '—'}
                            </td>
                          </tr>
                        )}
                        {semanticDetail.expected_type && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600 flex items-center gap-2">
                              <span>Expected Type</span>
                              <span className="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                                {semanticDetail.expected_type}
                              </span>
                            </td>
                            <td className="p-2.5 align-top text-slate-600">
                              {semanticDetail.expected_type_reason || '—'}
                            </td>
                          </tr>
                        )}
                        {semanticDetail.potential_dmv && semanticDetail.potential_dmv.length > 0 && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600 flex flex-col gap-1.5">
                              <span>Potential DMVs</span>
                              <div className="flex flex-wrap gap-1">
                                {semanticDetail.potential_dmv.map((dmv: string, i: number) => (
                                  <span key={i} className="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                                    {dmv}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="p-2.5 align-top text-slate-600">
                              {semanticDetail.potential_dmv_reason || '—'}
                            </td>
                          </tr>
                        )}
                        {semanticDetail.expected_str_pattern && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600 flex items-center gap-2">
                              <span>Expected Pattern</span>
                              <span className="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                                {semanticDetail.expected_str_pattern}
                              </span>
                            </td>
                            <td className="p-2.5 align-top text-slate-600">
                              {semanticDetail.expected_str_pattern_reason || '—'}
                            </td>
                          </tr>
                        )}
                        {semanticDetail.relationships && semanticDetail.relationships.length > 0 && (
                          <tr className="hover:bg-slate-50/30">
                            <td className="p-2.5 align-top font-medium text-slate-600 flex flex-col gap-1.5">
                              <span>Relationships</span>
                              <div className="flex flex-col gap-1">
                                {semanticDetail.relationships.map((rel: string, i: number) => (
                                  <span key={i} className="font-mono text-[10px] bg-slate-50 text-slate-700 px-1.5 py-0.5 rounded inline-block max-w-max">
                                    {rel}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="p-2.5 align-top text-slate-600">
                              Functional dependencies detected for this column.
                            </td>
                          </tr>
                        )}
                        {semanticDetail.is_error && (
                          <tr>
                            <td className="p-2.5 align-top font-medium text-red-600 flex flex-col gap-1.5">
                              <span>Quality Error</span>
                              <div className="flex flex-wrap gap-1">
                                {(semanticDetail.error_types || []).map((err: string, i: number) => (
                                  <span key={i} className="text-[10px] font-bold uppercase text-red-600">
                                    {err}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="p-2.5 align-top text-red-600">
                              Reason: {semanticDetail.error_reason || 'Anomalies detected in column data.'}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}

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
