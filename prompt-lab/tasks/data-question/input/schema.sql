-- Incident tracking database (SQLite).
CREATE TABLE services (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,      -- service name as deployed
    team  TEXT NOT NULL       -- owning team
);

CREATE TABLE incidents (
    id            INTEGER PRIMARY KEY,
    service_id    INTEGER NOT NULL REFERENCES services(id),
    title         TEXT NOT NULL,
    severity      TEXT NOT NULL,      -- SEV1 (worst) to SEV3
    opened_at     TEXT NOT NULL,      -- ISO 8601, UTC
    resolved_at   TEXT,               -- ISO 8601, UTC; NULL while open
    duplicate_of  INTEGER REFERENCES incidents(id)  -- set when filed twice
);
