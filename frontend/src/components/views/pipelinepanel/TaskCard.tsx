import React from "react";
import { roleMeta, ERROR_TYPE_LABELS } from "./utils";

export const TaskCard: React.FC<{
  task: any;
  index: number;
  phase: string;
}> = ({ task, index: _index, phase }) => {
  const meta = roleMeta(task.agent_role);
  return (
    <div className="group rounded-lg border bg-card p-4 hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.color}`}
          >
            {meta.icon}
            {meta.label}
          </span>
          <span className="text-xs text-muted-foreground font-mono">
            {task.task_id}
          </span>
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
          {phase}
        </span>
      </div>

      {task.error_type && (
        <div className="text-sm text-muted-foreground mb-2">
          <span className="font-medium text-foreground">Fixes:</span>{" "}
          {ERROR_TYPE_LABELS[task.error_type] ?? task.error_type}
        </div>
      )}

      {task.target_columns?.length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Target columns
          </div>
          <div className="flex flex-wrap gap-1.5">
            {task.target_columns.map((col: string) => (
              <span
                key={col}
                className="inline-block rounded bg-primary/8 border border-primary/15 px-2 py-0.5 text-xs font-mono text-primary"
              >
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      {task.instructions && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors select-none">
            View instructions
          </summary>
          <pre className="mt-1.5 whitespace-pre-wrap bg-muted/50 rounded p-2 text-[11px] leading-relaxed max-h-40 overflow-auto">
            {typeof task.instructions === "string"
              ? task.instructions
              : JSON.stringify(task.instructions, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
};
