package api

import (
	"strings"
	"testing"

	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

func TestErrorsCSVIncludesAllColumnsAndEscapesFormulas(t *testing.T) {
	row := 7
	csv := errorsCSV([]store.ParsedError{{
		Scope: "row", Row: &row, Column: "A", Sheet: "2026Q1",
		ExternalID: "AAA00001", PeriodCode: "2026Q1",
		Code: "INVALID_EXTERNAL_ID", Message: "bad id", RawValue: "=1+1",
	}})
	if !strings.HasPrefix(csv, "\ufeff") {
		t.Fatal("CSV must start with UTF-8 BOM")
	}
	if !strings.Contains(csv, "ID") || !strings.Contains(csv, "2026Q1") {
		t.Fatalf("CSV missing expected fields: %q", csv)
	}
	if !strings.Contains(csv, "\"'=1+1\"") {
		t.Fatalf("formula must be neutralized: %q", csv)
	}
	if !strings.Contains(csv, "AAA00001") || !strings.Contains(csv, "2026Q1") {
		t.Fatalf("row fields missing: %q", csv)
	}
}
