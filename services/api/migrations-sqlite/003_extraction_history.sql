CREATE INDEX IF NOT EXISTS extraction_imports_status_idx ON extraction_imports (status, extracted_at DESC);
