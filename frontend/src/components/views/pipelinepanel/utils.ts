import React from "react";
import { TextIcon } from "./TextIcon";

export const ROLE_META: Record<
  string,
  { label: string; color: string; icon: React.ReactNode }
> = {
  dedup_agent: {
    label: "Deduplication",
    color: "bg-violet-500/10 text-violet-600 border-violet-200",
    icon: React.createElement(TextIcon, null, "[]"),
  },
  null_agent: {
    label: "Null Handling",
    color: "bg-sky-500/10 text-sky-600 border-sky-200",
    icon: React.createElement(TextIcon, null, "*"),
  },
  typecast_agent: {
    label: "Type Casting",
    color: "bg-amber-500/10 text-amber-600 border-amber-200",
    icon: React.createElement(TextIcon, null, "T"),
  },
  duplicate_handler: {
    label: "Deduplication",
    color: "bg-violet-500/10 text-violet-600 border-violet-200",
    icon: React.createElement(TextIcon, null, "[]"),
  },
  null_type_handler: {
    label: "Null & Type Fix",
    color: "bg-sky-500/10 text-sky-600 border-sky-200",
    icon: React.createElement(TextIcon, null, "*"),
  },
  validator: {
    label: "Validation",
    color: "bg-emerald-500/10 text-emerald-600 border-emerald-200",
    icon: React.createElement(TextIcon, null, "#"),
  },
  planner: {
    label: "Planner",
    color: "bg-amber-500/10 text-amber-600 border-amber-200",
    icon: React.createElement(TextIcon, null, "|||"),
  },
};

export function roleMeta(role: string) {
  return (
    ROLE_META[role] ?? {
      label: role,
      color: "bg-gray-100 text-gray-600 border-gray-200",
      icon: React.createElement(TextIcon, null, "*"),
    }
  );
}

export function formatDisplayValue(value: any, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function getOptionConsequence(
  consequences: any,
  optionText: string,
): string | null {
  if (!consequences) return null;

  // Case 1: consequences is a dictionary
  if (typeof consequences === "object" && !Array.isArray(consequences)) {
    // Exact match
    if (consequences[optionText]) {
      return consequences[optionText];
    }
    // Case-insensitive key check
    const lowerOpt = optionText.toLowerCase();
    for (const key of Object.keys(consequences)) {
      if (key.toLowerCase() === lowerOpt) {
        return consequences[key];
      }
      // Substring check
      if (
        lowerOpt.includes(key.toLowerCase()) ||
        key.toLowerCase().includes(lowerOpt)
      ) {
        return consequences[key];
      }
    }
  }

  // Case 2: consequences is a string
  if (typeof consequences === "string") {
    const lines = consequences.split("\n");
    const cleanOpt = optionText
      .replace(/^\([^)]+\)\s*/, "")
      .toLowerCase()
      .trim();

    for (const line of lines) {
      if (
        line.toLowerCase().includes(cleanOpt) ||
        cleanOpt.includes(line.toLowerCase())
      ) {
        return line.trim();
      }
    }
    return consequences;
  }

  return null;
}

export const ERROR_TYPE_LABELS: Record<string, string> = {
  duplicate: "Duplicate rows",
  null: "Null values",
  type_cast: "Type casting",
  format: "Format issues",
};

export const VALIDATION_RULE_LABELS: Record<string, string> = {
  dataframe_no_exact_duplicates: "No exact duplicate rows",
  no_duplicate_rows: "No exact duplicate rows",
  column_unique: "Must be unique",
  is_unique: "Must be unique",
  no_unresolved_duplicate_groups: "No unresolved duplicate groups",
  null_rate_lt: "Null rate < threshold",
  null_rate_lte: "Max null rate",
  no_disguised_missing_values: "No disguised missing values",
  expected_str_pattern: "Matches string pattern",
  duplicate_rows_eq_0: "Duplicate rows must be 0",
};

export const SEVERITY_STYLES: Record<string, string> = {
  error: "bg-red-100 text-red-700 border-red-200",
  warning: "bg-amber-100 text-amber-700 border-amber-200",
  info: "bg-blue-100 text-blue-700 border-blue-200",
};

export function tryFormatToISO(input: string, expectedType: string): string {
  if (!input) return input;
  if (expectedType === "str") return input;
  
  let prefix = "";
  let valPart = input.trim();
  
  const prefixes = [
    "fill_value:", 
    "fill_value", 
    "fill", 
    "impute",
    "strategy:"
  ];
  
  for (const p of prefixes) {
    if (valPart.toLowerCase().startsWith(p)) {
      const idx = p.length;
      prefix = valPart.substring(0, idx);
      let remaining = valPart.substring(idx);
      const spacesMatch = remaining.match(/^\s+/);
      if (spacesMatch) {
        prefix += spacesMatch[0];
        remaining = remaining.substring(spacesMatch[0].length);
      }
      valPart = remaining.trim();
      break;
    }
  }
  
  if (expectedType === "time" || expectedType === "datetime" || expectedType === "str" || !expectedType) {
    const timeRegex = /^(\d{1,2})[:h](\d{2})(?::m?(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?$/i;
    const match = valPart.match(timeRegex);
    if (match) {
      let hours = parseInt(match[1], 10);
      const minutes = parseInt(match[2], 10);
      const seconds = match[3] ? parseInt(match[3], 10) : 0;
      const ampm = match[4] ? match[4].toLowerCase().replace(/\./g, "") : null;
      
      if (hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59 && seconds >= 0 && seconds <= 59) {
        if (ampm) {
          if (ampm === "pm" && hours < 12) {
            hours += 12;
          } else if (ampm === "am" && hours === 12) {
            hours = 0;
          }
        }
        const hStr = String(hours).padStart(2, "0");
        const mStr = String(minutes).padStart(2, "0");
        const sStr = String(seconds).padStart(2, "0");
        
        if (expectedType !== "datetime") {
          return `${prefix}${hStr}:${mStr}:${sStr}`;
        } else {
          // If expectedType is datetime but they only provided time, use today's date
          const today = new Date();
          const y = today.getFullYear();
          const m = String(today.getMonth() + 1).padStart(2, "0");
          const d = String(today.getDate()).padStart(2, "0");
          return `${prefix}${y}-${m}-${d}T${hStr}:${mStr}:${sStr}`;
        }
      }
    }
  }

  if (expectedType === "date" || expectedType === "str" || !expectedType) {
    const dateRegex = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/;
    const match = valPart.match(dateRegex);
    if (match) {
      const y = match[1];
      const m = match[2].padStart(2, "0");
      const d = match[3].padStart(2, "0");
      return `${prefix}${y}-${m}-${d}`;
    }
    const date = new Date(valPart);
    if (!isNaN(date.getTime())) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, "0");
      const d = String(date.getDate()).padStart(2, "0");
      return `${prefix}${y}-${m}-${d}`;
    }
  } else if (expectedType === "datetime") {
    const date = new Date(valPart);
    if (!isNaN(date.getTime())) {
      return `${prefix}${date.toISOString().split(".")[0]}`;
    }
  }
  
  return input;
}
