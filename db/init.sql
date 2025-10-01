CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('operator','supervisor','admin')),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products(
  item_code TEXT PRIMARY KEY,
  item_name TEXT NOT NULL,
  ABC TEXT, XYZ TEXT,
  unit_cost NUMERIC,
  monthly_mean NUMERIC, monthly_std NUMERIC, annual_qty NUMERIC,
  ACV NUMERIC, z_level NUMERIC, lead_time_days INT,
  SS INT, ROP INT, EOQ INT, SMIN INT, SMAX INT,
  OnHand INT, BelowROP BOOLEAN,
  uom TEXT NOT NULL DEFAULT 'UN',
  requires_lot BOOLEAN NOT NULL DEFAULT FALSE,
  requires_serial BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stock(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  item_code TEXT NOT NULL REFERENCES products(item_code),
  lot TEXT NULL,
  serial TEXT NULL,
  expiry DATE NULL,
  location TEXT NOT NULL DEFAULT 'MAIN',
  qty INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS moves(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  type TEXT NOT NULL CHECK (type IN ('inbound','outbound','transfer','return')),
  doc_type TEXT NOT NULL CHECK (doc_type IN ('PO','SO','TR','RT')),
  doc_number TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','approved','pending','cancelled')) DEFAULT 'pending',
  created_by UUID NOT NULL REFERENCES users(id),
  approved_by UUID NULL REFERENCES users(id),
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS move_lines(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  move_id UUID NOT NULL REFERENCES moves(id) ON DELETE CASCADE,
  item_code TEXT NOT NULL REFERENCES products(item_code),
  lot TEXT NULL,
  serial TEXT NULL,
  expiry DATE NULL,
  qty INT NOT NULL,
  qty_confirmed INT NOT NULL DEFAULT 0,
  location_from TEXT NOT NULL DEFAULT 'MAIN',
  location_to TEXT NOT NULL DEFAULT 'MAIN'
);

CREATE TABLE IF NOT EXISTS audit(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  user_id UUID NULL REFERENCES users(id),
  ts TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS print_jobs(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  printer_name TEXT NOT NULL,
  payload_zpl TEXT NOT NULL,
  copies INT NOT NULL DEFAULT 1,
  status TEXT NOT NULL CHECK (status IN ('queued','sent','error','retry')) DEFAULT 'queued',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);

INSERT INTO users(username, password_hash, role)
VALUES ('admin', '$2b$12$1nqmxCFIvossKXkg0vvicuKEGDYZUtm1gea3xMN2rf4hZ8alJFvum', 'admin')
ON CONFLICT DO NOTHING;
