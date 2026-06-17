import React, { useMemo, useState, useEffect } from 'react';
import { FileText, ArrowUp, ArrowDown, ListFilter, ChevronDown, Search } from 'lucide-react';

interface FormatAnomaliesPanelProps {
  dataProfile: any;
  previewData: any;
}

const COLOR_PALETTE = [
  'bg-amber-100/50 text-amber-900 ring-amber-200/50',
  'bg-blue-100/50 text-blue-900 ring-blue-200/50',
  'bg-emerald-100/50 text-emerald-900 ring-emerald-200/50',
  'bg-purple-100/50 text-purple-900 ring-purple-200/50',
  'bg-pink-100/50 text-pink-900 ring-pink-200/50',
  'bg-indigo-100/50 text-indigo-900 ring-indigo-200/50',
  'bg-cyan-100/50 text-cyan-900 ring-cyan-200/50',
  'bg-rose-100/50 text-rose-900 ring-rose-200/50',
  'bg-orange-100/50 text-orange-900 ring-orange-200/50',
  'bg-teal-100/50 text-teal-900 ring-teal-200/50',
  'bg-sky-100/50 text-sky-900 ring-sky-200/50',
  'bg-lime-100/50 text-lime-900 ring-lime-200/50',
  'bg-fuchsia-100/50 text-fuchsia-900 ring-fuchsia-200/50',
  'bg-violet-100/50 text-violet-900 ring-violet-200/50',
  'bg-red-100/50 text-red-900 ring-red-200/50',
];

const abstractFormat = (val: any) => {
  if (val == null) return "";
  return String(val).replace(/[0-9]/g, 'D').replace(/[a-zA-Z]/g, 'A');
};

