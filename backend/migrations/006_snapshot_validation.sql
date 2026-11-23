-- Preserve the origin of a resolved total. Existing rows keep their legacy representation.
ALTER TABLE slice_records ADD COLUMN total_source_record_id UUID REFERENCES slice_records(id) ON DELETE SET NULL;
ALTER TABLE slice_records ADD CONSTRAINT valid_document_counts CHECK (not_sent_docs >= 0 AND (total_docs IS NULL OR (total_docs >= 0 AND not_sent_docs <= total_docs))) NOT VALID;
ALTER TABLE import_errors ADD COLUMN source_sheet TEXT;
