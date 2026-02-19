"use client";

import clsx from "clsx";

interface Props {
  className?: string;
  count?: number;
}

export function SkeletonBox({ className }: { className?: string }) {
  return <div className={clsx("skeleton rounded-lg", className)} />;
}

export function StatCardSkeleton() {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <SkeletonBox className="h-3 w-20" />
        <SkeletonBox className="h-4 w-4 rounded" />
      </div>
      <SkeletonBox className="h-7 w-24" />
    </div>
  );
}

export function StatGridSkeleton({ count = 8 }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5 animate-fade-in">
      <SkeletonBox className="h-4 w-48 mb-4" />
      <div className="flex items-end gap-1.5 h-[220px] pt-4">
        {Array.from({ length: 24 }).map((_, i) => (
          <SkeletonBox
            key={i}
            className="flex-1 rounded-t"
            style={{ height: `${20 + Math.random() * 60}%` } as React.CSSProperties}
          />
        ))}
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl overflow-hidden animate-fade-in">
      <div className="p-4 space-y-3">
        <SkeletonBox className="h-3 w-full" />
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <SkeletonBox className="h-3 w-12" />
            <SkeletonBox className="h-3 w-24" />
            <SkeletonBox className="h-3 flex-1" />
            <SkeletonBox className="h-3 w-16" />
            <SkeletonBox className="h-3 w-10" />
          </div>
        ))}
      </div>
    </div>
  );
}
