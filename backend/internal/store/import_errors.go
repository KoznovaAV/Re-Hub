package store

import (
	"context"

	"github.com/jackc/pgx/v5/pgtype"
)

func (s *Store) ImportErrors(ctx context.Context, importID string) ([]ParsedError, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT scope, row_number, COALESCE(column_name, ''), code, message,
			COALESCE(raw_value, ''), COALESCE(source_sheet, ''), COALESCE(external_id, ''), COALESCE(period_code, '')
		FROM import_errors
		WHERE import_id = $1::uuid
		ORDER BY row_number NULLS FIRST, id`, importID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := []ParsedError{}
	for rows.Next() {
		var item ParsedError
		var row pgtype.Int4
		if err := rows.Scan(&item.Scope, &row, &item.Column, &item.Code, &item.Message,
			&item.RawValue, &item.Sheet, &item.ExternalID, &item.PeriodCode); err != nil {
			return nil, err
		}
		if row.Valid {
			value := int(row.Int32)
			item.Row = &value
		}
		result = append(result, item)
	}
	return result, rows.Err()
}
