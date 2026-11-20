package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/KoznovaAV/Re-Hub/backend/internal/parser"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

const maxUploadBytes = 25 << 20

func (s *Server) importClients(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	if !isAdmin(r) {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "Only an administrator can import clients")
		return
	}
	path, name, cleanup, err := receiveUpload(w, r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "UPLOAD_ERROR", err.Error())
		return
	}
	defer cleanup()

	context, err := clientsContext(r.FormValue("context"))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_CONTEXT", err.Error())
		return
	}
	if s.parser == nil {
		writeError(w, http.StatusServiceUnavailable, "PARSER_UNAVAILABLE", "Parser service is not configured")
		return
	}
	result, err := s.parser.Parse(r.Context(), path, context)
	if err != nil {
		log.Printf("parse clients: %v", err)
		writeError(w, http.StatusBadGateway, "PARSER_ERROR", "Parser service failed")
		return
	}
	if fileError := firstFileError(result); fileError != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_FILE", fileError.Message)
		return
	}

	rows := make([]store.NewClientData, 0, len(result.Rows))
	for _, row := range result.Rows {
		var data parser.ClientData
		if err := json.Unmarshal(row.Data, &data); err != nil {
			continue
		}
		rows = append(rows, store.NewClientData{
			ExternalID:     data.ExternalID,
			Name:           data.Name,
			ContactDetails: data.ContactDetails,
			Tags:           data.Tags,
			Excluded:       data.Excluded != nil && *data.Excluded,
			Active:         data.Active,
			SourceRow:      row.Source.Row,
		})
	}
	errorsList := convertParserErrors(result.Errors)
	keyMode, _ := context["key_mode"].(string)
	importResult, err := s.store.SaveClients(r.Context(), name, actorID(r), keyMode, result.NonemptyRowCount, rows, errorsList)
	if err != nil {
		log.Printf("save clients: %v", err)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "Could not save clients")
		return
	}
	writeImportResult(w, importResult)
}

func (s *Server) importSnapshot(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	if !isAdmin(r) {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "Only an administrator can import snapshots")
		return
	}
	path, name, cleanup, err := receiveUpload(w, r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "UPLOAD_ERROR", err.Error())
		return
	}
	defer cleanup()

	context, snapshotDate, err := snapshotContext(r)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_CONTEXT", err.Error())
		return
	}
	if s.parser == nil {
		writeError(w, http.StatusServiceUnavailable, "PARSER_UNAVAILABLE", "Parser service is not configured")
		return
	}
	result, err := s.parser.Parse(r.Context(), path, context)
	if err != nil {
		log.Printf("parse snapshot: %v", err)
		writeError(w, http.StatusBadGateway, "PARSER_ERROR", "Parser service failed")
		return
	}
	if fileError := firstFileError(result); fileError != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_FILE", fileError.Message)
		return
	}

	rows := make([]store.ParsedRow, 0, len(result.Rows))
	for _, row := range result.Rows {
		var data parser.SnapshotData
		if err := json.Unmarshal(row.Data, &data); err != nil {
			continue
		}
		rows = append(rows, store.ParsedRow{
			ExternalID: data.ExternalID,
			PeriodCode: data.PeriodCode,
			TotalDocs:  data.TotalDocs,
			NotSent:    data.UnsentDocs,
			Sheet:      row.Source.Sheet,
			Row:        row.Source.Row,
		})
	}
	scope := stringSlice(context["period_scope"])
	importResult, err := s.store.SaveSnapshot(r.Context(), name, scope, snapshotDate, actorID(r), result.NonemptyRowCount, rows, convertParserErrors(result.Errors))
	if err != nil {
		log.Printf("save snapshot: %v", err)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "Could not save snapshot")
		return
	}
	writeImportResult(w, importResult)
}

func receiveUpload(w http.ResponseWriter, r *http.Request) (string, string, func(), error) {
	r.Body = http.MaxBytesReader(w, r.Body, maxUploadBytes+(1<<20))
	if err := r.ParseMultipartForm(maxUploadBytes); err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			return "", "", func() {}, fmt.Errorf("file is too large")
		}
		return "", "", func() {}, fmt.Errorf("expected multipart form with file")
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		return "", "", func() {}, fmt.Errorf("file field is required")
	}
	defer file.Close()
	name := filepath.Base(header.Filename)
	if strings.ToLower(filepath.Ext(name)) != ".xlsx" {
		return "", "", func() {}, fmt.Errorf("only .xlsx files are supported")
	}
	if header.Size > maxUploadBytes {
		return "", "", func() {}, fmt.Errorf("file is too large")
	}
	temp, err := os.CreateTemp("", "rehub-*.xlsx")
	if err != nil {
		return "", "", func() {}, fmt.Errorf("could not create temporary file")
	}
	cleanup := func() {
		_ = temp.Close()
		_ = os.Remove(temp.Name())
	}
	if _, err := io.Copy(temp, io.LimitReader(file, maxUploadBytes)); err != nil {
		cleanup()
		return "", "", func() {}, fmt.Errorf("could not save uploaded file")
	}
	if err := temp.Close(); err != nil {
		cleanup()
		return "", "", func() {}, fmt.Errorf("could not save uploaded file")
	}
	return temp.Name(), name, cleanup, nil
}

