import React from "react";

export const TextIcon: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "w-4 h-4",
}) => (
  <span
    aria-hidden="true"
    className={`inline-flex items-center justify-center text-[10px] font-bold leading-none ${className}`}
  >
    {children}
  </span>
);
