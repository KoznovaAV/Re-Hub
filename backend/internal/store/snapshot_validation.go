package store

import (
	"context"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
)

type snapshotQuerier interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

// ValidateSnapshot uses the same domain rules as the transactional write.
func (s *Store) ValidateSnapshot(ctx context.Context, scope []string, date time.Time, rows []ParsedRow) ([]ParsedRow, []ParsedError, error) {
	return validateSnapshot(ctx, s.pool, scope, date, rows)
}
func validateSnapshot(ctx context.Context, q snapshotQuerier, scope []string, date time.Time, rows []ParsedRow) ([]ParsedRow, []ParsedError, error) {
	valid := []ParsedRow{}
	problems := []ParsedError{}
	counts := map[string]int{}
	allowed := map[string]bool{}
	for _, p := range scope {
		allowed[p] = true
	}
	for _, r := range rows {
		counts[r.ExternalID+"\x00"+r.PeriodCode]++
	}
	for _, r := range rows {
		code, message := "", ""
		var clientID, periodID string
		switch {
		case r.ExternalID == "" || r.PeriodCode == "":
			code, message = "MISSING_KEY", "Client and period are required"
		case counts[r.ExternalID+"\x00"+r.PeriodCode] > 1:
			code, message = "DUPLICATE_KEY", "All repeated client/period rows are rejected"
		case !allowed[r.PeriodCode]:
			code, message = "PERIOD_OUT_OF_SCOPE", "Period is outside the import scope"
		}
		if code == "" {
			err := q.QueryRow(ctx, "SELECT id::text FROM clients WHERE external_id=$1", r.ExternalID).Scan(&clientID)
			if err == pgx.ErrNoRows {
				code, message = "CLIENT_UNKNOWN", "Client must be imported first"
			} else if err != nil {
				return nil, nil, err
			}
		}
		if code == "" {
			err := q.QueryRow(ctx, "SELECT id::text FROM report_periods WHERE label=$1", r.PeriodCode).Scan(&periodID)
			if err == pgx.ErrNoRows {
				code, message = "PERIOD_UNKNOWN", "Period is not configured"
			} else if err != nil {
				return nil, nil, err
			}
		}
		if code == "" && r.TotalDocs == nil {
			var total int
			var source string
			err := q.QueryRow(ctx, `SELECT sr.total_docs,sr.id::text FROM slice_records sr JOIN slices s ON s.id=sr.slice_id WHERE sr.client_id=$1::uuid AND s.period_id=$2::uuid AND s.slice_date<$3::date AND sr.total_docs IS NOT NULL ORDER BY s.slice_date DESC,s.id DESC LIMIT 1`, clientID, periodID, date).Scan(&total, &source)
			if err == pgx.ErrNoRows {
				code, message = "TOTAL_MISSING_FIRST_OBSERVATION", "No earlier total for this client and period"
			} else if err != nil {
				return nil, nil, err
			} else {
				r.TotalDocs = &total
				r.TotalSourceID = source
			}
		}
		if code == "" && (r.NotSent < 0 || *r.TotalDocs < 0) {
			code, message = "INTEGER_OUT_OF_RANGE", "Document counts must be nonnegative"
		}
		if code == "" && r.NotSent > *r.TotalDocs {
			code, message = "UNSENT_GT_TOTAL", "Unsent documents exceed resolved total"
		}
		if code != "" {
			e := rowError(r, code, message)
			switch code {
			case "UNSENT_GT_TOTAL", "INTEGER_OUT_OF_RANGE":
				e.Column = "E"
				e.RawValue = strconv.Itoa(r.NotSent)
			case "TOTAL_MISSING_FIRST_OBSERVATION":
				e.Column = "D"
			case "MISSING_KEY", "DUPLICATE_KEY", "CLIENT_UNKNOWN":
				e.Column = "A"
				e.RawValue = r.ExternalID
			case "PERIOD_OUT_OF_SCOPE", "PERIOD_UNKNOWN":
				e.Column = "B"
				e.RawValue = r.PeriodCode
			}
			problems = append(problems, e)
		} else {
			valid = append(valid, r)
		}
	}
	return valid, problems, nil
}
