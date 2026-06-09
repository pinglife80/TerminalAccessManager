import React from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, List } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  totalItems?: number;
  variant?: 'top' | 'bottom';
  showPageSizeSelector?: boolean;
}

// 获取可见的页码列表（带省略号）
const getVisiblePages = (currentPage: number, totalPages: number): (number | 'ellipsis')[] => {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | 'ellipsis')[] = [];

  // 始终显示第一页
  pages.push(1);

  // 计算中间显示的页码范围
  let start = Math.max(2, currentPage - 1);
  let end = Math.min(totalPages - 1, currentPage + 1);

  // 如果当前页靠近开头，显示更多后面的页码
  if (currentPage <= 3) {
    end = 4;
  }

  // 如果当前页靠近结尾，显示更多前面的页码
  if (currentPage >= totalPages - 2) {
    start = totalPages - 3;
  }

  // 添加省略号
  if (start > 2) {
    pages.push('ellipsis');
  }

  // 添加中间页码
  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  // 添加省略号
  if (end < totalPages - 1) {
    pages.push('ellipsis');
  }

  // 始终显示最后一页
  pages.push(totalPages);

  return pages;
};

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  pageSize = 10,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50, 100],
  totalItems,
  variant = 'bottom',
  showPageSizeSelector = true,
}) => {
  const visiblePages = getVisiblePages(currentPage, totalPages);

  const startItem = totalItems ? (currentPage - 1) * pageSize + 1 : 0;
  const endItem = totalItems ? Math.min(currentPage * pageSize, totalItems) : 0;

  // 顶部变体 - 简洁风格
  if (variant === 'top') {
    if (totalPages <= 1) return null;
    return (
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* 信息显示 - 顶部显示精简信息 */}
        <div className="text-sm text-muted-foreground font-medium">
          {totalItems !== undefined && (
            <span className="flex items-center gap-1.5">
              <List className="h-4 w-4 text-muted-foreground" />
              Showing <span className="text-foreground font-semibold">{startItem}</span>
              {' - '}
              <span className="text-foreground font-semibold">{endItem}</span>
              {' of '}
              <span className="text-foreground font-semibold">{totalItems}</span>
              {' items'}
            </span>
          )}
        </div>

        {/* 简洁跳转导航 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Page</span>
          <span className="px-3 py-1.5 bg-blue-50 text-blue-700 font-semibold rounded-lg text-sm">
            {currentPage} / {totalPages}
          </span>
        </div>
      </div>
    );
  }

  // 底部变体 - 完整功能分页导航
  return (
    <div className="bg-card border-t border-border px-4 sm:px-6 py-4">
      <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
        {/* 左侧信息显示区 */}
        <div className="flex items-center gap-4 text-sm">
          {totalItems !== undefined && (
            <span className="text-muted-foreground">
              Showing{' '}
              <span className="font-semibold text-foreground">{startItem}</span>
              {' - '}
              <span className="font-semibold text-foreground">{endItem}</span>
              {' of '}
              <span className="font-semibold text-foreground">{totalItems}</span>
              {' results'}
            </span>
          )}

          {/* 每页数量选择器 */}
          {showPageSizeSelector && onPageSizeChange && (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Per page</span>
              <select
                value={pageSize}
                onChange={(e) => onPageSizeChange(Number(e.target.value))}
                className="px-3 py-1.5 border border-border rounded-lg text-sm font-medium text-muted-foreground bg-card hover:border-border focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors cursor-pointer"
              >
                {pageSizeOptions.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* 右侧导航控制区 - 只有多页时才显示 */}
        {totalPages > 1 && (
        <nav className="flex items-center gap-1.5">
          {/* 首页按钮 - 优化样式 */}
          <button
            type="button"
            onClick={() => onPageChange(1)}
            disabled={currentPage === 1}
            className="inline-flex items-center justify-center p-2 rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-card disabled:hover:border-border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            title="First page"
            aria-label="First page"
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>

          {/* 上一页按钮 */}
          <button
            type="button"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="inline-flex items-center justify-center p-2 rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-card disabled:hover:border-border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            title="Previous page"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          {/* 页码按钮组 */}
          <div className="hidden sm:flex items-center gap-1 mx-2">
            {visiblePages.map((page, idx) => (
              page === 'ellipsis' ? (
                <span
                  key={`ellipsis-${idx}`}
                  className="px-2 py-1 text-muted-foreground font-semibold select-none"
                >
                  ...
                </span>
              ) : (
                <button
                  type="button"
                  key={page}
                  onClick={() => onPageChange(page)}
                  aria-current={page === currentPage ? 'page' : undefined}
                  className={`min-w-[2.25rem] h-9 px-3 inline-flex items-center justify-center rounded-lg text-sm font-semibold transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 ${
                    page === currentPage
                      ? 'bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-200'
                      : 'border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border'
                  }`}
                >
                  {page}
                </button>
              )
            ))}
          </div>

          {/* 移动端显示当前页信息 */}
          <div className="sm:hidden px-3 py-1.5 bg-blue-50 text-blue-700 font-semibold rounded-lg text-sm mx-1">
            {currentPage} / {totalPages}
          </div>

          {/* 下一页按钮 */}
          <button
            type="button"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="inline-flex items-center justify-center p-2 rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-card disabled:hover:border-border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            title="Next page"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>

          {/* 末页按钮 - 优化样式 */}
          <button
            type="button"
            onClick={() => onPageChange(totalPages)}
            disabled={currentPage === totalPages}
            className="inline-flex items-center justify-center p-2 rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-card disabled:hover:border-border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            title="Last page"
            aria-label="Last page"
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        </nav>
        )}
      </div>
    </div>
  );
};

export default Pagination;
