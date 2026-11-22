package store

import (
	"testing"
	"time"
)

func TestEventValidation(t *testing.T) {
	date := time.Date(2026, 11, 22, 0, 0, 0, 0, time.UTC)
	future := date.AddDate(0, 0, 1)
	past := date.AddDate(0, 0, -1)
	valid := EventInput{Type: "call", Result: "Перенос", Date: date, PeriodCode: "2026Q3", CallbackOn: &future}
	if err := ValidateEvent(valid); err != nil {
		t.Fatal(err)
	}
	cases := []EventInput{
		{Type: "call", Result: "Перенос", Date: date, PeriodCode: "2026Q3"},
		{Type: "call", Result: "Перенос", Date: date, PeriodCode: "2026Q3", CallbackOn: &past},
		{Type: "comment", Result: "Отказ"},
		{Type: "comment", CallbackOn: &future},
		{Type: "call", Result: "Отказ", PeriodCode: "2026Q3", Stage: "Закрыт"},
		{Type: "call", Result: "Отказ", PeriodCode: "2026Q3", PromisedAt: &future},
		{Type: "call", Result: "Неизвестно", PeriodCode: "2026Q3"},
		{Type: "call", Result: "Недозвон"},
	}
	for _, c := range cases {
		if ValidateEvent(c) == nil {
			t.Errorf("accepted invalid event %+v", c)
		}
	}
	for _, result := range []string{"Дозвон", "Недозвон", "Отказ", "Не тот контакт"} {
		if err := ValidateEvent(EventInput{Type: "call", Result: result, PeriodCode: "2026Q3", Date: date}); err != nil {
			t.Fatal(err)
		}
	}
}
