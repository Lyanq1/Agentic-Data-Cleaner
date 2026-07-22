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
import { SemanticProfilePanel } from './SemanticProfilePanel';
import { TablePreviewPanel } from './TablePreviewPanel';
import * as XLSX from 'xlsx';
import Papa from 'papaparse';
import { Panel } from '../ui/Panel';
import { Button } from '../ui/Button';

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
  const [cleanFile, setCleanFile] = useState<File | null>(null);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [profileData, setProfileData] = useState<any | null>(null);
  const [requirements, setRequirements] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedRunId, setUploadedRunId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'profile' | 'semantic' | 'preview'>('profile');
  const [error, setError] = useState<string | null>(null);
  const [isBenchmarkMode, setIsBenchmarkMode] = useState(false);

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
    setCleanFile(null);
    setPreviewData(null);
    setProfileData(null);
    setUploadedRunId(null);
    setIsBenchmarkMode(false);
    const input = document.getElementById('file-upload') as HTMLInputElement;
    if (input) input.value = '';
    const cleanInput = document.getElementById('clean-file-upload') as HTMLInputElement;
    if (cleanInput) cleanInput.value = '';
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
      if (isBenchmarkMode && cleanFile) {
        const response = await pipelineApi.uploadBenchmarkFile(file, cleanFile);
        onUploadSuccess(response.run_id);
        return;
      }

      const response = await pipelineApi.uploadFile(file, requirements, cleanFile);
      setUploadedRunId(response.run_id);
      
      try {
        await parseFile(file);
      } catch (parseErr) {
        console.warn('Skipping client-side table preview for this format:', parseErr);
      }
      
      // Poll getProfile until both statistical and semantic profiles are available
      let profile = null;
      for (let i = 0; i < 40; i++) {
        try {
          profile = await pipelineApi.getProfile(response.run_id);
          if (profile && profile.semantic_profile) {
            break;
          }
          // If profile exists but semantic_profile is not ready yet, wait and retry
          await new Promise(resolve => setTimeout(resolve, 1500));
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
    <div className="w-full max-w-6xl flex flex-col pt-4 text-left pb-16 px-2 h-full min-h-0 overflow-y-auto hidden-scrollbar">
      {/* Header section */}
      {!profileData && (
        <div className="mb-6 text-left animate-fade-in">
          <h1 className="text-xl font-bold text-foreground">Upload dataset</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Provide your data file and specific requirements for the AI agent to process.
          </p>
        </div>
      )}

      <div className="space-y-6">
        {/* Upload form Panel */}
        {!profileData && (
          <Panel className="max-w-2xl w-full">
            <form onSubmit={handleUpload} className="p-6 space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-foreground">
                  Data File
                </label>
                {!file ? (
                  <div 
                    className="border border-dashed border-border rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer bg-muted/5 hover:bg-muted/10 transition-colors group" 
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
                    <div className="mb-2">
                      <UploadCloud className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div className="text-xs font-medium mb-0.5 text-foreground">
                      Click to select or drag and drop
                    </div>
                    <div className="text-[10px] text-muted-foreground">
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
                  <div className="relative p-3 rounded-lg border bg-muted/20 flex items-center space-x-3 border-border">
                    <div className="bg-primary/10 p-2 rounded">
                      <FileText className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold truncate text-foreground">{file.name}</p>
                      <p className="text-[10px] text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                    <button 
                      type="button"
                      onClick={handleRemoveFile}
                      className="p-1 hover:bg-muted rounded-full transition-colors cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-foreground">
                  Clean File / Ground Truth (Optional, for testing)
                </label>
                {!cleanFile ? (
                  <div 
                    className="border border-dashed border-border rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer bg-muted/5 hover:bg-muted/10 transition-colors group" 
                    onClick={() => document.getElementById('clean-file-upload')?.click()}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                        const selectedFile = e.dataTransfer.files[0];
                        setCleanFile(selectedFile);
                      }
                    }}
                  >
                    <div className="mb-2">
                      <UploadCloud className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div className="text-xs font-medium mb-0.5 text-foreground">
                      Click to select or drag and drop
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      CSV, JSON, XLSX, SQL, TSV, Parquet
                    </div>
                    <input
                      id="clean-file-upload"
                      type="file"
                      className="hidden"
                      accept=".csv,.json,.xlsx,.xls,.jsonl,.sql,.tsv,.parquet"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          setCleanFile(e.target.files[0]);
                        }
                      }}
                    />
                  </div>
                ) : (
                  <div className="relative p-3 rounded-lg border bg-muted/20 flex items-center space-x-3 border-border">
                    <div className="bg-success/15 p-2 rounded">
                      <FileText className="h-4 w-4 text-success" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold truncate text-foreground">{cleanFile.name}</p>
                      <p className="text-[10px] text-muted-foreground">{(cleanFile.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                    <button 
                      type="button"
                      onClick={() => {
                        setCleanFile(null);
                        const cleanInput = document.getElementById('clean-file-upload') as HTMLInputElement;
                        if (cleanInput) cleanInput.value = '';
                      }}
                      className="p-1 hover:bg-muted rounded-full transition-colors cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </div>
                )}
              </div>

              {cleanFile && (
                <div className="flex items-center gap-3 p-3 border rounded-lg bg-muted/20 border-border hover:bg-muted/30 transition-all duration-300">
                  <input
                    type="checkbox"
                    id="benchmark-mode"
                    checked={isBenchmarkMode}
                    onChange={(e) => setIsBenchmarkMode(e.target.checked)}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary/25 cursor-pointer"
                  />
                  <div className="flex flex-col cursor-pointer select-none" onClick={() => setIsBenchmarkMode(!isBenchmarkMode)}>
                    <label className="text-xs font-semibold text-foreground cursor-pointer">
                      Benchmark Mode
                    </label>
                    <span className="text-[10px] text-muted-foreground">
                      Auto-resolve validations and evaluate F1-score without HIL interrupts.
                    </span>
                  </div>
                </div>
              )}

              {!isBenchmarkMode && (
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-foreground">
                    Business Cleaning Requirements (Optional)
                  </label>
                  <textarea
                    className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[100px] transition-all text-foreground"
                    placeholder="e.g. Clean the email column, drop rows with missing values, extract domain names..."
                    value={requirements}
                    onChange={(e) => setRequirements(e.target.value)}
                  />
                </div>
              )}

              {error && (
                <div className="p-3 border border-destructive/20 bg-destructive/5 text-destructive text-xs rounded-lg flex items-start space-x-2">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                type="submit"
                disabled={!file || isUploading}
                className="w-full cursor-pointer"
              >
                {isUploading ? (
                  <div className="flex items-center space-x-2">
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    <span>Uploading & Profiling...</span>
                  </div>
                ) : (
                  'Upload File'
                )}
              </Button>
            </form>
          </Panel>
        )}

        {/* Post-Upload Statistics View */}
        {profileData && (
          <div className="space-y-6 animate-fade-in">
            {/* Navigation and Actions */}
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between bg-card p-4 rounded-lg border gap-4">
              <div className="flex items-center space-x-4">
                {/* Active Tab triggers */}
                <div className="inline-flex rounded-md border bg-muted p-0.5">
                  <button
                    onClick={() => setActiveTab('profile')}
                    className={`inline-flex items-center space-x-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                      activeTab === 'profile' 
                        ? 'bg-background text-foreground border border-border shadow-xs' 
                        : 'text-muted-foreground hover:text-foreground border border-transparent'
                    }`}
                  >
                    <BarChart3 className="h-3.5 w-3.5" />
                    <span>Statistical Profile</span>
                  </button>
                  <button
                    onClick={() => setActiveTab('semantic')}
                    className={`inline-flex items-center space-x-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                      activeTab === 'semantic' 
                        ? 'bg-background text-foreground border border-border shadow-xs' 
                        : 'text-muted-foreground hover:text-foreground border border-transparent'
                    }`}
                  >
                    <span>Semantic Profile</span>
                  </button>
                  {previewData && (
                    <button
                      onClick={() => setActiveTab('preview')}
                      className={`inline-flex items-center space-x-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                        activeTab === 'preview' 
                          ? 'bg-background text-foreground border border-border shadow-xs' 
                          : 'text-muted-foreground hover:text-foreground border border-transparent'
                      }`}
                    >
                      <TableIcon className="h-3.5 w-3.5" />
                      <span>Table Preview</span>
                    </button>
                  )}
                </div>
                
                <div className="hidden sm:flex items-center space-x-2 text-xs text-muted-foreground">
                  <span className="font-mono text-xs text-muted-foreground bg-muted border px-2 py-0.5 rounded">
                    {profileData.total_rows.toLocaleString()} rows
                  </span>
                  <span>/</span>
                  <span className="font-mono text-xs text-muted-foreground bg-muted border px-2 py-0.5 rounded">
                    {profileData.total_columns} columns
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-3 w-full md:w-auto">
                <Button
                  onClick={handleRemoveFile}
                  variant="outline"
                  className="cursor-pointer"
                >
                  Upload New File
                </Button>
                <Button
                  onClick={() => onUploadSuccess(uploadedRunId!)}
                  className="flex-1 md:flex-initial cursor-pointer"
                >
                  <span>Start ETL Pipeline</span>
                  <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                </Button>
              </div>
            </div>

            {/* Profile Tab View */}
            {activeTab === 'profile' && (
              <StatisticalProfilePanel profileData={profileData} />
            )}

            {/* Semantic Profile Tab View */}
            {activeTab === 'semantic' && (
              <SemanticProfilePanel profileData={profileData} />
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
