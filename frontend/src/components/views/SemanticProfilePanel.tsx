import React, { useMemo, useState } from 'react';
import { 
  BookOpen, 
  Layers, 
  Brain, 
  HelpCircle, 
  CheckCircle, 
  XCircle, 
  AlertTriangle, 
  Search, 
  Filter,
  FileText,
  Workflow
} from 'lucide-react';
import { formatDisplayValue } from './pipelinepanel/utils';

interface SemanticProfilePanelProps {
  profileData: any;
}

export const SemanticProfilePanel: React.FC<SemanticProfilePanelProps> = ({ profileData }) => {
  const semanticProfile = profileData?.semantic_profile;
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedGroup, setSelectedGroup] = useState<string>('All');
  const [showThinking, setShowThinking] = useState(false);
  const [expandedColumn, setExpandedColumn] = useState<string | null>(null);

  // Extract logical groups from semantic profile columns
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

  const groupNames = useMemo(() => {
    return ['All', ...Object.keys(logicalGroups)];
  }, [logicalGroups]);

  // Filter columns based on search term and selected logical group
  const filteredColumns = useMemo(() => {
    if (!semanticProfile?.columns) return [];
    
    return Object.entries(semanticProfile.columns).filter(([colName, detail]: [string, any]) => {
      const matchesSearch = 
        colName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (detail.description || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (detail.semantic_data_type || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (detail.expected_type || '').toLowerCase().includes(searchTerm.toLowerCase());
        
      const matchesGroup = 
        selectedGroup === 'All' || 
        (detail.logical_group || 'Uncategorized') === selectedGroup;
        
      return matchesSearch && matchesGroup;
    });
  }, [semanticProfile, searchTerm, selectedGroup]);

  if (!semanticProfile) {
    return (
      <div className="bg-card rounded-xl border border-slate-200 p-8 text-center text-muted-foreground shadow-sm">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm font-semibold">No Semantic Profile data available.</p>
        <p className="text-xs">Please check that the Semantic Profiler agent ran successfully in the backend.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overview Card */}
      <div className="bg-gradient-to-br from-indigo-50/50 via-white to-sky-50/30 rounded-xl border border-slate-200 p-6 shadow-sm text-left space-y-4">
        <div className="flex items-center space-x-3 text-indigo-700">
          <BookOpen className="h-5 w-5" />
          <h2 className="text-lg font-bold tracking-tight">Dataset Semantic Context</h2>
        </div>
        
        {/* Table Summary */}
        {semanticProfile.table_summary && (
          <div className="space-y-1 bg-white/60 backdrop-blur-sm rounded-lg p-4 border border-slate-100/50">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Business Purpose & Summary
            </h3>
            <p className="text-sm text-slate-700 leading-relaxed font-sans">
              {formatDisplayValue(semanticProfile.table_summary)}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {/* Logical Groups Summary */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-slate-400" />
              <span>Logical Groups ({Object.keys(logicalGroups).length})</span>
            </h3>
            <div className="border border-slate-100 rounded-lg overflow-hidden bg-white/70">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50/60 border-b border-slate-100">
                    <th className="text-left p-2 font-bold text-slate-500 w-[150px]">Group</th>
                    <th className="text-left p-2 font-bold text-slate-500">Columns</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(logicalGroups).map(([groupName, cols], i) => (
                    <tr key={i} className="hover:bg-slate-50/30">
                      <td className="p-2 align-top font-semibold text-slate-700">{formatDisplayValue(groupName)}</td>
                      <td className="p-2 align-top">
                        <div className="flex flex-wrap gap-1">
                          {cols.map((colName, idx) => (
                            <span key={idx} className="font-mono text-[9px] bg-slate-100 text-slate-600 px-1 py-0.5 rounded border border-slate-200/40">
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

          {/* Thinking Process / Chain of Thought */}
          {semanticProfile.thinking && (
            <div className="space-y-2 flex flex-col">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Brain className="h-3.5 w-3.5 text-slate-400" />
                <span>AI Agent Thinking</span>
              </h3>
              <div className="flex-1 border border-slate-100 rounded-lg p-3 bg-slate-50/50 flex flex-col justify-between">
                <p className="text-xs text-slate-600 italic">
                  Review the semantic analysis reasoning process and rules formulated by the Profiler Agent.
                </p>
                <button
                  type="button"
                  onClick={() => setShowThinking(!showThinking)}
                  className="mt-3 inline-flex items-center justify-center space-x-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 h-9 px-3 w-full transition-colors cursor-pointer"
                >
                  <Brain className="h-3.5 w-3.5 text-indigo-500" />
                  <span>{showThinking ? 'Hide Agent Logics' : 'View Semantic Logics'}</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Expanded Chain of Thought Log */}
        {showThinking && semanticProfile.thinking && (
          <div className="bg-slate-900 text-slate-100 rounded-xl p-5 font-mono text-xs leading-relaxed max-h-72 overflow-y-auto border border-slate-800 shadow-inner mt-4 animate-fade-in custom-scrollbar">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
              <span className="text-indigo-400 font-bold uppercase tracking-wider text-[10px]">Chain of Thought Log</span>
              <span className="text-[10px] text-slate-500 font-bold">ProfilerAgent v1.0</span>
            </div>
            {semanticProfile.thinking.split('\n').map((line: string, i: number) => (
              <div key={i} className="min-h-[1.2rem] py-0.5">
                {line}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Metadata List Section */}
      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
          {/* Search bar */}
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search column metadata..."
              className="w-full pl-9 pr-4 py-2 text-xs border border-slate-200 rounded-lg placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          {/* Group filters */}
          <div className="flex items-center space-x-2 w-full sm:w-auto overflow-x-auto select-none py-1 sm:py-0">
            <Filter className="h-3.5 w-3.5 text-slate-400 shrink-0" />
            <span className="text-xs font-semibold text-slate-500 shrink-0 mr-1">Group:</span>
            <div className="flex space-x-1.5">
              {groupNames.map((group) => (
                <button
                  key={group}
                  onClick={() => setSelectedGroup(group)}
                  className={`text-[10px] font-bold px-2.5 py-1 rounded-md border transition-all shrink-0 ${
                    selectedGroup === group
                      ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                      : 'bg-slate-50 text-slate-600 border-slate-200/60 hover:bg-slate-100'
                  }`}
                >
                  {formatDisplayValue(group)}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Column Metadata Grid */}
        <div className="grid grid-cols-1 gap-4">
          {filteredColumns.length === 0 ? (
            <div className="bg-card rounded-xl border border-slate-200 p-8 text-center text-muted-foreground shadow-sm">
              <Search className="h-6 w-6 mx-auto mb-2 text-slate-400" />
              <p className="text-sm font-semibold">No columns match your filter criteria.</p>
            </div>
          ) : (
            filteredColumns.map(([colName, colDetail]: [string, any], idx: number) => {
              const isExpanded = expandedColumn === colName;
              const hasErrors = colDetail.is_error;
              const errorCount = colDetail.error_types?.length || 0;
              const hasDMVs = colDetail.potential_dmv && colDetail.potential_dmv.length > 0;
              const hasPattern = !!colDetail.expected_str_pattern;

              return (
                <div 
                  key={colName} 
                  className={`bg-card rounded-xl border transition-all ${
                    hasErrors 
                      ? 'border-red-200 shadow-sm bg-red-50/5' 
                      : 'border-slate-200 hover:border-slate-300 hover:shadow-sm'
                  }`}
                >
                  {/* Card Header */}
                  <div 
                    className="px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none"
                    onClick={() => setExpandedColumn(isExpanded ? null : colName)}
                  >
                    <div className="flex items-center space-x-3 text-left">
                      <div className={`p-2 rounded-lg ${
                        hasErrors 
                          ? 'bg-red-50 text-red-600' 
                          : 'bg-indigo-50 text-indigo-600'
                      }`}>
                        <FileText className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <h4 className="font-bold text-slate-800 text-sm tracking-tight">{colName}</h4>
                          <div className="flex items-center space-x-1 font-mono text-[9px] bg-slate-100 text-slate-500 border border-slate-200/50 px-2 py-0.5 rounded-full select-none">
                            <span>{profileData.columns?.[colName]?.dtype || 'unknown'}</span>
                            <span className="text-slate-400">➔</span>
                            <span className="text-indigo-600 font-semibold">{colDetail.expected_type}</span>
                          </div>
                          {hasErrors && (
                            <span className="text-[9px] font-bold text-red-600 bg-red-100/50 px-2 py-0.5 rounded-full border border-red-200/30 flex items-center gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              <span>{errorCount} error(s)</span>
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate max-w-xl mt-0.5">
                          {colDetail.description || 'No description provided.'}
                        </p>
                      </div>
                    </div>

                    {/* Metadata Badges in Header */}
                    <div className="flex items-center justify-between sm:justify-end gap-3 border-t sm:border-0 pt-2 sm:pt-0 border-slate-100">
                      <div className="flex items-center space-x-2">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Group:</span>
                        <span className="text-[10px] font-bold text-slate-700 bg-slate-100 px-2.5 py-0.5 rounded-full border border-slate-200/40">
                          {formatDisplayValue(colDetail.logical_group || 'Uncategorized')}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-indigo-600 hover:text-indigo-500">
                        {isExpanded ? 'Collapse' : 'Expand Details'}
                      </span>
                    </div>
                  </div>

                  {/* Card Expanded Content */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 px-5 py-5 bg-slate-50/10 text-left space-y-4 animate-fade-in">
                      {/* Properties Grid Table */}
                      <div className="border border-slate-150 rounded-lg overflow-hidden bg-white shadow-sm">
                        <table className="w-full text-xs border-collapse">
                          <thead>
                            <tr className="bg-slate-50/80 border-b border-slate-200">
                              <th className="text-left p-3 font-bold text-slate-500 w-[200px] border-r border-slate-150">Property & Expected State</th>
                              <th className="text-left p-3 font-bold text-slate-500">Agent Reasoning & Business Context</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-150">
                            {/* Semantic Data Type */}
                            <tr className="hover:bg-slate-50/20">
                              <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150 flex items-center gap-1.5">
                                <Workflow className="h-3.5 w-3.5 text-indigo-500 shrink-0" />
                                <span>Semantic Data Type</span>
                              </td>
                              <td className="p-3 align-top text-slate-600">
                                <div className="flex items-center space-x-2">
                                  <span className="font-bold text-indigo-700 bg-indigo-50 border border-indigo-200/30 px-2 py-0.5 rounded">
                                    {colDetail.semantic_data_type}
                                  </span>
                                  {colDetail.semantic_data_type_reason && (
                                    <span className="text-xs text-slate-500">• {colDetail.semantic_data_type_reason}</span>
                                  )}
                                </div>
                              </td>
                            </tr>

                            {/* Current Physical Type */}
                            <tr className="hover:bg-slate-50/20">
                              <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150">
                                Current Physical Type
                              </td>
                              <td className="p-3 align-top text-slate-600">
                                <span className="font-mono font-bold text-slate-700 bg-slate-100 border px-1.5 py-0.5 rounded">
                                  {profileData.columns?.[colName]?.dtype || 'unknown'}
                                </span>
                              </td>
                            </tr>

                            {/* Expected Type */}
                            <tr className="hover:bg-slate-50/20">
                              <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150">
                                Expected Type
                              </td>
                              <td className="p-3 align-top text-slate-600">
                                <div className="flex flex-col gap-1">
                                  <div className="flex items-center space-x-2">
                                    <span className="font-mono font-bold text-indigo-600 bg-indigo-50 border border-indigo-200/30 px-1.5 py-0.5 rounded">
                                      {colDetail.expected_type}
                                    </span>
                                    {colDetail.expected_type_reason && (
                                      <span className="text-xs text-slate-500">• {colDetail.expected_type_reason}</span>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>

                            {/* Nullability / Allow Missing */}
                            <tr className="hover:bg-slate-50/20">
                              <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150 flex items-center gap-1.5">
                                {colDetail.allow_missing ? (
                                  <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                                ) : (
                                  <XCircle className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                                )}
                                <span>Allow Missing (Nullable)</span>
                              </td>
                              <td className="p-3 align-top text-slate-600">
                                <div className="flex items-center space-x-2">
                                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                                    colDetail.allow_missing 
                                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200/30' 
                                      : 'bg-slate-100 text-slate-700 border-slate-200/50'
                                  }`}>
                                    {colDetail.allow_missing ? 'Yes' : 'No'}
                                  </span>
                                  {colDetail.allow_missing_reason && (
                                    <span className="text-xs text-slate-500">• {colDetail.allow_missing_reason}</span>
                                  )}
                                </div>
                              </td>
                            </tr>

                            {/* Pre-assigned strategies */}
                            {colDetail.fill_strategies && colDetail.fill_strategies.length > 0 && (
                              <tr className="hover:bg-slate-50/20">
                                <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150">
                                  Allowed Imputation Strategies
                                </td>
                                <td className="p-3 align-top">
                                  <div className="flex flex-wrap gap-1.5">
                                    {colDetail.fill_strategies.map((strat: string, i: number) => (
                                      <span key={i} className="font-mono text-[10px] bg-slate-100 text-slate-600 border px-1.5 py-0.5 rounded">
                                        {strat}
                                      </span>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Disguised Missing Values */}
                            {hasDMVs && (
                              <tr className="hover:bg-slate-50/20">
                                <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150 flex items-center gap-1.5">
                                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                  <span>Disguised Missing (DMVs)</span>
                                </td>
                                <td className="p-3 align-top text-slate-600">
                                  <div className="space-y-1.5">
                                    <div className="flex flex-wrap gap-1">
                                      {colDetail.potential_dmv.map((dmv: string, i: number) => (
                                        <span key={i} className="font-mono text-[10px] bg-amber-50 text-amber-800 border border-amber-200/30 px-1.5 py-0.5 rounded">
                                          "{dmv}"
                                        </span>
                                      ))}
                                    </div>
                                    {colDetail.potential_dmv_reason && (
                                      <p className="text-xs text-slate-400 italic">{colDetail.potential_dmv_reason}</p>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Expected Pattern */}
                            {hasPattern && (
                              <tr className="hover:bg-slate-50/20">
                                <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150">
                                  Format Validation Pattern
                                </td>
                                <td className="p-3 align-top text-slate-600">
                                  <div className="space-y-1">
                                    <div className="flex items-center space-x-2">
                                      <span className="font-mono text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded">
                                        {colDetail.expected_str_pattern}
                                      </span>
                                    </div>
                                    {colDetail.expected_str_pattern_reason && (
                                      <p className="text-xs text-slate-400 italic">{colDetail.expected_str_pattern_reason}</p>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Relationships */}
                            {colDetail.relationships && colDetail.relationships.length > 0 && (
                              <tr className="hover:bg-slate-50/20">
                                <td className="p-3 align-top font-semibold text-slate-700 border-r border-slate-150">
                                  Cross-Column Dependencies
                                </td>
                                <td className="p-3 align-top">
                                  <div className="flex flex-col gap-1.5">
                                    {colDetail.relationships.map((rel: string, i: number) => (
                                      <span key={i} className="font-mono text-[10px] bg-slate-50 text-slate-600 border border-slate-200/50 px-2 py-0.5 rounded inline-block max-w-max">
                                        {rel}
                                      </span>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Quality Errors */}
                            {hasErrors && (
                              <tr className="bg-red-50/15 hover:bg-red-50/25">
                                <td className="p-3 align-top font-semibold text-red-700 border-r border-slate-150 flex items-center gap-1.5">
                                  <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                                  <span>Semantic Quality Anomalies</span>
                                </td>
                                <td className="p-3 align-top text-red-700">
                                  <div className="space-y-2">
                                    <div className="flex flex-wrap gap-1">
                                      {colDetail.error_types.map((err: string, i: number) => (
                                        <span key={i} className="text-[9px] font-bold uppercase tracking-wider text-white bg-red-500 px-2 py-0.5 rounded border border-red-600">
                                          {err}
                                        </span>
                                      ))}
                                    </div>
                                    <p className="text-xs leading-relaxed">
                                      <strong className="font-semibold">Reason:</strong> {colDetail.error_reason || 'Anomalies detected in column data.'}
                                    </p>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