func clientsContext(raw string) (map[string]any, error) {
	context := map[string]any{}
	if strings.TrimSpace(raw) != "" {
		if err := json.Unmarshal([]byte(raw), &context); err != nil {
			return nil, fmt.Errorf("context must be valid JSON")
		}
	}
	if context["contract_version"] == nil {
		context["contract_version"] = "1.0"
	}
	context["file_kind"] = "clients"
	if context["key_mode"] == nil {
		context["key_mode"] = "anonymous"
	}
	if context["mapping_profile"] == nil {
		context["mapping_profile"] = "customer_kcr_directory_v1"
	}
	return context, nil
}

func snapshotContext(r *http.Request) (map[string]any, time.Time, error) {
	context := map[string]any{}
	if raw := r.FormValue("context"); strings.TrimSpace(raw) != "" {
		if err := json.Unmarshal([]byte(raw), &context); err != nil {
			return nil, time.Time{}, fmt.Errorf("context must be valid JSON")
		}
	}
	if context["contract_version"] == nil {
		context["contract_version"] = "1.0"
	}
	context["file_kind"] = "snapshot"
	if context["key_mode"] == nil {
		context["key_mode"] = "anonymous"
	}
	if context["mapping_profile"] == nil {
		context["mapping_profile"] = "customer_october_tabs_v1"
	}
	if context["coverage"] == nil {
		context["coverage"] = "unknown"
	}

	dateText := r.FormValue("snapshot_date")
	if dateText == "" {
		dateText = r.FormValue("slice_date")
	}
	if dateText == "" {
		if value, ok := context["snapshot_date"].(string); ok {
			dateText = value
		}
	}
	if dateText == "" {
		dateText = time.Now().Format("2006-01-02")
	}
	date, err := time.Parse("2006-01-02", dateText)
	if err != nil {
		return nil, time.Time{}, fmt.Errorf("snapshot_date must be YYYY-MM-DD")
	}
	context["snapshot_date"] = dateText

	scope := stringSlice(context["period_scope"])
	if len(scope) == 0 {
		for _, value := range strings.Split(r.FormValue("period_scope"), ",") {
			if value = strings.TrimSpace(value); value != "" {
				scope = append(scope, value)
			}
		}
	}
	if len(scope) == 0 {
		scope = []string{"Y2025", "2026Q1", "2026Q2", "2026Q3"}
	}
	context["period_scope"] = scope
	return context, date, nil
}

func firstFileError(result *parser.Result) *parser.Error {
	for i := range result.Errors {
		if result.Errors[i].Scope == "file" {
			return &result.Errors[i]
		}
	}
	return nil
}

func convertParserErrors(items []parser.Error) []store.ParsedError {
	result := make([]store.ParsedError, 0, len(items))
	for _, item := range items {
		parsed := store.ParsedError{Scope: item.Scope, Code: item.Code, Message: item.Message}
		if item.Source != nil {
			row := item.Source.Row
			parsed.Row = &row
			if item.Source.Column != nil {
				parsed.Column = *item.Source.Column
			}
		}
		if item.RawValue != nil {
			parsed.RawValue = fmt.Sprint(item.RawValue)
		}
		if item.KeyHint.ExternalID != nil {
			parsed.ExternalID = *item.KeyHint.ExternalID
		}
		if item.KeyHint.PeriodCode != nil {
			parsed.PeriodCode = *item.KeyHint.PeriodCode
		}
		result = append(result, parsed)
	}
	return result
}

func stringSlice(value any) []string {
	items, ok := value.([]any)
	if !ok {
		if values, ok := value.([]string); ok {
			return values
		}
		return nil
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func writeImportResult(w http.ResponseWriter, result *store.ImportResult) {
	writeJSON(w, http.StatusCreated, map[string]any{
		"data": map[string]any{
			"import_id": result.ImportID,
			"kind":      result.Kind,
			"status":    result.Status,
			"counters": map[string]int{
				"rows_total": result.RowsTotal, "rows_ok": result.RowsOK, "rows_errors": result.RowsErrors,
				"created": result.Created, "updated": result.Updated,
			},
			"period_scope": result.PeriodScope,
			"errors":       result.Errors,
		},
	})
}
