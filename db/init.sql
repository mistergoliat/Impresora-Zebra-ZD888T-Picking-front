-- Database initialization script for picking application
-- Creates the stock table and supporting constraints.

CREATE TABLE IF NOT EXISTS stock (
    id SERIAL PRIMARY KEY,
    item_code VARCHAR(64) NOT NULL,
    lot VARCHAR(64),
    serial VARCHAR(64),
    location VARCHAR(64) NOT NULL,
    quantity NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- Maintain uniqueness across item, lot, serial and location while
-- treating NULL values as empty strings to mimic legacy behaviour.
CREATE UNIQUE INDEX IF NOT EXISTS stock_item_lot_serial_location_uq
    ON stock (item_code, COALESCE(lot, ''), COALESCE(serial, ''), location);
