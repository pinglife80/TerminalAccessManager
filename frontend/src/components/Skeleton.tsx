import React from 'react';

const SkeletonLine: React.FC<{ width?: string; height?: string; className?: string }> = ({
  width = '100%',
  height = '1rem',
  className = '',
}) => (
  <div
    className={`bg-muted rounded animate-pulse ${className}`}
    style={{ width, height }}
  />
);

const SkeletonCircle: React.FC<{ size?: string; className?: string }> = ({
  size = '2rem',
  className = '',
}) => (
  <div
    className={`bg-muted rounded-full animate-pulse ${className}`}
    style={{ width: size, height: size }}
  />
);

export const CardSkeleton: React.FC = () => (
  <div className="bg-card shadow rounded-lg p-6">
    <div className="flex items-center mb-4">
      <SkeletonCircle size="4rem" className="mr-4" />
      <div className="flex-1">
        <SkeletonLine width="60%" className="mb-2" />
        <SkeletonLine width="40%" height="0.75rem" />
      </div>
    </div>
    <div className="space-y-2">
      <SkeletonLine />
      <SkeletonLine width="80%" />
      <SkeletonLine width="60%" />
    </div>
  </div>
);

export const StatsCardSkeleton: React.FC = () => (
  <div className="bg-card shadow rounded-lg p-5">
    <div className="flex items-center">
      <div className="flex-shrink-0">
        <SkeletonCircle size="2.5rem" />
      </div>
      <div className="ml-5 w-0 flex-1">
        <dl>
          <dt>
            <SkeletonLine width="60%" height="0.75rem" className="mb-2" />
          </dt>
          <dd>
            <SkeletonLine width="40%" height="1.5rem" />
          </dd>
        </dl>
      </div>
    </div>
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number; columns?: number }> = ({
  rows = 5,
  columns = 6,
}) => (
  <div className="bg-card shadow rounded-lg overflow-hidden">
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-background">
          <tr>
            {Array.from({ length: columns }).map((_, i) => (
              <th
                key={i}
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
              >
                <SkeletonLine width="80%" height="0.75rem" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-card divide-y divide-border">
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-background transition-colors">
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex} className="px-6 py-4 whitespace-nowrap">
                  {colIndex === 0 ? (
                    <div className="flex items-center">
                      <SkeletonCircle size="1.5rem" className="mr-2" />
                      <SkeletonLine width="60%" />
                    </div>
                  ) : (
                    <SkeletonLine width={colIndex % 2 === 0 ? '70%' : '50%'} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

export const DashboardSkeleton: React.FC = () => (
  <div className="min-h-full bg-background p-8">
    <div className="mb-8">
      <SkeletonLine width="30%" height="2rem" className="mb-2" />
      <SkeletonLine width="20%" height="1rem" />
    </div>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <StatsCardSkeleton />
      <StatsCardSkeleton />
      <StatsCardSkeleton />
    </div>

    <CardSkeleton />
  </div>
);

export const PageSkeleton: React.FC = () => (
  <div className="min-h-full bg-background p-8">
    <div className="mb-8 flex flex-col md:flex-row md:items-center md:justify-between">
      <div>
        <SkeletonLine width="40%" height="2rem" className="mb-2" />
        <SkeletonLine width="30%" height="1rem" />
      </div>
      <div className="mt-4 md:mt-0">
        <SkeletonLine width="12rem" height="2.5rem" />
      </div>
    </div>

    <div className="bg-card shadow rounded-lg p-4 mb-6">
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1">
          <SkeletonLine width="100%" height="2.5rem" />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <SkeletonLine width="10rem" height="2.5rem" />
          <SkeletonLine width="8rem" height="2.5rem" />
          <SkeletonLine width="8rem" height="2.5rem" />
        </div>
      </div>
    </div>

    <TableSkeleton rows={5} columns={7} />
  </div>
);

export default {
  SkeletonLine,
  SkeletonCircle,
  CardSkeleton,
  StatsCardSkeleton,
  TableSkeleton,
  DashboardSkeleton,
  PageSkeleton,
};