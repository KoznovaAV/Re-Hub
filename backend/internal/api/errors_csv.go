package api

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

var importErrorCSVHeader = []string{"Лист", "Строка", "Колонка", "ID", "Период", "Код", "Причина", "Значение"}

func (s *Server) importErrorsCSV(w http.ResponseWriter, r *http.Request) {
	if !isAdmin(r) {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "Only an administrator can download import errors")
		return
	}
	if !s.ready(w) {
		return
	}
	importID := r.PathValue("id")
	items, err := s.store.ImportErrors(r.Context(), importID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_IMPORT_ID", "Import id must be a UUID")
		return
	}
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="import-errors-%s.csv"`, importID))
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(errorsCSV(items)))
}

func errorsCSV(items []store.ParsedError) string {
	var builder strings.Builder
	builder.WriteString("\ufeff")
	writeCSVRow(&builder, importErrorCSVHeader)
	for _, item := range items {
		row := []string{item.Sheet, "", item.Column, item.ExternalID, item.PeriodCode, item.Code, item.Message, item.RawValue}
		if item.Row != nil {
			row[1] = fmt.Sprintf("%d", *item.Row)
		}
		writeCSVRow(&builder, row)
	}
	return builder.String()
}

func writeCSVRow(builder *strings.Builder, row []string) {
	for index, value := range row {
		if index > 0 {
			builder.WriteByte(';')
		}
		builder.WriteString(csvCell(value))
	}
	builder.WriteString("\r\n")
}

func csvCell(value string) string {
	text := value
	if text != "" && strings.ContainsRune("=+-@", rune(text[0])) {
		text = "'" + text
	}
	return `"` + strings.ReplaceAll(text, `"`, `""`) + `"`
}
