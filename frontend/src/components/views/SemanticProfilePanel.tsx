import React, { useMemo, useState } from 'react';
import { 
  BookOpen, 
  Layers, 
  Brain, 
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
      <div className="bg-card rounded-lg border border-border p-6 text-left space-y-4">
        <div className="flex items-center space-x-3 text-foreground">
          <BookOpen className="h-5 w-5" />
          <h2 className="text-lg font-bold tracking-tight">Dataset Semantic Context</h2>
        </div>
        
        {/* Table Summary */}
        {semanticProfile.table_summary && (
          <div className="space-y-1 bg-muted/10 rounded-lg p-4 border border-border">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Business Purpose & Summary
            </h3>
            <p className="text-sm text-foreground leading-relaxed font-sans">
              {formatDisplayValue(semanticProfile.table_summary)}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {/* Logical Groups Summary */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-muted-foreground" />
              <span>Logical Groups ({Object.keys(logicalGroups).length})</span>
            </h3>
            <div className="border border-border rounded-lg overflow-hidden bg-card">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-muted/50 border-b border-border">
                    <th className="text-left p-2 font-bold text-muted-foreground w-[150px]">Group</th>
                    <th className="text-left p-2 font-bold text-muted-foreground">Columns</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {Object.entries(logicalGroups).map(([groupName, cols], i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="p-2 align-top font-semibold text-foreground">{formatDisplayValue(groupName)}</td>
                      <td className="p-2 align-top">
                        <div className="flex flex-wrap gap-1">
                          {cols.map((colName, idx) => (
                            <span key={idx} className="font-mono text-[9px] bg-muted text-muted-foreground px-1 py-0.5 rounded border border-border">
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
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Brain className="h-3.5 w-3.5 text-muted-foreground" />
                <span>AI Agent Thinking</span>
              </h3>
              <div className="flex-1 border border-border rounded-lg p-3 bg-muted/10 flex flex-col justify-between">
                <p className="text-xs text-muted-foreground italic">
                  Review the semantic analysis reasoning process and rules formulated by the Profiler Agent.
                </p>
                <button
                  type="button"
                  onClick={() => setShowThinking(!showThinking)}
                  className="mt-3 inline-flex items-center justify-center space-x-1.5 rounded border border-border bg-card hover:bg-muted text-xs font-semibold text-foreground h-9 px-3 w-full transition-colors cursor-pointer"
                >
                  <Brain className="h-3.5 w-3.5 text-primary" />
                  <span>{showThinking ? 'Hide Agent Logics' : 'View Semantic Logics'}</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Expanded Chain of Thought Log */}
        {showThinking && semanticProfile.thinking && (
          <div className="bg-slate-950 text-slate-300 rounded-lg p-4 font-mono text-xs leading-relaxed max-h-72 overflow-y-auto border border-slate-800 shadow-inner mt-4 animate-fade-in custom-scrollbar">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
              <span className="text-primary font-bold uppercase tracking-wider text-[10px]">Chain of Thought Log</span>
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
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-card p-3 rounded-lg border border-border">
          {/* Search bar */}
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search column metadata..."
              className="w-full pl-9 pr-4 py-2 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary bg-background text-foreground transition-all"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          {/* Group filters */}
          <div className="flex items-center space-x-2 w-full sm:w-auto overflow-x-auto select-none py-1 sm:py-0">
            <Filter className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-xs font-semibold text-muted-foreground shrink-0 mr-1">Group:</span>
            <div className="flex space-x-1.5">
              {groupNames.map((group) => (
                <button
                  key={group}
                  onClick={() => setSelectedGroup(group)}
                  className={`text-[10px] font-bold px-2.5 py-1 rounded border transition-all shrink-0 cursor-pointer ${
                    selectedGroup === group
                      ? 'bg-primary text-primary-foreground border-primary shadow-xs'
                      : 'bg-muted text-muted-foreground border-border hover:bg-muted/80'
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
            <div className="bg-card rounded-lg border border-border p-8 text-center text-muted-foreground">
              <Search className="h-5 w-5 mx-auto mb-2 text-muted-foreground/50" />
              <p className="text-xs font-semibold">No columns match your filter criteria.</p>
            </div>
          ) : (
            filteredColumns.map(([colName, colDetail]: [string, any]) => {
              const isExpanded = expandedColumn === colName;
              const hasErrors = colDetail.is_error;
              const errorCount = colDetail.error_types?.length || 0;
              const hasDMVs = colDetail.potential_dmv && colDetail.potential_dmv.length > 0;
              const hasPattern = !!colDetail.expected_str_pattern;

              return (
                <div 
                  key={colName} 
                  className={`bg-card rounded-lg border transition-all ${
                    hasErrors 
                      ? 'border-destructive/30 bg-destructive/5' 
                      : 'border-border hover:border-border/80'
                  }`}
                >
                  {/* Card Header */}
                  <div 
                    className="px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none"
                    onClick={() => setExpandedColumn(isExpanded ? null : colName)}
                  >
                    <div className="flex items-center space-x-3 text-left">
                      <div className={`p-2 rounded ${
                        hasErrors 
                          ? 'bg-destructive/10 text-destructive' 
                          : 'bg-muted text-muted-foreground'
                      }`}>
                        <FileText className="h-3.5 w-3.5" />
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <h4 className="font-bold text-foreground text-sm tracking-tight">{colName}</h4>
                          <div className="flex items-center space-x-1 font-mono text-[9px] bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded select-none">
                            <span>{profileData.columns?.[colName]?.dtype || 'unknown'}</span>
                            <span className="text-muted-foreground">➔</span>
                            <span className="text-primary font-semibold">{colDetail.expected_type}</span>
                          </div>
                          {hasErrors && (
                            <span className="text-[9px] font-bold text-destructive bg-destructive/10 px-2 py-0.5 rounded border border-destructive/20 flex items-center gap-1">
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
                    <div className="flex items-center justify-between sm:justify-end gap-3 border-t sm:border-0 pt-2 sm:pt-0 border-border">
                      <div className="flex items-center space-x-2">
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Group:</span>
                        <span className="font-mono text-[10px] text-muted-foreground bg-muted px-2.5 py-0.5 rounded border border-border">
                          {formatDisplayValue(colDetail.logical_group || 'Uncategorized')}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-primary hover:underline">
                        {isExpanded ? 'Collapse' : 'Expand Details'}
                      </span>
                    </div>
                  </div>

                  {/* Card Expanded Content */}
                  {isExpanded && (
                    <div className="border-t border-border px-5 py-5 bg-muted/5 text-left space-y-4 animate-fade-in">
                      {/* Properties Grid Table */}
                      <div className="border border-border rounded-lg overflow-hidden bg-card">
                        <table className="w-full text-xs border-collapse">
                          <thead>
                            <tr className="bg-muted/50 border-b border-border">
                              <th className="text-left p-3 font-bold text-muted-foreground w-[200px] border-r border-border">Property & Expected State</th>
                              <th className="text-left p-3 font-bold text-muted-foreground">Agent Reasoning & Business Context</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {/* Semantic Data Type */}
                            <tr className="hover:bg-muted/30">
                              <td className="p-3 align-top font-semibold text-foreground border-r border-border flex items-center gap-1.5">
                                <Workflow className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                <span>Semantic Data Type</span>
                              </td>
                              <td className="p-3 align-top text-foreground">
                                <div className="flex items-center space-x-2">
                                  <span className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded">
                                    {colDetail.semantic_data_type}
                                  </span>
                                  {colDetail.semantic_data_type_reason && (
                                    <span className="text-xs text-muted-foreground">• {colDetail.semantic_data_type_reason}</span>
                                  )}
                                </div>
                              </td>
                            </tr>

                            {/* Current Physical Type */}
                            <tr className="hover:bg-muted/30">
                              <td className="p-3 align-top font-semibold text-foreground border-r border-border">
                                Current Physical Type
                              </td>
                              <td className="p-3 align-top text-foreground">
                                <span className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-1.5 py-0.5 rounded">
                                  {profileData.columns?.[colName]?.dtype || 'unknown'}
                                </span>
                              </td>
                            </tr>

                            {/* Expected Type */}
                            <tr className="hover:bg-muted/30">
                              <td className="p-3 align-top font-semibold text-foreground border-r border-border">
                                Expected Type
                              </td>
                              <td className="p-3 align-top text-foreground">
                                <div className="flex flex-col gap-1">
                                  <div className="flex items-center space-x-2">
                                    <span className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-1.5 py-0.5 rounded">
                                      {colDetail.expected_type}
                                    </span>
                                    {colDetail.expected_type_reason && (
                                      <span className="text-xs text-muted-foreground">• {colDetail.expected_type_reason}</span>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>

                            {/* Nullability / Allow Missing */}
                            <tr className="hover:bg-muted/30">
                              <td className="p-3 align-top font-semibold text-foreground border-r border-border flex items-center gap-1.5">
                                {colDetail.allow_missing ? (
                                  <CheckCircle className="h-3.5 w-3.5 text-success shrink-0" />
                                ) : (
                                  <XCircle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                )}
                                <span>Allow Missing (Nullable)</span>
                              </td>
                              <td className="p-3 align-top text-foreground">
                                <div className="flex items-center space-x-2">
                                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                                    colDetail.allow_missing 
                                      ? 'bg-success/5 text-success border-success/20' 
                                      : 'bg-muted text-muted-foreground border-border'
                                  }`}>
                                    {colDetail.allow_missing ? 'Yes' : 'No'}
                                  </span>
                                  {colDetail.allow_missing_reason && (
                                    <span className="text-xs text-muted-foreground">• {colDetail.allow_missing_reason}</span>
                                  )}
                                </div>
                              </td>
                            </tr>

                            {/* Pre-assigned strategies */}
                            {colDetail.fill_strategies && colDetail.fill_strategies.length > 0 && (
                              <tr className="hover:bg-muted/30">
                                <td className="p-3 align-top font-semibold text-foreground border-r border-border">
                                  Allowed Imputation Strategies
                                </td>
                                <td className="p-3 align-top">
                                  <div className="flex flex-wrap gap-1.5">
                                    {colDetail.fill_strategies.map((strat: string, i: number) => (
                                      <span key={i} className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-1.5 py-0.5 rounded">
                                        {strat}
                                      </span>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Disguised Missing Values */}
                            {hasDMVs && (
                              <tr className="hover:bg-muted/30">
                                <td className="p-3 align-top font-semibold text-foreground border-r border-border flex items-center gap-1.5">
                                  <AlertTriangle className="h-3.5 w-3.5 text-warning shrink-0" />
                                  <span>Disguised Missing (DMVs)</span>
                                </td>
                                <td className="p-3 align-top text-foreground">
                                  <div className="space-y-1.5">
                                    <div className="flex flex-wrap gap-1">
                                      {colDetail.potential_dmv.map((dmv: string, i: number) => (
                                        <span key={i} className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-1.5 py-0.5 rounded">
                                          "{dmv}"
                                        </span>
                                      ))}
                                    </div>
                                    {colDetail.potential_dmv_reason && (
                                      <p className="text-xs text-muted-foreground italic">{colDetail.potential_dmv_reason}</p>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Expected Pattern */}
                            {hasPattern && (
                              <tr className="hover:bg-muted/30">
                                <td className="p-3 align-top font-semibold text-foreground border-r border-border">
                                  Format Validation Pattern
                                </td>
                                <td className="p-3 align-top text-foreground">
                                  <div className="space-y-1">
                                    <div className="flex items-center space-x-2">
                                      <span className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded">
                                        {colDetail.expected_str_pattern}
                                      </span>
                                    </div>
                                    {colDetail.expected_str_pattern_reason && (
                                      <p className="text-xs text-muted-foreground italic">{colDetail.expected_str_pattern_reason}</p>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Relationships */}
                            {colDetail.relationships && colDetail.relationships.length > 0 && (
                              <tr className="hover:bg-muted/30">
                                <td className="p-3 align-top font-semibold text-foreground border-r border-border">
                                  Cross-Column Dependencies
                                </td>
                                <td className="p-3 align-top">
                                  <div className="flex flex-col gap-1.5">
                                    {colDetail.relationships.map((rel: string, i: number) => (
                                      <span key={i} className="font-mono text-[10px] bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded inline-block max-w-max">
                                        {rel}
                                      </span>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}

                            {/* Quality Errors */}
                            {hasErrors && (
                              <tr className="bg-destructive/5 hover:bg-destructive/10">
                                <td className="p-3 align-top font-semibold text-destructive border-r border-border flex items-center gap-1.5">
                                  <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />
                                  <span>Semantic Quality Anomalies</span>
                                </td>
                                <td className="p-3 align-top text-destructive">
                                  <div className="space-y-2">
                                    <div className="flex flex-wrap gap-1">
                                      {colDetail.error_types.map((err: string, i: number) => (
                                        <span key={i} className="text-[9px] font-bold uppercase tracking-wider text-destructive bg-destructive/10 px-2 py-0.5 rounded border border-destructive/20">
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
