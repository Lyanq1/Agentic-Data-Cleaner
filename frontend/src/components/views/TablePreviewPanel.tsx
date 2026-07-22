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
    <div className="flex flex-col bg-card rounded-lg border border-border overflow-hidden w-full text-left">
      <div className="p-4 border-b border-border flex flex-wrap items-center justify-between bg-muted/10 gap-4">
        <div className="flex items-center space-x-2">
          <TableIcon className="h-4.5 w-4.5 text-muted-foreground" />
          <h2 className="font-semibold text-foreground text-sm truncate max-w-[240px]">
            {previewData.fileName}
          </h2>
          <span className="font-mono text-xs text-muted-foreground bg-muted border px-2 py-0.5 rounded">
            {previewData.rowCount.toLocaleString()} rows detected
          </span>
        </div>
        
        {/* Pagination controls */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="text-muted-foreground">
            Showing {startIndex + 1}-{endIndex} of {totalRows} loaded
          </span>
          <div className="flex items-center border border-border rounded bg-card overflow-hidden">
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-1.5 hover:bg-muted disabled:opacity-30 disabled:hover:bg-transparent transition-colors cursor-pointer"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1 font-semibold text-foreground border-x border-border bg-muted/30 select-none">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-1.5 hover:bg-muted disabled:opacity-30 disabled:hover:bg-transparent transition-colors cursor-pointer"
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
              <th className="sticky left-0 z-30 bg-muted border-b border-r border-border px-3 py-2 text-center font-medium text-muted-foreground w-12">
              </th>
              {previewData.headers.map((header, i) => (
                <th 
                  key={i} 
                  className="bg-muted border-b border-r border-border px-4 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap"
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
                <tr key={rowIndex} className="hover:bg-muted/20 transition-colors">
                  <td className="sticky left-0 z-10 bg-muted border-b border-r border-border px-3 py-1.5 text-center font-medium text-muted-foreground">
                    {rowIndex + 1}
                  </td>
                  {row.map((cell, cellIndex) => (
                    <td 
                      key={cellIndex} 
                      className="border-b border-r border-border px-4 py-1.5 text-foreground whitespace-nowrap max-w-xs truncate font-mono"
                    >
                      {cell === null || cell === undefined || cell === '' ? (
                        <span className="text-muted-foreground/30 italic select-none">empty</span>
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
