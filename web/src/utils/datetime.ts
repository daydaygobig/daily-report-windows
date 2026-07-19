import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const BEIJING_TIMEZONE = "Asia/Shanghai";

export const formatBeijingDateTime = (value?: string | null, format = "YYYY-MM-DD HH:mm:ss"): string => {
  if (!value) {
    return "-";
  }
  const date = dayjs.utc(value).tz(BEIJING_TIMEZONE);
  if (!date.isValid()) {
    return value;
  }
  return date.format(format);
};

export const formatDateTime = (value?: string | null): string => {
  if (!value) {
    return "-";
  }
  const date = dayjs(value);
  if (!date.isValid()) {
    return value;
  }
  return date.format("YYYY-MM-DD HH:mm:ss");
};

export const formatUtcDateTime = (value?: string | null): string => {
  if (!value) {
    return "-";
  }
  const date = dayjs.utc(value).local();
  if (!date.isValid()) {
    return value;
  }
  return date.format("YYYY-MM-DD HH:mm:ss");
};
