package api

import (
	"fmt"
	"strings"

	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

// CSV columns consumed by the import UI ("Скачать проблемные строки").
// "Причина" is parser/domain message; "Значение" is raw_value.
var errorCSVHeader = []string{"Лист", "Строка", "Колонка", "ID", "Период", "Код", "Причина", "Значение"}

// ErrorsCSV renders ParsedError rows for the import error download.
// Go must keep sheet/row/column/code/message/raw_value/key fields so the UI can emit a complete CSV.
func ErrorsCSV(items []store.ParsedError) string {
	rows := make([][]string, 0, len(items)+1)
	rows = append(rows, errorCSVHeader)
	for _, item := range items {
		rowText := ""
		if item.Row != nil {
			rowText = fmt.Sprintf("%d", *item.Row)
		}
		rows = append(rows, []string{
			item.Sheet,
			rowText,
			item.Column,
			item.ExternalID,
			item.PeriodCode,
			item.Code,
			item.Message,
			item.RawValue,
		})
	}
	var builder strings.Builder
	builder.WriteString("\ufeff")
	for i, row := range rows {
		if i > 0 {
			builder.WriteString("\r\n")
		}
		for j, cell := range row {
			if j > 0 {
				builder.WriteByte(';')
			}
			builder.WriteString(csvEscape(cell))
		}
	}
	return builder.String()
}

func csvEscape(value string) string {
	if strings.ContainsAny(value, ";\"\r\n") || strings.HasPrefix(value, "=") || strings.HasPrefix(value, "+") || strings.HasPrefix(value, "-") || strings.HasPrefix(value, "@") {
		return `"` + strings.ReplaceAll(value, `"`, `""`) + `"`
	}
	return value
}

// CompleteForCSV reports whether an error carries the fields required for a useful CSV row.
// File-scope items may omit row/column. Row-scope items need a row number; column/raw_value may be empty.
func CompleteForCSV(item store.ParsedError) bool {
	if item.Code == "" || item.Message == "" {
		return false
	}
	if item.Scope == "row" && item.Row == nil {
		return false
	}
	return true
}
