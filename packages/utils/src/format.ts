import { format, formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

export function formatDate(date: string | Date, pattern: string = "yyyy-MM-dd"): string {
  return format(new Date(date), pattern, { locale: zhCN });
}

export function formatDateTime(date: string | Date): string {
  return format(new Date(date), "yyyy-MM-dd HH:mm", { locale: zhCN });
}

export function formatRelative(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: zhCN });
}

export function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function formatSalary(range: string): string {
  return range;
}
