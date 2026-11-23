ALTER TABLE clients ADD COLUMN IF NOT EXISTS in_pool boolean NOT NULL DEFAULT false;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS joined_on date;
ALTER TABLE client_events ADD COLUMN IF NOT EXISTS promise_label text;
CREATE TABLE IF NOT EXISTS client_actions (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('claim','sanction')),
    letter_number text NOT NULL,
    letter_date date NOT NULL,
    status text NOT NULL,
    comment text NOT NULL DEFAULT '',
    author_id uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS client_pool_idx ON clients(in_pool, assigned_to);