export const FormatAnomaliesPanel: React.FC<FormatAnomaliesPanelProps> = ({
  dataProfile,
  previewData,
}) => {
  const anomaliesMap = useMemo(() => {
    if (!dataProfile?.columns) return {};
    const map: Record<string, Record<string, string>> = {};
    for (const [colName, colStat] of Object.entries(dataProfile.columns)) {
      const stats = (colStat as any).categorical_stats;
      if (stats?.format_anomalies && stats.format_anomalies.length > 0) {
        map[colName] = {};
        stats.format_anomalies.forEach((anom: any, idx: number) => {
          map[colName][anom.format_pattern] = COLOR_PALETTE[idx % COLOR_PALETTE.length];
        });
      }
    }
    return map;
  }, [dataProfile]);

  const anomalousCols = Object.keys(anomaliesMap);
  const rows = previewData?.rows || [];

  // Sorting & Filtering State
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' | null }>({ key: '', direction: null });
  const [selectedFilters, setSelectedFilters] = useState<Record<string, Set<any>>>({});
  const [selectedColorFilters, setSelectedColorFilters] = useState<Record<string, Set<string>>>({});
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [expandedSection, setExpandedSection] = useState<'color' | 'value'>('value');
  const [filterSearchText, setFilterSearchText] = useState('');

  // Reset all filters & sorting states when new previewData is loaded (prevents stale filter conflicts)
  useEffect(() => {
    setSelectedFilters({});
    setSelectedColorFilters({});
    setSortConfig({ key: '', direction: null });
    setActiveDropdown(null);
    setFilterSearchText('');
  }, [previewData]);

  // Helper to open dropdown and auto-expand correct section
  const openDropdown = (col: string) => {
    setActiveDropdown(col);
    setFilterSearchText('');
    if (anomaliesMap[col]) {
      setExpandedSection('color');
    } else {
      setExpandedSection('value');
    }
  };

  // Pre-calculate unique values for each column
  const columnUniqueValuesMap = useMemo(() => {
    const map: Record<string, any[]> = {};
    previewData?.columns?.forEach((col: string) => {
      const values = rows.map((r: any) => r[col]);
      const unique = Array.from(new Set(values));
      map[col] = unique.sort((a, b) => {
        if (a === null || a === undefined) return 1;
        if (b === null || b === undefined) return -1;
        const numA = Number(a);
        const numB = Number(b);
        if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
        return String(a).localeCompare(String(b));
      });
    });
    return map;
  }, [rows, previewData?.columns]);

  // Pre-calculate unique colors for each column (by format pattern + default)
  const columnUniqueColorsMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    previewData?.columns?.forEach((col: string) => {
      if (anomaliesMap[col]) {
        map[col] = [...Object.keys(anomaliesMap[col]), '__default__'];
      } else {
        map[col] = [];
      }
    });
    return map;
  }, [anomaliesMap, previewData?.columns]);

  // Handle Sort
  const handleSort = (col: string, direction: 'asc' | 'desc') => {
    setSortConfig({ key: col, direction });
  };

  // Handle Value Filter Toggle
  const handleValueFilterToggle = (col: string, val: any) => {
    setSelectedFilters(prev => {
      const currentSet = prev[col] ? new Set(prev[col]) : new Set(columnUniqueValuesMap[col]);
      if (currentSet.has(val)) {
        currentSet.delete(val);
      } else {
        currentSet.add(val);
      }

      if (currentSet.size === columnUniqueValuesMap[col]?.length) {
        const next = { ...prev };
        delete next[col];
        return next;
      }

      return { ...prev, [col]: currentSet };
    });

    // Clear color filter on this column to avoid filter conflict
    setSelectedColorFilters(prev => {
      if (!prev[col]) return prev;
      const next = { ...prev };
      delete next[col];
      return next;
    });
  };

  // Handle Color Filter Toggle
  const handleColorFilterToggle = (col: string, pattern: string) => {
    setSelectedColorFilters(prev => {
      const currentSet = prev[col] ? new Set(prev[col]) : new Set(columnUniqueColorsMap[col]);
      if (currentSet.has(pattern)) {
        currentSet.delete(pattern);
      } else {
        currentSet.add(pattern);
      }

      if (currentSet.size === columnUniqueColorsMap[col]?.length) {
        const next = { ...prev };
        delete next[col];
        return next;
      }

      return { ...prev, [col]: currentSet };
    });

    // Clear value filter on this column to avoid filter conflict
    setSelectedFilters(prev => {
      if (!prev[col]) return prev;
      const next = { ...prev };
      delete next[col];
      return next;
    });
  };

  // Select all / clear all values helper
  const handleSelectAllValues = (col: string) => {
    setSelectedFilters(prev => {
      const next = { ...prev };
      delete next[col];
      return next;
    });
    setSelectedColorFilters(prev => {
      if (!prev[col]) return prev;
      const next = { ...prev };
      delete next[col];
      return next;
    });
  };

  const handleClearAllValues = (col: string) => {
    setSelectedFilters(prev => ({
      ...prev,
      [col]: new Set()
    }));
    setSelectedColorFilters(prev => {
      if (!prev[col]) return prev;
      const next = { ...prev };
      delete next[col];
      return next;
    });
  };

  // Clear all filters of a column
  const handleClearColumnFilters = (col: string) => {
    setSelectedFilters(prev => {
      const next = { ...prev };
      delete next[col];
      return next;
    });
    setSelectedColorFilters(prev => {
      const next = { ...prev };
      delete next[col];
      return next;
    });
  };

  // Reset all filters & sorting
  const handleResetAll = () => {
    setSelectedFilters({});
    setSelectedColorFilters({});
    setSortConfig({ key: '', direction: null });
    setActiveDropdown(null);
    setFilterSearchText('');
  };

  // Apply filters when OK is clicked, taking search results into account if active
  const handleOkClick = (col: string) => {
    if (filterSearchText) {
      const colUniqueVals = columnUniqueValuesMap[col] || [];
      const filteredVals = colUniqueVals.filter((v: any) => {
        const str = v === null || v === undefined ? '(blanks)' : String(v).toLowerCase();
        return str.includes(filterSearchText.toLowerCase());
      });

      const checkedFilteredVals = filteredVals.filter(val => {
        return selectedFilters[col] ? selectedFilters[col].has(val) : true;
      });

      setSelectedFilters(prev => ({
        ...prev,
        [col]: new Set(checkedFilteredVals)
      }));

      // Clear color filter on this column to avoid filter conflict
      setSelectedColorFilters(prev => {
        if (!prev[col]) return prev;
        const next = { ...prev };
        delete next[col];
        return next;
      });
    }
    setActiveDropdown(null);
    setFilterSearchText('');
  };

  // Derived processed (filtered & sorted) rows
  const processedRows = useMemo(() => {
    let result = [...rows];

    // Value filters
    Object.entries(selectedFilters).forEach(([col, allowedSet]) => {
      result = result.filter(row => allowedSet.has(row[col]));
    });

    // Color filters
    Object.entries(selectedColorFilters).forEach(([col, allowedColors]) => {
      result = result.filter(row => {
        const val = row[col];
        const pattern = abstractFormat(val);
        const hasHighlight = anomaliesMap[col] && anomaliesMap[col][pattern];
        const actualColorKey = hasHighlight ? pattern : '__default__';
        return allowedColors.has(actualColorKey);
      });
    });

    // Sorting
    if (sortConfig.key && sortConfig.direction) {
      const { key, direction } = sortConfig;

      const getSortValue = (val: any) => {
        if (val === null || val === undefined) return null;
        const num = Number(val);
        if (!isNaN(num)) return num;

        const cleanStr = String(val).trim();
        const match = cleanStr.match(/^-?[0-9.]+/);
        if (match) {
          const parsed = parseFloat(match[0]);
          if (!isNaN(parsed)) return parsed;
        }
        return String(val).toLowerCase();
      };

      result.sort((a, b) => {
        const valA = a[key];
        const valB = b[key];

        if ((valA === null || valA === undefined) && (valB === null || valB === undefined)) return 0;
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;

        const parsedA = getSortValue(valA);
        const parsedB = getSortValue(valB);

        if (typeof parsedA === 'number' && typeof parsedB === 'number') {
          return direction === 'asc' ? parsedA - parsedB : parsedB - parsedA;
        }

        const strA = String(parsedA);
        const strB = String(parsedB);
        return direction === 'asc' ? strA.localeCompare(strB) : strB.localeCompare(strA);
      });
    }

    return result;
  }, [rows, selectedFilters, selectedColorFilters, sortConfig, anomaliesMap]);

  const totalCount = rows.length;
  const filteredCount = processedRows.length;
  const isAnyFilterActive = Object.keys(selectedFilters).length > 0 || Object.keys(selectedColorFilters).length > 0 || !!sortConfig.key;

  if (anomalousCols.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 h-full flex flex-col items-center justify-center bg-slate-50/50">
        <FileText className="w-10 h-10 mb-3 text-slate-300" />
        <h3 className="font-semibold text-slate-700">No Formatting Anomalies Detected</h3>
        <p className="text-xs mt-1">The profiler did not find any multi-format discrepancies in string columns.</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-white text-slate-800 relative">
      
      {/* Click-outside backdrop */}
      {activeDropdown && (
        <div 
          className="fixed inset-0 z-20 cursor-default" 
          onClick={() => {
            setActiveDropdown(null);
            setFilterSearchText('');
          }} 
        />
      )}

      {/* Control / Reset Bar */}
      <div className="flex justify-between items-center px-4 py-2 border-b border-slate-100 bg-slate-50/50 text-xs shrink-0 select-none">
        <div className="text-slate-500">
          Showing <span className="font-semibold text-slate-700">{filteredCount}</span> of <span className="font-semibold text-slate-700">{totalCount}</span> rows
        </div>
        {isAnyFilterActive && (
          <button 
            onClick={handleResetAll} 
            className="text-blue-600 hover:text-blue-700 font-semibold hover:underline flex items-center gap-1 transition-all"
          >
            Clear all filters & sorting
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 p-4 flex flex-col">
        {rows.length > 0 ? (
          processedRows.length > 0 ? (
            <div className="border rounded-lg overflow-auto ring-1 ring-slate-100 flex-1 relative custom-scrollbar">
              <table className="w-full text-xs text-left whitespace-nowrap border-collapse">
                <thead className="bg-slate-50 sticky top-0 z-20 shadow-sm select-none">
                  <tr>
                    <th className="px-3 py-2.5 border-b font-semibold text-slate-600 bg-slate-50 w-12 text-center text-[10px] uppercase tracking-wider sticky top-0 z-10 shadow-[inset_0_-1px_0_rgba(226,232,240,1)]">
                      Row
                    </th>
                    {previewData?.columns?.map((col: string, index: number) => {
                      const isFiltered = !!selectedFilters[col] || !!selectedColorFilters[col];
                      const isSorted = sortConfig.key === col && sortConfig.direction;
                      const hasColorOptions = !!anomaliesMap[col];
                      
                      const colUniqueVals = columnUniqueValuesMap[col] || [];
                      const filteredUniqueVals = filterSearchText
                        ? colUniqueVals.filter((v: any) => {
                            const str = v === null || v === undefined ? '(blanks)' : String(v).toLowerCase();
                            return str.includes(filterSearchText.toLowerCase());
                          })
                        : colUniqueVals;

                      // Dynamically position dropdown to prevent clipping on the viewport edges
                      const isLeftHalf = index < (previewData?.columns?.length || 0) / 2;
                      const alignmentClass = isLeftHalf ? 'left-0' : 'right-0';

                      return (
                        <th 
                          key={col} 
                          className={`px-3 py-2.5 border-b font-semibold text-slate-600 bg-slate-50 relative group cursor-pointer select-none min-w-[120px] shadow-[inset_0_-1px_0_rgba(226,232,240,1)] ${
                            anomalousCols.includes(col) ? 'text-amber-700' : ''
                          }`}
                          onClick={(e) => {
                            if ((e.target as HTMLElement).closest('.dropdown-menu')) return;
                            if (activeDropdown === col) {
                              setActiveDropdown(null);
                              setFilterSearchText('');
                            } else {
                              openDropdown(col);
                            }
                          }}
                        >
                          <div className="flex items-center justify-between gap-1.5 py-0.5">
                            <span className="truncate">{col}</span>
                            <div className="flex items-center gap-1 shrink-0">
                              {isSorted && (
                                sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3 text-blue-600 font-semibold" /> : <ArrowDown className="w-3 h-3 text-blue-600 font-semibold" />
                              )}
                              {isFiltered && <ListFilter className="w-3 h-3 text-blue-600 font-semibold" />}
                              {!isSorted && !isFiltered && (
                                <ChevronDown className="w-3 h-3 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                              )}
                            </div>
                          </div>

                          {/* Dropdown Menu */}
                          {activeDropdown === col && (
                            <div 
                              className={`absolute ${alignmentClass} top-full mt-1 w-64 max-h-[380px] overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg z-30 text-slate-700 font-normal normal-case dropdown-menu flex flex-col pointer-events-auto cursor-default py-1 custom-scrollbar`}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {/* Sort Section */}
                              <div className="py-1">
                                <button
                                  onClick={() => handleSort(col, 'asc')}
                                  className={`flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-slate-50 text-xs ${
                                    sortConfig.key === col && sortConfig.direction === 'asc' ? 'bg-blue-50/50 font-semibold text-blue-600' : ''
                                  }`}
                                >
                                  <ArrowUp className="w-3.5 h-3.5" />
                                  Sort Ascending
                                </button>
                                <button
                                  onClick={() => handleSort(col, 'desc')}
                                  className={`flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-slate-50 text-xs ${
                                    sortConfig.key === col && sortConfig.direction === 'desc' ? 'bg-blue-50/50 font-semibold text-blue-600' : ''
                                  }`}
                                >
                                  <ArrowDown className="w-3.5 h-3.5" />
                                  Sort Descending
                                </button>
                              </div>

                              {/* Filter by Color Accordion Section */}
                              {hasColorOptions && (
                                <div className="border-t border-slate-100">
                                  <button
                                    onClick={() => setExpandedSection(expandedSection === 'color' ? 'value' : 'color')}
                                    className="w-full px-3 py-2 text-left text-[9px] font-bold text-slate-400 hover:text-slate-600 hover:bg-slate-50/50 uppercase tracking-wider flex justify-between items-center bg-slate-50/20"
                                  >
                                    <span>Filter by Color {selectedColorFilters[col] && <span className="text-blue-600 font-semibold text-[8px] normal-case ml-1">(Active)</span>}</span>
                                    <span className="text-[9px] text-slate-400 font-mono">
                                      {expandedSection === 'color' ? '▼' : '▶'}
                                    </span>
                                  </button>

                                  {expandedSection === 'color' && (
                                    <div className="max-h-28 overflow-y-auto px-3 py-2 space-y-1.5 custom-scrollbar bg-white">
                                      {Object.entries(anomaliesMap[col]).map(([pattern, colorClass]) => {
                                        const isChecked = selectedColorFilters[col] ? selectedColorFilters[col].has(pattern) : true;
                                        return (
                                          <label key={pattern} className="flex items-center gap-2 py-0.5 text-xs cursor-pointer hover:text-slate-900 select-none">
                                            <input
                                              type="checkbox"
                                              checked={isChecked}
                                              onChange={() => handleColorFilterToggle(col, pattern)}
                                              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                                            />
                                            <span className={`px-2 py-0.5 rounded text-[10px] truncate max-w-[180px] ring-1 ring-inset ${colorClass}`}>
                                              {pattern || '(empty)'}
                                            </span>
                                          </label>
                                        );
                                      })}
                                      <label className="flex items-center gap-2 py-0.5 text-xs cursor-pointer hover:text-slate-900 select-none">
                                        <input
                                          type="checkbox"
                                          checked={selectedColorFilters[col] ? selectedColorFilters[col].has('__default__') : true}
                                          onChange={() => handleColorFilterToggle(col, '__default__')}
                                          className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                                        />
                                        <span className="text-slate-500 text-[10px]">No Highlight (Default)</span>
                                      </label>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Filter by Value Accordion Section */}
                              <div className="border-t border-slate-100">
                                <button
                                  onClick={() => setExpandedSection(expandedSection === 'value' ? 'color' : 'value')}
                                  className="w-full px-3 py-2 text-left text-[9px] font-bold text-slate-400 hover:text-slate-600 hover:bg-slate-50/50 uppercase tracking-wider flex justify-between items-center bg-slate-50/20"
                                >
                                  <span>Filter by Value {selectedFilters[col] && <span className="text-blue-600 font-semibold text-[8px] normal-case ml-1">(Active)</span>}</span>
                                  <span className="text-[9px] text-slate-400 font-mono">
                                    {expandedSection === 'value' ? '▼' : '▶'}
                                  </span>
                                </button>

                                {expandedSection === 'value' && (
                                  <div className="py-2 bg-white">
                                    <div className="px-3 pb-2 relative">
                                      <input
                                        type="text"
                                        placeholder="Search values..."
                                        value={filterSearchText}
                                        onChange={(e) => setFilterSearchText(e.target.value)}
                                        className="w-full pl-7 pr-3 py-1 border border-slate-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-slate-50"
                                      />
                                      <Search className="w-3.5 h-3.5 text-slate-400 absolute left-5 top-2.5" />
                                    </div>

                                    <div className="flex justify-between px-3 py-1 text-[10px] text-blue-600 font-medium">
                                      <button onClick={() => handleSelectAllValues(col)} className="hover:underline">Select All</button>
                                      <button onClick={() => handleClearAllValues(col)} className="hover:underline">Clear All</button>
                                    </div>

                                    <div className="max-h-36 overflow-y-auto px-3 py-1 space-y-1 custom-scrollbar">
                                      {filteredUniqueVals.map((val) => {
                                        const isChecked = selectedFilters[col] ? selectedFilters[col].has(val) : true;
                                        const displayVal = val === null || val === undefined ? '(Blanks)' : String(val);
                                        return (
                                          <label key={displayVal} className="flex items-center gap-2 py-0.5 text-xs cursor-pointer hover:text-slate-900 select-none truncate">
                                            <input
                                              type="checkbox"
                                              checked={isChecked}
                                              onChange={() => handleValueFilterToggle(col, val)}
                                              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                                            />
                                            <span className="truncate" title={displayVal}>{displayVal}</span>
                                          </label>
                                        );
                                      })}
                                      {filteredUniqueVals.length === 0 && (
                                        <div className="text-[10px] text-slate-400 text-center py-2">No values found</div>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* Footer Actions */}
                              <div className="border-t border-slate-100 mt-auto p-2 flex justify-between bg-slate-50/80 rounded-b-lg">
                                <button
                                  onClick={() => handleClearColumnFilters(col)}
                                  className="text-[10px] text-slate-500 hover:text-slate-700 font-semibold px-2 py-1 hover:bg-slate-100 rounded transition-colors"
                                >
                                  Clear Filter
                                </button>
                                <button
                                  onClick={() => handleOkClick(col)}
                                  className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-bold px-3 py-1 rounded shadow-sm transition-colors"
                                >
                                  OK
                                </button>
                              </div>
                            </div>
                          )}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {processedRows.map((row: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-3 py-2 text-slate-400 text-center border-r border-slate-50 bg-white/50">{i + 1}</td>
                      {previewData?.columns?.map((col: string) => {
                        const val = row[col];
                        const isAnomalousCol = !!anomaliesMap[col];
                        let colorClass = 'text-slate-600';

                        if (isAnomalousCol) {
                          const pattern = abstractFormat(val);
                          if (anomaliesMap[col][pattern]) {
                            colorClass = `${anomaliesMap[col][pattern]} font-medium ring-1 ring-inset`;
                          }
                        }

                        return (
                          <td key={col} className={`px-3 py-2 ${colorClass}`}>
                            {val !== null ? String(val) : <span className="text-slate-300 italic">null</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center p-12 text-slate-500 border border-dashed rounded-lg bg-slate-50/50 flex-1 flex flex-col items-center justify-center">
              <ListFilter className="w-10 h-10 mb-3 text-slate-300" />
              <h3 className="font-semibold text-slate-700">No matching rows</h3>
              <p className="text-xs mt-1">Try clearing your filters or search terms to see the data.</p>
              <button 
                onClick={handleResetAll}
                className="mt-4 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs px-3.5 py-1.5 rounded border border-slate-200 font-semibold transition-colors"
              >
                Clear all filters
              </button>
            </div>
          )
        ) : (
          <div className="text-center p-8 text-slate-500 border border-dashed rounded-lg bg-slate-50/50">
            No rows found in the available preview sample.
          </div>
        )}
      </div>
    </div>
  );
};

