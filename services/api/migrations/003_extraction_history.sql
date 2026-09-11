ALTER TABLE extraction_imports DROP CONSTRAINT IF EXISTS extraction_imports_status_check;
ALTER TABLE extraction_imports ADD CONSTRAINT extraction_imports_status_check
    CHECK (status IN ('REVIEW_REQUIRED', 'APPROVED', 'SUPERSEDED', 'FAILED'));
CREATE INDEX IF NOT EXISTS extraction_imports_status_idx ON extraction_imports (status, extracted_at DESC);
