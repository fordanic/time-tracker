export interface Timer {
  entry_id: number;
  project: string;
  activity: string;
  started_at: string;
  stopped_at?: string;
  note: string | null;
  duration_seconds?: number;
}

export interface Reminder {
  kind: "active" | "inactive";
  project: string | null;
  activity: string | null;
  reason: string;
  idle_threshold_minutes: number | null;
}

export interface RecentActivity {
  project: string;
  activity: string;
}

export interface ArchivedActivity extends RecentActivity {
  project_archived: boolean;
}

export interface ReminderSettings {
  inactive_enabled: boolean;
  inactive_interval_minutes: number;
  active_enabled: boolean;
  active_interval_minutes: number;
  window_enabled: boolean;
  window_weekdays: number[];
  window_start: string;
  window_end: string;
  snooze_minutes: number;
  idle_enabled: boolean;
  idle_threshold_minutes: number;
}

export interface Bootstrap {
  active: Timer | null;
  reminder: Reminder | null;
  projects: string[];
  activities: Record<string, string[]>;
  recent: RecentActivity[];
  completed: Timer[];
  today_completed_seconds: number;
  archived_projects: string[];
  archived_activities: ArchivedActivity[];
  settings: ReminderSettings;
  export_delimiter: "," | "|";
  idle_detection: { available: boolean };
  configuration_path: string;
}

export interface ReviewFilter {
  preset: "all_time" | "today" | "this_week" | "this_month" | "custom";
  start_date: string | null;
  end_date: string | null;
  project: string | null;
  activity: string | null;
}

export interface Segment extends Timer {
  day: string;
  stopped_at: string;
  duration_seconds: number;
}

export interface ReviewData {
  groups: Array<{ day: string; duration_seconds: number; segments: Segment[] }>;
  daily_summaries: Array<{
    day: string;
    project: string;
    activity: string;
    duration_seconds: number;
  }>;
  range_summaries: Array<{
    project: string;
    activity: string;
    duration_seconds: number;
  }>;
  projects: string[];
  activities: string[];
}
