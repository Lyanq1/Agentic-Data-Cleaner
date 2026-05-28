import React, { useState, useEffect } from 'react';
import { 
  UploadCloud, 
  X, 
  FileText, 
  Table as TableIcon, 
  BarChart3, 
  Database, 
  Binary, 
  ArrowRight,
  AlertCircle
} from 'lucide-react';
import { pipelineApi } from '../../api/services';
import * as XLSX from 'xlsx';
import Papa from 'papaparse';

interface UploadViewProps {
  onUploadSuccess: (runId: string) => void;
  onProfileLoaded?: (runId: string) => void;
  onClearProfile?: () => void;
  initialRunId?: string | null;
}

interface PreviewData {
  headers: string[];
  rows: any[][];
  fileName: string;
  rowCount: number;
}

export const UploadView: React.FC<UploadViewProps> = ({ 
  onUploadSuccess,
  onProfileLoaded,
  onClearProfile,
  initialRunId
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [profileData, setProfileData] = useState<any | null>(null);
  const [requirements, setRequirements] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedRunId, setUploadedRunId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'profile' | 'preview'>('profile');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialRunId && !profileData && !isUploading) {
      const loadExistingProfile = async () => {
        setIsUploading(true);
        setError(null);
        try {
          const profile = await pipelineApi.getProfile(initialRunId);
          setProfileData(profile);
          setUploadedRunId(initialRunId);
          setActiveTab('profile');
        } catch (err: any) {
          console.error('Failed to load existing profile:', err);
          setError(err.message || 'Failed to load statistical profile');
        } finally {
          setIsUploading(false);
        }
      };
      loadExistingProfile();
    }
  }, [initialRunId]);

  const parseFile = (selectedFile: File): Promise<void> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      const extension = selectedFile.name.split('.').pop()?.toLowerCase();

      if (extension === 'csv') {
        Papa.parse(selectedFile, {
          complete: (results: Papa.ParseResult<any>) => {
            if (results.data && results.data.length > 0) {
              const data = results.data as any[][];
              const validRows = data.filter(row => row.length > 0 && row.some(cell => cell !== ''));
              
              setPreviewData({
                headers: validRows[0].map(String),
                rows: validRows.slice(1, 101), // Preview first 100 rows
                fileName: selectedFile.name,
                rowCount: validRows.length - 1
              });
              resolve();
            } else {
              reject(new Error('CSV file is empty'));
            }
          },
          error: (err: any) => {
            console.error('CSV parse error:', err);
            reject(err);
          }
        });
      } else if (extension === 'xlsx' || extension === 'xls') {
        reader.onload = (e) => {
          try {
            const data = new Uint8Array(e.target?.result as ArrayBuffer);
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];
            const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as any[][];

            if (jsonData.length > 0) {
              setPreviewData({
                headers: jsonData[0].map(String),
                rows: jsonData.slice(1, 101),
                fileName: selectedFile.name,
                rowCount: jsonData.length - 1
              });
              resolve();
            } else {
              reject(new Error('Excel sheet is empty'));
            }
          } catch (err) {
            console.error('Excel parse error:', err);
            reject(err);
          }
        };
        reader.readAsArrayBuffer(selectedFile);
      } else if (extension === 'json') {
        reader.onload = (e) => {
          try {
            const json = JSON.parse(e.target?.result as string);
            let rows: any[] = [];
            if (Array.isArray(json)) {
              rows = json;
            } else if (typeof json === 'object') {
              rows = [json];
            }

            if (rows.length > 0) {
              const headers = Object.keys(rows[0]);
              const rowData = rows.slice(0, 100).map(row => headers.map(h => row[h]));
              setPreviewData({
                headers,
                rows: rowData,
                fileName: selectedFile.name,
                rowCount: rows.length
              });
              resolve();
            } else {
              reject(new Error('JSON file is empty'));
            }
          } catch (err) {
            console.error('JSON parse error:', err);
            reject(err);
          }
        };
        reader.readAsText(selectedFile);
      } else {
        // SQL / Parquet: Skip client-side preview parsing
        resolve();
      }
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      setError(null);
      // Clean up previous results if a new file is chosen
      setPreviewData(null);
      setProfileData(null);
      setUploadedRunId(null);
    }
  };

  const handleRemoveFile = () => {
    setFile(null);
    setPreviewData(null);
    setProfileData(null);
    setUploadedRunId(null);
    const input = document.getElementById('file-upload') as HTMLInputElement;
    if (input) input.value = '';
    if (onClearProfile) {
      onClearProfile();
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file first.');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const response = await pipelineApi.uploadFile(file, requirements);
      setUploadedRunId(response.run_id);
      
      // Attempt browser-side parse for table preview
      try {
        await parseFile(file);
      } catch (parseErr) {
        console.warn('Skipping client-side table preview for this format:', parseErr);
      }
      
      // Fetch detailed statistical profile from backend
      const profile = await pipelineApi.getProfile(response.run_id);
      setProfileData(profile);
      setActiveTab('profile');
      if (onProfileLoaded) {
        onProfileLoaded(response.run_id);
      }
    } catch (err: any) {
      console.error('Upload/Profile failed:', err);
      setError(err.response?.data?.detail || err.message || 'An error occurred during upload');
    } finally {
      setIsUploading(false);
    }
  };

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
    <div className="w-full max-w-6xl mx-auto flex flex-col pt-4 text-left pb-16 px-2 h-full min-h-0 overflow-y-auto hidden-scrollbar">
      {/* Header section */}
      {!profileData && (
        <div className="mb-8 text-center animate-fade-in">
          <h1 className="text-3xl font-bold tracking-tight mb-2">Upload Dataset</h1>
          <p className="text-muted-foreground">
            Provide your data file and specific requirements for the AI agent to process.
          </p>
        </div>
      )}

      <div className="space-y-6">
        {/* Upload form Panel */}
        {!profileData && (
          <div className="rounded-xl border bg-card text-card-foreground shadow-sm max-w-2xl mx-auto w-full">
            <form onSubmit={handleUpload} className="p-6 space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-800">
                  Data File
                </label>
                {!file ? (
                  <div 
                    className="border-2 border-dashed border-slate-200 rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer hover:bg-slate-50/50 hover:border-primary/45 transition-all duration-300 group" 
                    onClick={() => document.getElementById('file-upload')?.click()}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                        const selectedFile = e.dataTransfer.files[0];
                        setFile(selectedFile);
                        setError(null);
                      }
                    }}
                  >
                    <div className="bg-slate-50 p-3 rounded-full mb-3 group-hover:scale-110 transition-transform">
                      <UploadCloud className="h-8 w-8 text-slate-400 group-hover:text-primary" />
                    </div>
                    <div className="text-sm font-medium mb-1 text-slate-700">
                      Click to select or drag and drop
                    </div>
                    <div className="text-xs text-muted-foreground">
                      CSV, JSON, XLSX, SQL, TSV, Parquet (Max 50MB)
                    </div>
                    <input
                      id="file-upload"
                      type="file"
                      className="hidden"
                      accept=".csv,.json,.xlsx,.xls,.jsonl,.sql,.tsv,.parquet"
                      onChange={handleFileChange}
                    />
                  </div>
                ) : (
                  <div className="relative p-4 rounded-xl border bg-slate-50/45 flex items-center space-x-3 border-slate-100">
                    <div className="bg-primary/10 p-2.5 rounded-lg">
                      <FileText className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate text-slate-800">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                    <button 
                      type="button"
                      onClick={handleRemoveFile}
                      className="p-1 hover:bg-slate-200/50 rounded-full transition-colors"
                    >
                      <X className="h-4 w-4 text-slate-500" />
                    </button>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-800">
                  Business Cleaning Requirements (Optional)
                </label>
                <textarea
                  className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 min-h-[100px] transition-all"
                  placeholder="e.g. Clean the email column, drop rows with missing values, extract domain names..."
                  value={requirements}
                  onChange={(e) => setRequirements(e.target.value)}
                />
              </div>

              {error && (
                <div className="p-3 border border-destructive/20 bg-destructive/5 text-destructive text-sm rounded-lg flex items-start space-x-2">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={!file || isUploading}
                className="inline-flex items-center justify-center rounded-lg text-sm font-semibold transition-all bg-primary text-primary-foreground hover:bg-primary/95 h-11 px-4 py-2 w-full shadow-md active:scale-[0.98] disabled:opacity-50"
              >
                {isUploading ? (
                  <div className="flex items-center space-x-2">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    <span>Uploading & Profiling...</span>
                  </div>
                ) : (
                  'Upload File'
                )}
              </button>
            </form>
          </div>
        )}

        {/* Post-Upload Statistics View */}
        {profileData && (
          <div className="space-y-6 animate-fade-in">
            {/* Navigation and Actions */}
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between bg-card p-4 rounded-xl border shadow-sm gap-4">
              <div className="flex items-center space-x-4">
                {/* Active Tab triggers */}
                <div className="inline-flex rounded-lg border bg-muted p-1">
                  <button
                    onClick={() => setActiveTab('profile')}
                    className={`inline-flex items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                      activeTab === 'profile' 
                        ? 'bg-background text-foreground shadow-sm' 
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <BarChart3 className="h-3.5 w-3.5" />
                    <span>Statistical Profile</span>
                  </button>
                  {previewData && (
                    <button
                      onClick={() => setActiveTab('preview')}
                      className={`inline-flex items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                        activeTab === 'preview' 
                          ? 'bg-background text-foreground shadow-sm' 
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <TableIcon className="h-3.5 w-3.5" />
                      <span>Table Preview</span>
                    </button>
                  )}
                </div>
                
                <div className="hidden sm:flex items-center space-x-2 text-xs text-muted-foreground">
                  <span className="font-semibold text-slate-700 bg-slate-100 px-2.5 py-0.5 rounded-full">
                    {profileData.total_rows.toLocaleString()} rows
                  </span>
                  <span>/</span>
                  <span className="font-semibold text-slate-700 bg-slate-100 px-2.5 py-0.5 rounded-full">
                    {profileData.total_columns} columns
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-3 w-full md:w-auto">
                <button
                  onClick={handleRemoveFile}
                  className="inline-flex items-center justify-center rounded-lg text-xs font-semibold border hover:bg-slate-50 transition-colors h-10 px-4"
                >
                  Upload New File
                </button>
                <button
                  onClick={() => onUploadSuccess(uploadedRunId!)}
                  className="flex-1 md:flex-initial inline-flex items-center justify-center space-x-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md px-5 h-10 hover:scale-[1.02] active:scale-[0.98]"
                >
                  <span>Start ETL Pipeline</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Profile Tab View */}
            {activeTab === 'profile' && (
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

                      {/* Content Section (Grid mirroring the image mockup) */}
                      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 p-5 min-h-[140px]">
                        {/* 1. Left Panel: General stats */}
                        <div className="md:col-span-3 space-y-2.5 pr-2 border-r border-slate-100 flex flex-col justify-center">
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
                        <div className="bg-slate-50/30 border-t border-slate-100 px-5 py-2 text-[11px] text-muted-foreground flex flex-col space-y-1">
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
            )}

            {/* Preview Tab View */}
            {activeTab === 'preview' && previewData && (
              <div className="flex flex-col bg-card rounded-xl border shadow-sm overflow-hidden w-full">
                <div className="p-4 border-b flex items-center justify-between bg-slate-50/50">
                  <div className="flex items-center space-x-2">
                    <TableIcon className="h-4.5 w-4.5 text-slate-500" />
                    <h2 className="font-semibold text-slate-700 text-sm">{previewData.fileName}</h2>
                    <span className="text-xs text-muted-foreground bg-slate-200/50 border px-2 py-0.5 rounded-full font-medium">
                      {previewData.rowCount.toLocaleString()} rows detected
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground italic">Previewing first 100 rows</p>
                </div>
                
                <div className="overflow-auto relative max-h-[600px]">
                  <table className="w-full text-xs border-separate border-spacing-0">
                    <thead className="sticky top-0 z-20">
                      <tr>
                        <th className="sticky left-0 z-30 bg-slate-100 border-b border-r px-3 py-2 text-center font-medium text-slate-400 w-12 shadow-[1px_0_0_0_#dadce0]">
                        </th>
                        {previewData.headers.map((header, i) => (
                          <th 
                            key={i} 
                            className="bg-slate-100 border-b border-r px-4 py-2 text-left font-semibold text-slate-700 whitespace-nowrap"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewData.rows.map((row, rowIndex) => (
                        <tr key={rowIndex} className="hover:bg-blue-50/20 transition-colors">
                          <td className="sticky left-0 z-10 bg-slate-100 border-b border-r px-3 py-1.5 text-center font-medium text-slate-400 shadow-[1px_0_0_0_#dadce0]">
                            {rowIndex + 1}
                          </td>
                          {row.map((cell, cellIndex) => (
                            <td 
                              key={cellIndex} 
                              className="border-b border-r px-4 py-1.5 text-slate-600 whitespace-nowrap max-w-xs truncate"
                            >
                              {cell === null || cell === undefined || cell === '' ? (
                                <span className="text-slate-300 italic select-none">empty</span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
