import React, { useState, useEffect } from 'react';
import { 
  UploadCloud, 
  X, 
  FileText, 
  Table as TableIcon, 
  BarChart3, 
  ArrowRight,
  AlertCircle
} from 'lucide-react';
import { pipelineApi } from '../../api/services';
import { StatisticalProfilePanel } from './StatisticalProfilePanel';
import { TablePreviewPanel } from './TablePreviewPanel';
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
                rows: validRows.slice(1, 1001), // Preview first 1000 rows for paging
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
                rows: jsonData.slice(1, 1001), // Preview first 1000 rows for paging
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
              const rowData = rows.slice(0, 1000).map(row => headers.map(h => row[h]));
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
      
      try {
        await parseFile(file);
      } catch (parseErr) {
        console.warn('Skipping client-side table preview for this format:', parseErr);
      }
      
      // Poll getProfile until it is available (since the pipeline runs asynchronously in the background)
      let profile = null;
      for (let i = 0; i < 20; i++) {
        try {
          profile = await pipelineApi.getProfile(response.run_id);
          if (profile) break;
        } catch (err: any) {
          // If it is 404, wait and retry
          if (err.response?.status === 404) {
            await new Promise(resolve => setTimeout(resolve, 1500));
            continue;
          }
          throw err; // For other errors, throw immediately
        }
      }
      
      if (!profile) {
        throw new Error('Statistical profile generation timed out. Please check the backend logs.');
      }

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
              <StatisticalProfilePanel profileData={profileData} />
            )}

            {/* Preview Tab View */}
            {activeTab === 'preview' && previewData && (
              <TablePreviewPanel previewData={previewData} />
            )}
          </div>
        )}
      </div>
    </div>
  );
};
