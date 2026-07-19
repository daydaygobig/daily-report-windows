import { useCallback, useEffect, useMemo, useState } from "react";
import { Resizable } from "react-resizable";
import type { ColumnsType } from "antd/es/table";

type ColumnWithKey<RecordType> = ColumnsType<RecordType>[number] & { key: string };

const readCache = (storageKey: string): Record<string, number> => {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const stored = window.localStorage.getItem(storageKey);
    return stored ? (JSON.parse(stored) as Record<string, number>) : {};
  } catch {
    return {};
  }
};

const writeCache = (storageKey: string, widths: Record<string, number>) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {
    // ignore
  }
};

export function useResizableColumns<RecordType>(
  baseColumns: ColumnWithKey<RecordType>[],
  storageKey: string,
  defaultWidths: Record<string, number> = {},
  fallbackWidth = 160
) {
  const [columns, setColumns] = useState<ColumnWithKey<RecordType>[]>(() => {
    const cache = readCache(storageKey);
    return baseColumns.map((column) => ({
      ...column,
      width: column.width ?? cache[column.key] ?? defaultWidths[column.key] ?? fallbackWidth
    }));
  });

  useEffect(() => {
    const cache = readCache(storageKey);
    setColumns((prev) =>
      baseColumns.map((column) => {
        const prevEntry = prev.find((item) => item.key === column.key);
        return {
          ...column,
          width: column.width ?? prevEntry?.width ?? cache[column.key] ?? defaultWidths[column.key] ?? fallbackWidth
        };
      })
    );
  }, [baseColumns, defaultWidths, fallbackWidth, storageKey]);

  const handleResize = useCallback(
    (index: number) =>
      (_: unknown, { size }: { size: { width: number } }) => {
        setColumns((prev) => {
          const next = [...prev];
          next[index] = { ...next[index], width: size.width };
          return next;
        });
      },
    []
  );

  useEffect(() => {
    const widths = columns.reduce<Record<string, number>>((acc, column) => {
      if (column.width) {
        acc[column.key] = column.width as number;
      }
      return acc;
    }, {});
    writeCache(storageKey, widths);
  }, [columns, storageKey]);

  const ResizableTitle = useCallback(
    (props: any) => {
      const { onResize, width, ...restProps } = props;
      if (!width) {
        return <th {...restProps} />;
      }
      return (
        <Resizable
          width={width}
          height={0}
          handle={
            <span
              onClick={(e) => e.stopPropagation()}
              style={{ position: "absolute", right: -6, top: 0, bottom: 0, width: 12, cursor: "col-resize", zIndex: 1 }}
            />
          }
          onResize={onResize}
          draggableOpts={{ enableUserSelectHack: false }}
        >
          <th {...restProps} style={{ width }} />
        </Resizable>
      );
    },
    []
  );

  const mergedColumns = useMemo(
    () =>
      columns.map((col, index) => ({
        ...col,
        onHeaderCell: (column: ColumnWithKey<RecordType>) => ({
          width: column.width,
          onResize: handleResize(index)
        })
      })),
    [columns, handleResize]
  );

  const components = useMemo(
    () => ({
      header: {
        cell: ResizableTitle
      }
    }),
    [ResizableTitle]
  );

  return { columns: mergedColumns as ColumnsType<RecordType>, components };
}
