ALTER TABLE customers ADD COLUMN external_id TEXT NOT NULL;
CREATE INDEX customers_external_id_idx ON customers (external_id);
ALTER TABLE customers DROP COLUMN legacy_code;
