import React from "react";
import { TextIcon } from "./TextIcon";

export const ROLE_META: Record<
  string,
  { label: string; color: string; icon: React.ReactNode }
> = {
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

export const SEVERITY_STYLES: Record<string, string> = {
  error: "bg-red-100 text-red-700 border-red-200",
  warning: "bg-amber-100 text-amber-700 border-amber-200",
  info: "bg-blue-100 text-blue-700 border-blue-200",
};
