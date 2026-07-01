import { useCallback, useMemo, useRef, useState } from 'react';
import {
  columnWidthKey,
  defaultWidthForColumn,
  mergeColumnWidths,
  minWidthForColumn,
  readStoredColumnWidths,
  writeStoredColumnWidths,
} from './stockListColumnStorage';
import { stockListGridTemplateColumns } from '../components/stockTableChrome';

export function useStockListColumnWidths(columnDefs) {
  const defsRef = useRef(columnDefs);
  defsRef.current = columnDefs;

  const [widths, setWidths] = useState(() => mergeColumnWidths(columnDefs));
  const [resizingKey, setResizingKey] = useState(null);
  const widthsRef = useRef(widths);
  widthsRef.current = widths;

  const getWidth = useCallback((col) => {
    const wk = columnWidthKey(col);
    return widths[wk] ?? mergeColumnWidths([col])[wk];
  }, [widths]);

  const startResize = useCallback((col, e) => {
    e.preventDefault();
    e.stopPropagation();
    const wk = columnWidthKey(col);
    const startX = e.clientX;
    const startW = widthsRef.current[wk];
    const minW = minWidthForColumn(col);
    setResizingKey(wk);

    function onMouseMove(ev) {
      const next = Math.max(minW, Math.round(startW + ev.clientX - startX));
      setWidths((prev) => {
        const updated = { ...prev, [wk]: next };
        widthsRef.current = updated;
        return updated;
      });
    }

    function onMouseUp() {
      setResizingKey(null);
      const stored = readStoredColumnWidths();
      writeStoredColumnWidths({ ...stored, ...widthsRef.current });
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, []);

  const gridTemplateColumns = useMemo(
    () => stockListGridTemplateColumns(columnDefs, (col) => {
      const wk = columnWidthKey(col);
      return widths[wk] ?? defaultWidthForColumn(col);
    }),
    [columnDefs, widths],
  );

  return { getWidth, startResize, resizingKey, widths, gridTemplateColumns };
}
