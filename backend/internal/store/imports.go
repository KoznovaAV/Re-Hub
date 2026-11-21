package store

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

func (s *Store) SaveSnapshot(ctx context.Context, fileName string, scope []string, snapshotDate time.Time, userID string, totalRows int, rows []ParsedRow, parserErrors []ParsedError) (*ImportResult, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	importID, err := createImportJob(ctx, tx, "snapshot", fileName, scope, userID)
	if err != nil {
		return nil, err
	}

	periodIDs, err := periodIDs(ctx, tx)
	if err != nil {
		return nil, err
	}
	clientIDs, err := clientIDs(ctx, tx)
	if err != nil {
		return nil, err
	}

	counts := make(map[string]int)
	sliceIDs := make(map[string]string)
	rowsOK := 0
	importErrors := append([]ParsedError{}, parserErrors...)

	for _, row := range rows {
		counts[row.ExternalID+"\x00"+row.PeriodCode]++
	}
	for _, row := range rows {
		key := row.ExternalID + "\x00" + row.PeriodCode
		if row.ExternalID == "" || row.PeriodCode == "" {
			importErrors = append(importErrors, rowError(row, "MISSING_KEY", "external_id and period_code are required"))
			continue
		}
		if counts[key] > 1 {
			importErrors = append(importErrors, rowError(row, "DUPLICATE_KEY", fmt.Sprintf("duplicate external_id + period_code: %s/%s", row.ExternalID, row.PeriodCode)))
			continue
		}

		clientID, ok := clientIDs[row.ExternalID]
		if !ok {
			importErrors = append(importErrors, rowError(row, "CLIENT_UNKNOWN", fmt.Sprintf("client %s is not loaded", row.ExternalID)))
			continue
		}
		periodID, ok := periodIDs[row.PeriodCode]
		if !ok {
			importErrors = append(importErrors, rowError(row, "PERIOD_UNKNOWN", fmt.Sprintf("period %s is not configured", row.PeriodCode)))
			continue
		}

		sliceID := sliceIDs[row.PeriodCode]
		if sliceID == "" {
			date := snapshotDate
			if date.IsZero() {
				date = time.Now()
			}
			if err := tx.QueryRow(ctx, `
				INSERT INTO slices (period_id, slice_date, uploaded_by, file_name, source_profile)
				VALUES ($1::uuid, $2::date, NULLIF($3, '')::uuid, $4, 'customer_october_tabs_v1')
				ON CONFLICT (period_id, slice_date) DO UPDATE
				SET uploaded_by = COALESCE(EXCLUDED.uploaded_by, slices.uploaded_by),
					file_name = COALESCE(EXCLUDED.file_name, slices.file_name),
					source_profile = COALESCE(EXCLUDED.source_profile, slices.source_profile)
				RETURNING id::text`, periodID, date, userID, fileName).Scan(&sliceID); err != nil {
				return nil, fmt.Errorf("create slice %s: %w", row.PeriodCode, err)
			}
			sliceIDs[row.PeriodCode] = sliceID
		}

		if _, err := tx.Exec(ctx, `
			INSERT INTO slice_records (slice_id, client_id, total_docs, not_sent_docs, source_sheet, source_row, raw_external_id)
			VALUES ($1::uuid, $2::uuid, $3, $4, NULLIF($5, ''), NULLIF($6, 0), $7)
			ON CONFLICT (slice_id, client_id) DO UPDATE
			SET total_docs = EXCLUDED.total_docs,
				not_sent_docs = EXCLUDED.not_sent_docs,
				source_sheet = EXCLUDED.source_sheet,
				source_row = EXCLUDED.source_row,
				raw_external_id = EXCLUDED.raw_external_id`,
			sliceID, clientID, row.TotalDocs, row.NotSent, row.Sheet, row.Row, row.ExternalID); err != nil {
			return nil, fmt.Errorf("upsert slice record %s/%s: %w", row.ExternalID, row.PeriodCode, err)
		}
		rowsOK++
	}

	if err := insertErrors(ctx, tx, importID, importErrors); err != nil {
		return nil, err
	}
	status := "completed"
	if len(importErrors) > 0 {
		status = "partial"
	}
	if _, err := tx.Exec(ctx, `
		UPDATE import_jobs
		SET status = $1, rows_total = $2, rows_ok = $3, rows_errors = $4
		WHERE id = $5::uuid`, status, totalRows, rowsOK, len(importErrors), importID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &ImportResult{
		ImportID: importID, Kind: "snapshot", RowsTotal: totalRows, RowsOK: rowsOK,
		RowsErrors: len(importErrors), PeriodScope: scope, Status: status, Errors: importErrors,
	}, nil
}

func (s *Store) SaveClients(ctx context.Context, fileName, userID, sourceKeyMode string, totalRows int, rows []NewClientData, parserErrors []ParsedError) (*ImportResult, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	importID, err := createImportJob(ctx, tx, "clients", fileName, nil, userID)
	if err != nil {
		return nil, err
	}
	if sourceKeyMode == "" {
		sourceKeyMode = "anonymous"
	}

	counts := make(map[string]int)
	created, updated, rowsOK := 0, 0, 0
	importErrors := append([]ParsedError{}, parserErrors...)

	for _, row := range rows {
		counts[row.ExternalID]++
	}
	for _, row := range rows {
		if row.ExternalID == "" {
			importErrors = append(importErrors, ParsedError{Scope: "row", Code: "MISSING_KEY", Message: "external_id is required"})
			continue
		}
		if counts[row.ExternalID] > 1 {
			importErrors = append(importErrors, ParsedError{Scope: "row", Code: "DUPLICATE_KEY", Message: "duplicate external_id: " + row.ExternalID})
			continue
		}

		active := true
		if row.Active != nil {
			active = *row.Active
		}
		inactive := !active
		name := row.Name
		if name == "" {
			name = "Клиент " + row.ExternalID
		}

		var clientID string
		var inserted bool
		if err := tx.QueryRow(ctx, `
			INSERT INTO clients (external_id, name, excluded, inactive, stage, source_key_mode, contact_details, updated_at)
			VALUES ($1, $2, $3, $4, 'Не в работе', $5, $6, NOW())
			ON CONFLICT (external_id) DO UPDATE
			SET name = CASE WHEN $7 THEN EXCLUDED.name ELSE clients.name END,
				contact_details = COALESCE(EXCLUDED.contact_details, clients.contact_details),
				excluded = EXCLUDED.excluded,
				inactive = EXCLUDED.inactive,
				updated_at = NOW()
			RETURNING id::text, (xmax = 0) AS inserted`,
			row.ExternalID, name, row.Excluded, inactive, sourceKeyMode, row.ContactDetails, row.Name != "").Scan(&clientID, &inserted); err != nil {
			return nil, fmt.Errorf("upsert client %s: %w", row.ExternalID, err)
		}
		if inserted {
			created++
		} else {
			updated++
		}
		if _, err := tx.Exec(ctx, "DELETE FROM client_tags WHERE client_id = $1::uuid", clientID); err != nil {
			return nil, err
		}
		for _, tag := range row.Tags {
			if _, err := tx.Exec(ctx, "INSERT INTO client_tags (client_id, tag) VALUES ($1::uuid, $2) ON CONFLICT DO NOTHING", clientID, tag); err != nil {
				return nil, err
			}
		}
		rowsOK++
	}

	if err := insertErrors(ctx, tx, importID, importErrors); err != nil {
		return nil, err
	}
	status := "completed"
	if len(importErrors) > 0 {
		status = "partial"
	}
	if _, err := tx.Exec(ctx, `
		UPDATE import_jobs
		SET status = $1, rows_total = $2, rows_ok = $3, rows_errors = $4
		WHERE id = $5::uuid`, status, totalRows, rowsOK, len(importErrors), importID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &ImportResult{
		ImportID: importID, Kind: "clients", RowsTotal: totalRows, RowsOK: rowsOK,
		RowsErrors: len(importErrors), Created: created, Updated: updated, Status: status, Errors: importErrors,
	}, nil
}

func createImportJob(ctx context.Context, tx pgx.Tx, kind, fileName string, scope []string, userID string) (string, error) {
	var id string
	if scope == nil {
		scope = []string{}
	}
	if err := tx.QueryRow(ctx, `
		INSERT INTO import_jobs (kind, file_name, period_scope, status, created_by)
		VALUES ($1, $2, $3, 'completed', NULLIF($4, '')::uuid)
		RETURNING id::text`, kind, fileName, scope, userID).Scan(&id); err != nil {
		return "", err
	}
	return id, nil
}

func periodIDs(ctx context.Context, tx pgx.Tx) (map[string]string, error) {
	rows, err := tx.Query(ctx, "SELECT label, id::text FROM report_periods")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := make(map[string]string)
	for rows.Next() {
		var code, id string
		if err := rows.Scan(&code, &id); err != nil {
			return nil, err
		}
		result[code] = id
	}
	return result, rows.Err()
}

func clientIDs(ctx context.Context, tx pgx.Tx) (map[string]string, error) {
	rows, err := tx.Query(ctx, "SELECT external_id, id::text FROM clients")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := make(map[string]string)
	for rows.Next() {
		var externalID, id string
		if err := rows.Scan(&externalID, &id); err != nil {
			return nil, err
		}
		result[externalID] = id
	}
	return result, rows.Err()
}

func insertErrors(ctx context.Context, tx pgx.Tx, importID string, errorsList []ParsedError) error {
	for _, item := range errorsList {
		var rowNumber any
		if item.Row != nil {
			rowNumber = *item.Row
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO import_errors (import_id, scope, row_number, column_name, code, message, raw_value, external_id, period_code)
			VALUES ($1::uuid, $2, $3, NULLIF($4, ''), $5, $6, NULLIF($7, ''), NULLIF($8, ''), NULLIF($9, ''))`,
			importID, item.Scope, rowNumber, item.Column, item.Code, item.Message, item.RawValue, item.ExternalID, item.PeriodCode); err != nil {
			return err
		}
	}
	return nil
}

func rowError(row ParsedRow, code, message string) ParsedError {
	rowNumber := row.Row
	return ParsedError{
		Scope: "row", Row: &rowNumber, Code: code, Message: message,
		ExternalID: row.ExternalID, PeriodCode: row.PeriodCode,
	}
}
