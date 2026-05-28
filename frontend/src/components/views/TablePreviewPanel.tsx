import React, { useState } from 'react';
import { Table as TableIcon, ChevronLeft, ChevronRight } from 'lucide-react';

interface PreviewData {
  headers: string[];
  rows: any[][];
  fileName: string;
  rowCount: number;
}

interface TablePreviewPanelProps {
  previewData: PreviewData;
}

export const TablePreviewPanel: React.FC<TablePreviewPanelProps> = ({ previewData }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 100;
  
  const totalRows = previewData.rows.length;
  const totalPages = Math.max(Math.ceil(totalRows / rowsPerPage), 1);
  
  // Safe page navigation
  const goToPage = (page: number) => {
    const pageNum = Math.max(1, Math.min(page, totalPages));
    setCurrentPage(pageNum);
  };

  const startIndex = (currentPage - 1) * rowsPerPage;
  const endIndex = Math.min(startIndex + rowsPerPage, totalRows);
  const currentRows = previewData.rows.slice(startIndex, endIndex);

  return (
    <div className="flex flex-col bg-card rounded-xl border shadow-sm overflow-hidden w-full text-left">
      <div className="p-4 border-b flex flex-wrap items-center justify-between bg-slate-50/50 gap-4">
        <div className="flex items-center space-x-2">
          <TableIcon className="h-4.5 w-4.5 text-slate-500" />
          <h2 className="font-semibold text-slate-700 text-sm truncate max-w-[240px]">
            {previewData.fileName}
          </h2>
          <span className="text-xs text-muted-foreground bg-slate-200/50 border px-2 py-0.5 rounded-full font-medium">
            {previewData.rowCount.toLocaleString()} rows detected
          </span>
        </div>
        
        {/* Pagination controls */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="text-muted-foreground">
            Showing {startIndex + 1}-{endIndex} of {totalRows} loaded
          </span>
          <div className="flex items-center border rounded bg-white shadow-sm overflow-hidden">
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-1.5 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1 font-semibold text-slate-700 border-x bg-slate-50/40 select-none">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-1.5 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              title="Next Page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
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
            {currentRows.map((row, index) => {
              const rowIndex = startIndex + index;
              return (
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
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
