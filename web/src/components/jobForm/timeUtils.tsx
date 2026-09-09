/**
 * HH:mm 时间选择输入（支持 24:00 与手输归一化）。
 * 从 JobFormModal 拆出，逻辑原样搬移。
 */
import { useEffect, useMemo, useState } from "react";
import { AutoComplete } from "antd";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";

export const TIME_BASE = "2020-01-01";

type TimeSelectInputProps = {
  value?: Dayjs;
  onChange?: (value: Dayjs) => void;
  minuteStep?: number;
  placeholder?: string;
  style?: React.CSSProperties;
};

export const parseTime = (value: string) => {
  if (value === "24:00") {
    return dayjs(`${TIME_BASE} 00:00`).add(1, "day");
  }
  return dayjs(`${TIME_BASE} ${value}`);
};

export const formatTime = (value: Dayjs) => {
  if (!value) {
    return "00:00";
  }
  const base = dayjs(TIME_BASE);
  const isTwentyFour =
    value.format("HH:mm") === "00:00" && value.isSame(base.add(1, "day"), "day");
  if (isTwentyFour) {
    return "24:00";
  }
  return value.format("HH:mm");
};

export const formatTimeValue = (value?: Dayjs) => (value ? formatTime(value) : "");

const buildTimeOptions = (minuteStep: number) => {
  const options: { value: string }[] = [];
  for (let minutes = 0; minutes < 24 * 60; minutes += minuteStep) {
    const hour = Math.floor(minutes / 60);
    const minute = minutes % 60;
    options.push({
      value: `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`
    });
  }
  options.push({ value: "24:00" });
  return options;
};

const normalizeTimeText = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(trimmed);
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour === 24 && minute === 0) {
    return parseTime("24:00");
  }
  if (hour >= 0 && hour < 24 && minute >= 0 && minute < 60) {
    const normalized = `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`;
    return parseTime(normalized);
  }
  return null;
};

export function TimeSelectInput({ value, onChange, minuteStep = 5, placeholder, style }: TimeSelectInputProps) {
  const [draft, setDraft] = useState(() => formatTimeValue(value));
  const [open, setOpen] = useState(false);
  const options = useMemo(() => buildTimeOptions(minuteStep), [minuteStep]);

  useEffect(() => {
    setDraft(formatTimeValue(value));
  }, [value]);

  const commitValue = (next: string) => {
    const parsed = normalizeTimeText(next);
    if (parsed) {
      onChange?.(parsed);
    }
    return parsed;
  };

  return (
    <AutoComplete
      open={open}
      value={draft}
      options={options}
      placeholder={placeholder}
      style={style}
      filterOption={(input, option) => (option?.value ?? "").includes(input)}
      onFocus={() => setOpen(true)}
      onChange={(next) => {
        setDraft(next);
        setOpen(true);
        commitValue(next);
      }}
      onSelect={(next) => {
        const parsed = commitValue(next);
        if (parsed) {
          setDraft(formatTime(parsed));
        }
        setOpen(false);
      }}
      onBlur={() => {
        const parsed = normalizeTimeText(draft);
        if (parsed) {
          onChange?.(parsed);
          setDraft(formatTime(parsed));
        } else {
          setDraft(formatTimeValue(value));
        }
        setOpen(false);
      }}
    />
  );
}
