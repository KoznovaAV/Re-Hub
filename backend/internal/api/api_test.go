package api

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/KoznovaAV/Re-Hub/backend/internal/parser"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

func TestParseLimitAndShare(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/?limit=5000&offset=-2", nil)
	limit, offset := parseLimit(request)
	if limit != 200 || offset != 0 {
		t.Fatalf("limit/offset = %d/%d", limit, offset)
	}
	if got := parseShare("42.5"); got == nil || *got != 42.5 {
		t.Fatalf("parseShare(42.5) = %v", got)
	}
	if parseShare("101") != nil || parseShare("bad") != nil {
		t.Fatal("invalid share must be rejected")
	}
}

func TestSnapshotContextDefaults(t *testing.T) {
	form := url.Values{}
	form.Set("snapshot_date", "2026-10-20")
	request := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(form.Encode()))
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	context, date, err := snapshotContext(request)
	if err != nil {
		t.Fatal(err)
	}
	if date.Format("2006-01-02") != "2026-10-20" {
		t.Fatalf("date = %s", date)
	}
	scope, ok := context["period_scope"].([]string)
	if !ok || len(scope) != 4 {
		t.Fatalf("scope = %#v", context["period_scope"])
	}
	if context["file_kind"] != "snapshot" || context["mapping_profile"] != "customer_october_tabs_v1" {
		t.Fatalf("context = %#v", context)
	}
}

func TestClientsContextHasNoSnapshotFields(t *testing.T) {
	context, err := clientsContext(`{"key_mode":"kcr"}`)
	if err != nil {
		t.Fatal(err)
	}
	if context["file_kind"] != "clients" || context["mapping_profile"] != "customer_kcr_directory_v1" {
		t.Fatalf("context = %#v", context)
	}
}

func TestHealthWithoutDatabase(t *testing.T) {
	mux := http.NewServeMux()
	New(nil, nil, "http://parser").Register(mux)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/health", nil))
	if response.Code != http.StatusOK {
		t.Fatalf("health status = %d", response.Code)
	}
	if !strings.Contains(response.Body.String(), `"db":"disabled"`) {
		t.Fatalf("health body = %s", response.Body.String())
	}
}

func TestDataEndpointsRejectMissingDatabase(t *testing.T) {
	mux := http.NewServeMux()
	New(nil, nil, "http://parser").Register(mux)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/v1/clients", nil))
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d", response.Code)
	}
}

func TestConvertParserErrors(t *testing.T) {
	column := "A"
	externalID := "AAA00001"
	period := "2026Q1"
	item := parser.Error{
		Scope: "row", Code: "INVALID_EXTERNAL_ID", Message: "bad id", RawValue: "bad",
		Source: &parser.Source{Sheet: "1 кв 2026", Row: 7, Column: &column},
	}
	item.KeyHint.ExternalID = &externalID
	item.KeyHint.PeriodCode = &period

	items := convertParserErrors([]parser.Error{item})
	if len(items) != 1 {
		t.Fatalf("items = %#v", items)
	}
	if items[0].Row == nil || *items[0].Row != 7 || items[0].Column != "A" {
		t.Fatalf("row/column = %#v", items[0])
	}
	if items[0].ExternalID != externalID || items[0].PeriodCode != period || items[0].RawValue != "bad" {
		t.Fatalf("mapped error = %#v", items[0])
	}
	if !CompleteForCSV(items[0]) {
		t.Fatalf("error incomplete for CSV: %#v", items[0])
	}
	csv := ErrorsCSV(items)
	if !strings.Contains(csv, `"Лист";"Строка";"Колонка";"ID";"Период";"Код";"Причина";"Значение"`) {
		t.Fatalf("csv header missing: %q", csv)
	}
	if !strings.Contains(csv, `"1 кв 2026";"7";"A";"AAA00001";"2026Q1";"INVALID_EXTERNAL_ID";"bad id";"bad"`) {
		t.Fatalf("csv row missing fields: %q", csv)
	}
}

func TestConvertParserErrorsFillsBlankReason(t *testing.T) {
	column := "E"
	item := parser.Error{
		Scope: "row", Code: "INTEGER_REQUIRED", Message: "   ", RawValue: nil,
		Source: &parser.Source{Sheet: "весь 2025 год", Row: 4, Column: &column},
	}
	items := convertParserErrors([]parser.Error{item})
	if items[0].Message != "INTEGER_REQUIRED" {
		t.Fatalf("message = %q", items[0].Message)
	}
	if !CompleteForCSV(items[0]) {
		t.Fatalf("incomplete: %#v", items[0])
	}
}

func TestCSVEscapeNeutralizesFormulas(t *testing.T) {
	got := csvEscape("=1+1")
	if got != `"'=1+1"` {
		t.Fatalf("formula escape = %q", got)
	}
	got = csvEscape("+cmd")
	if got != `"'+cmd"` {
		t.Fatalf("plus escape = %q", got)
	}
	got = csvEscape("обычный")
	if got != `"обычный"` {
		t.Fatalf("plain escape = %q", got)
	}
}

func TestErrorsCSVSkipsIncompleteRows(t *testing.T) {
	row := 3
	csv := ErrorsCSV([]store.ParsedError{
		{Scope: "row", Code: "BAD", Message: "reason", Row: &row, Column: "A", RawValue: "=CMD"},
		{Scope: "row", Code: "BAD", Message: "missing row"},
	})
	if !strings.Contains(csv, `"'=CMD"`) {
		t.Fatalf("expected neutralized raw value, got %q", csv)
	}
	if strings.Count(csv, "\r\n") != 1 {
		t.Fatalf("expected header + one data row, got %q", csv)
	}
}

func TestDownloadImportErrorsRequiresAdminAndDB(t *testing.T) {
	mux := http.NewServeMux()
	New(nil, nil, "http://parser").Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/imports/00000000-0000-0000-0000-000000000099/errors.csv", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("without db status = %d", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/imports/00000000-0000-0000-0000-000000000099/errors.csv", nil)
	req.Header.Set("X-Role", "admin")
	rec = httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("admin without db status = %d", rec.Code)
	}
}
