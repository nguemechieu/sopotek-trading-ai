export function CopyrightNotice({
  className = "",
}: {
  className?: string;
}) {
  const year = new Date().getFullYear();

  return (
    <p className={`text-xs leading-6 text-mist/45 ${className}`.trim()}>
      Copyright © {year} Sopotek Inc. All rights reserved. Sopotek Trading AI is a proprietary platform of Sopotek Inc.
    </p>
  );
}
