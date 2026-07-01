import React, { useMemo } from 'react';
import PnLDateSelect, { PERIOD_YEAR_OPTIONS } from './PnLDateSelect';
import { PNL_FORM_INNER_GAP, pnlFormFieldLabelStyle } from './pnlFormDialogChrome';
import {
  endMinDayForRange,
  endMinMonthForRange,
} from '../utils/buildPnlPeriodReport';

const dividerStyle = {
  width: 1,
  alignSelf: 'stretch',
  background: 'var(--border)',
  flexShrink: 0,
  margin: '0 2px',
};

const toolbarRowStyle = {
  display: 'flex',
  alignItems: 'stretch',
  flexWrap: 'nowrap',
  minWidth: 'max-content',
  gap: PNL_FORM_INNER_GAP,
};

const scrollWrapStyle = {
  overflowX: 'auto',
  overflowY: 'hidden',
  flexShrink: 0,
  marginLeft: -2,
  marginRight: -2,
};

const columnStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: PNL_FORM_INNER_GAP,
  flexShrink: 0,
};

const columnHeaderStyle = {
  ...pnlFormFieldLabelStyle,
  marginBottom: 0,
  whiteSpace: 'nowrap',
};

function ColumnHeader({ children, muted }) {
  return (
    <div style={columnHeaderStyle}>
      {children}
      {muted ? (
        <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> {muted}</span>
      ) : null}
    </div>
  );
}

export default function PnLPeriodRangeSelect({
  startYear,
  startMonth,
  startDay,
  endYear,
  endMonth,
  endDay,
  endLinked = true,
  onStartYearChange,
  onStartMonthChange,
  onStartDayChange,
  onEndYearChange,
  onEndMonthChange,
  onEndDayChange,
}) {
  const start = useMemo(
    () => ({ year: startYear, month: startMonth, day: startDay }),
    [startYear, startMonth, startDay],
  );
  const end = useMemo(
    () => ({ year: endYear, month: endMonth, day: endDay }),
    [endYear, endMonth, endDay],
  );

  const endYearOptions = useMemo(
    () => PERIOD_YEAR_OPTIONS.filter((y) => y >= startYear),
    [startYear],
  );
  const endMinMonth = endMinMonthForRange(start, end);
  const endMinDay = endMinDayForRange(start, end);

  return (
    <div style={scrollWrapStyle}>
      <div style={toolbarRowStyle}>
        <div style={columnStyle}>
          <ColumnHeader>From</ColumnHeader>
          <PnLDateSelect
            inline
            hideLabel
            allowAllMonths
            allowAllDays
            label="From"
            year={startYear}
            month={startMonth}
            day={startDay}
            yearOptions={PERIOD_YEAR_OPTIONS}
            onYearChange={onStartYearChange}
            onMonthChange={onStartMonthChange}
            onDayChange={onStartDayChange}
          />
        </div>
        <div style={dividerStyle} aria-hidden />
        <div style={{ ...columnStyle, opacity: endLinked ? 0.72 : 1 }}>
          <ColumnHeader muted="(optional)">Range end</ColumnHeader>
          <PnLDateSelect
            inline
            hideLabel
            allowAllMonths
            allowAllDays
            label="Range end"
            year={endYear}
            month={endMonth}
            day={endDay}
            yearOptions={endYearOptions}
            minMonth={endMinMonth}
            minDay={endMinDay}
            onYearChange={onEndYearChange}
            onMonthChange={onEndMonthChange}
            onDayChange={onEndDayChange}
          />
        </div>
      </div>
    </div>
  );
}
