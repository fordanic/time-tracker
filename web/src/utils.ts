export function duration(seconds: number): string {
  const wholeMinutes = Math.ceil(Math.max(0, seconds) / 60);
  return `${Math.floor(wholeMinutes / 60)}h ${String(wholeMinutes % 60).padStart(2, "0")}m`;
}

export function elapsed(startedAt: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function localInputValue(instant: string): string {
  const value = new Date(instant);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

export function offsetInstant(localValue: string): string {
  return new Date(localValue).toISOString();
}
