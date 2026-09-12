/** Dense operations table with sorting and the four data states. */

import { useMemo, useState, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import { cn } from "@/lib/cn";

export interface Column<T> {
  key: string;
  header: string;
  /** Cell renderer. */
  cell: (row: T) => ReactNode;
  /** Sort value; omit to make the column unsortable. */
  sortValue?: (row: T) => string | number | null;
  width?: string;
  align?: "left" | "right";
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyMessage?: string;
  emptyHint?: string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  /** Initial sort column key. */
  defaultSort?: string;
  defaultDescending?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading = false,
  error,
  onRetry,
  emptyMessage = "No records found.",
  emptyHint,
  onRowClick,
  selectedKey,
  defaultSort,
  defaultDescending = true,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(defaultSort);
  const [descending, setDescending] = useState(defaultDescending);

  const sorted = useMemo(() => {
    if (!rows) return rows;
    const column = columns.find((entry) => entry.key === sortKey);
    if (!column?.sortValue) return rows;

    const get = column.sortValue;
    return [...rows].sort((a, b) => {
      const left = get(a);
      const right = get(b);
      if (left === right) return 0;
      if (left === null) return 1;
      if (right === null) return -1;
      const result = left < right ? -1 : 1;
      return descending ? -result : result;
    });
  }, [rows, columns, sortKey, descending]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setDescending((current) => !current);
    } else {
      setSortKey(key);
      setDescending(true);
    }
  };

  return (
    <AsyncBoundary
      isLoading={isLoading}
      error={error}
      data={sorted}
      onRetry={onRetry}
      emptyMessage={emptyMessage}
      emptyHint={emptyHint}
      loadingVariant="rows"
      loadingRows={6}
    >
      {(data) => (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-line-strong border-b">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    style={column.width ? { width: column.width } : undefined}
                    className={cn(
                      "text-ink-subtle px-2.5 py-1.5 text-2xs font-semibold tracking-wide uppercase",
                      column.align === "right" ? "text-right" : "text-left",
                    )}
                  >
                    {column.sortValue ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className="hover:text-ink inline-flex items-center gap-1 transition-colors"
                      >
                        {column.header}
                        {sortKey === column.key ? (
                          <Icon
                            name={descending ? "chevronDown" : "chevronRight"}
                            size={11}
                            className={descending ? "" : "-rotate-90"}
                          />
                        ) : null}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => {
                const key = rowKey(row);
                return (
                  <tr
                    key={key}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(
                      "border-line-subtle border-b last:border-0",
                      onRowClick && "cursor-pointer",
                      selectedKey === key ? "bg-accent-dim" : onRowClick && "hover:bg-surface-hover",
                    )}
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={cn(
                          "text-ink-muted px-2.5 py-1.5 align-middle",
                          column.align === "right" && "text-right tabular-nums",
                        )}
                      >
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AsyncBoundary>
  );
}
