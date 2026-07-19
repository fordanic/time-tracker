CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    archived_at_utc INTEGER,
    created_at_utc INTEGER NOT NULL
);

CREATE TABLE activities (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    archived_at_utc INTEGER,
    created_at_utc INTEGER NOT NULL,
    UNIQUE (project_id, name)
);

CREATE TABLE time_entries (
    id INTEGER PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    started_at_utc INTEGER NOT NULL,
    stopped_at_utc INTEGER,
    note TEXT,
    created_at_utc INTEGER NOT NULL,
    CHECK (stopped_at_utc IS NULL OR stopped_at_utc >= started_at_utc)
);

CREATE UNIQUE INDEX one_active_time_entry
ON time_entries ((1))
WHERE stopped_at_utc IS NULL;
