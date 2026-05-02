export function formatDateTimeZhCn(value?: string | null): string {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export function formatShortDateTimeZhCn(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function sortUniqueNumbers(values: number[]): number[] {
  return [...new Set(values)].sort((left, right) => left - right);
}
