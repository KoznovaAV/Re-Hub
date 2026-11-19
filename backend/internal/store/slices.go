package store

import (
	"context"
	"time"
)

type SliceSummary struct {
	ID         string    `json:"id"`
	PeriodCode string    `json:"period_code"`
	SliceDate  time.Time `json:"slice_date"`
	FileName   string    `json:"file_name,omitempty"`
	Rows       int       `json:"rows"`
	Clients    int       `json:"clients"`
	UnsentDocs int       `json:"unsent_docs"`
	UploadedAt time.Time `json:"uploaded_at"`
}

func (s *Store) ListSlices(ctx context.Context, limit, offset int) ([]SliceSummary, int, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	var total int
	if err := s.pool.QueryRow(ctx, "SELECT COUNT(*) FROM slices").Scan(&total); err != nil {
		return nil, 0, err
	}
	rows, err := s.pool.Query(ctx, `
		SELECT s.id::text, rp.label, s.slice_date, COALESCE(s.file_name, ''),
			COUNT(sr.id)::int, COUNT(DISTINCT sr.client_id)::int,
			COALESCE(SUM(sr.not_sent_docs), 0)::int, s.uploaded_at
		FROM slices s
		JOIN report_periods rp ON rp.id = s.period_id
		LEFT JOIN slice_records sr ON sr.slice_id = s.id
		GROUP BY s.id, rp.label, s.slice_date, s.file_name, s.uploaded_at
		ORDER BY s.slice_date DESC, s.id DESC
		LIMIT $1 OFFSET $2`, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	result := make([]SliceSummary, 0)
	for rows.Next() {
		var item SliceSummary
		if err := rows.Scan(&item.ID, &item.PeriodCode, &item.SliceDate, &item.FileName,
			&item.Rows, &item.Clients, &item.UnsentDocs, &item.UploadedAt); err != nil {
			return nil, 0, err
		}
		result = append(result, item)
	}
	return result, total, rows.Err()
}
