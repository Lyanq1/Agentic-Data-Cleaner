import React from "react";

export const SpinnerIcon: React.FC<{ className?: string }> = ({
  className = "w-4 h-4",
}) => (
  <span
    aria-hidden="true"
    className={`inline-block rounded-full border-2 border-current border-t-transparent animate-spin ${className}`}
  />
);
