-- H-00 schema: call list, client flags, workflow history and import diagnostics.

ALTER TABLE report_periods DROP CONSTRAINT IF EXISTS report_periods_quarter_check;
ALTER TABLE report_periods
    ADD CONSTRAINT report_periods_quarter_check CHECK (quarter BETWEEN 0 AND 4);

INSERT INTO report_periods (year, quarter, label) VALUES
    (2025, 0, 'Y2025'),
    (2026, 1, '2026Q1'),
    (2026, 2, '2026Q2'),
    (2026, 3, '2026Q3')
ON CONFLICT (year, quarter) DO UPDATE SET label = EXCLUDED.label;

ALTER TABLE clients ALTER COLUMN inn DROP NOT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS inactive BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS excluded_reason TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'Не в работе';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS assigned_to UUID REFERENCES users(id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS promised_at DATE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_contact_at DATE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_name TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_phone TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS source_key_mode TEXT NOT NULL DEFAULT 'anonymous';

CREATE INDEX IF NOT EXISTS clients_call_list_idx
    ON clients (excluded, inactive, assigned_to, stage);
CREATE INDEX IF NOT EXISTS clients_external_id_idx ON clients (external_id);

CREATE TABLE IF NOT EXISTS client_tags (
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (client_id, tag)
);

CREATE TABLE IF NOT EXISTS client_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('call', 'email', 'comment', 'system', 'claim', 'slice')),
    event_date DATE NOT NULL,
    result TEXT,
    promised_at DATE,
    comment TEXT,
    author_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS client_events_client_date_idx
    ON client_events (client_id, event_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS import_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind TEXT NOT NULL CHECK (kind IN ('clients', 'snapshot')),
    file_name TEXT NOT NULL,
    period_scope TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('completed', 'partial', 'failed')),
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_ok INTEGER NOT NULL DEFAULT 0,
    rows_errors INTEGER NOT NULL DEFAULT 0,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS import_errors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    import_id UUID NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('row', 'file')),
    row_number INTEGER,
    column_name TEXT,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    raw_value TEXT,
    external_id TEXT,
    period_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS import_errors_import_idx ON import_errors (import_id, row_number);

ALTER TABLE slice_records ADD COLUMN IF NOT EXISTS source_sheet TEXT;
ALTER TABLE slice_records ADD COLUMN IF NOT EXISTS source_row INTEGER;
ALTER TABLE slice_records ADD COLUMN IF NOT EXISTS raw_external_id TEXT;

ALTER TABLE slices ADD COLUMN IF NOT EXISTS file_name TEXT;
ALTER TABLE slices ADD COLUMN IF NOT EXISTS source_profile TEXT;

INSERT INTO users (id, username, password_hash, role) VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin', 'demo-no-login', 'admin'),
    ('00000000-0000-0000-0000-000000000002', 'operator-a', 'demo-no-login', 'operator'),
    ('00000000-0000-0000-0000-000000000003', 'operator-b', 'demo-no-login', 'operator')
ON CONFLICT (username) DO NOTHING;
