package store

import (
	"context"
	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"os"
	"testing"
	"time"
)

func TestSnapshotDomainRulesAndPartialPersistence(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TEST_DATABASE_URL required")
	}
	ctx := context.Background()
	p, e := db.Open(ctx, url)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	if _, e = db.Migrate(ctx, p); e != nil {
		t.Fatal(e)
	}
	codes := []string{"PDOMAIN-A", "PDOMAIN-B", "PDOMAIN-C", "PDOMAIN-D"}
	defer func() {
		p.Exec(ctx, "DELETE FROM slices WHERE file_name='p-domain-test'")
		p.Exec(ctx, "DELETE FROM clients WHERE external_id=ANY($1::text[])", codes)
	}()
	for _, c := range codes {
		if _, e = p.Exec(ctx, "INSERT INTO clients(external_id,name) VALUES($1,$1) ON CONFLICT DO NOTHING", c); e != nil {
			t.Fatal(e)
		}
	}
	s := New(p)
	day := func(d string) time.Time { v, _ := time.Parse("2006-01-02", d); return v }
	total := 100
	row := func(c string, n int, tot *int) ParsedRow {
		return ParsedRow{ExternalID: c, PeriodCode: "2026Q3", NotSent: n, TotalDocs: tot, Sheet: "3 кв 2026", Row: 3}
	}
	save := func(d string, rows []ParsedRow) *ImportResult {
		t.Helper()
		v, e := s.SaveSnapshot(ctx, "p-domain-test", []string{"2026Q3"}, day(d), "", len(rows), rows, nil)
		if e != nil {
			t.Fatal(e)
		}
		return v
	}
	if got := save("2026-01-01", []ParsedRow{row(codes[0], 40, &total)}); got.RowsOK != 1 {
		t.Fatal(got)
	}
	rows := []ParsedRow{row(codes[0], 30, nil), row(codes[1], 101, &total), row(codes[2], 10, nil), row(codes[3], 20, &total), row(codes[3], 30, &total), row("PDOMAIN-UNKNOWN", 1, &total)}
	valid, problems, e := s.ValidateSnapshot(ctx, []string{"2026Q3"}, day("2026-01-02"), rows)
	if e != nil || len(valid) != 1 || len(problems) != 5 {
		t.Fatalf("preview %v %v %v", valid, problems, e)
	}
	if valid[0].TotalSourceID == "" || valid[0].TotalDocs == nil || *valid[0].TotalDocs != 100 {
		t.Fatal("inheritance lost")
	}
	got := save("2026-01-02", rows)
	if got.RowsOK != 1 || got.RowsErrors != 5 {
		t.Fatal(got)
	}
	found := map[string]bool{}
	for _, v := range got.Errors {
		found[v.Code] = true
		if v.Row == nil {
			t.Fatal("row lost")
		}
	}
	for _, c := range []string{"UNSENT_GT_TOTAL", "TOTAL_MISSING_FIRST_OBSERVATION", "DUPLICATE_KEY", "CLIENT_UNKNOWN"} {
		if !found[c] {
			t.Fatal(c)
		}
	}
	if got := save("2026-01-03", []ParsedRow{row(codes[0], 20, nil)}); got.RowsOK != 1 {
		t.Fatal(got)
	}
	var stored int
	var origin *string
	e = p.QueryRow(ctx, `SELECT sr.total_docs,sr.total_source_record_id::text FROM slice_records sr JOIN slices s ON s.id=sr.slice_id JOIN clients c ON c.id=sr.client_id WHERE c.external_id=$1 AND s.slice_date='2026-01-03'`, codes[0]).Scan(&stored, &origin)
	if e != nil || stored != 100 || origin == nil {
		t.Fatalf("stored=%d origin=%v err=%v", stored, origin, e)
	}
	for _, v := range []struct{ date, period, code string }{{"2025-12-31", "2026Q3", "TOTAL_MISSING_FIRST_OBSERVATION"}, {"2026-01-04", "2026Q2", "TOTAL_MISSING_FIRST_OBSERVATION"}, {"2026-01-04", "UNKNOWN", "PERIOD_UNKNOWN"}} {
		r := row(codes[0], 1, nil)
		r.PeriodCode = v.period
		_, errors, e := s.ValidateSnapshot(ctx, []string{v.period}, day(v.date), []ParsedRow{r})
		if e != nil || len(errors) != 1 || errors[0].Code != v.code {
			t.Fatalf("%+v: %v %v", v, errors, e)
		}
	}
}
