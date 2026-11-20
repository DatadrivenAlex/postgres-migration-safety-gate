-- Expand: add nullable field. Backfill in application-controlled batches.
ALTER TABLE customers ADD COLUMN external_id TEXT;
-- Build separately without a transaction in a production migration runner.
CREATE INDEX CONCURRENTLY customers_external_id_idx ON customers (external_id);
-- After backfill and application rollout, validate/enforce in a later release.
ALTER TABLE customers ADD CONSTRAINT customers_external_id_present CHECK (external_id IS NOT NULL) NOT VALID;
ALTER TABLE customers VALIDATE CONSTRAINT customers_external_id_present;
