package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

type unusedQuerier struct{}

func (unusedQuerier) QueryRow(context.Context, string, ...any) pgx.Row {
	panic("QueryRow must not be called for DUPLICATE_KEY rows")
}

func TestValidateSnapshotDuplicateKey(t *testing.T) {
	total := 10
	rows := []ParsedRow{
		{ExternalID: "NEG00001", PeriodCode: "2026Q3", Row: 2, Sheet: "3 кв 2026", NotSent: 1, TotalDocs: &total},
		{ExternalID: "NEG00001", PeriodCode: "2026Q3", Row: 3, Sheet: "3 кв 2026", NotSent: 2, TotalDocs: &total},
	}
	valid, problems, err := validateSnapshot(context.Background(), unusedQuerier{}, []string{"2026Q3"}, time.Date(2026, 10, 20, 0, 0, 0, 0, time.UTC), rows)
	if err != nil {
		t.Fatal(err)
	}
	if len(valid) != 0 {
		t.Fatalf("valid rows = %d, want 0", len(valid))
	}
	if len(problems) != 2 {
		t.Fatalf("problems = %d, want 2", len(problems))
	}
	for _, p := range problems {
		if p.Code != "DUPLICATE_KEY" {
			t.Fatalf("code = %q, want DUPLICATE_KEY", p.Code)
		}
		if p.Column != "A" {
			t.Fatalf("column = %q, want A", p.Column)
		}
	}
}
