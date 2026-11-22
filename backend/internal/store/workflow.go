package store

import (
	"fmt"
	"time"
)

// Результат звонка не меняет активность клиента и этап работы.
func ValidateEvent(input EventInput) error {
	invalid := func(message string) error { return fmt.Errorf("%w: %s", ErrInvalidEvent, message) }
	if !input.Date.IsZero() && input.Date.After(time.Now().UTC().Truncate(24*time.Hour)) {
		return invalid("event_date cannot be in the future")
	}
	if input.Stage != "" {
		return invalid("stage changes require a separately agreed workflow")
	}
	if input.Type != "call" {
		if input.Type != "email" && input.Type != "comment" {
			return invalid("unknown event type")
		}
		if input.Result != "" || input.CallbackOn != nil || input.PromisedAt != nil {
			return invalid("call fields are not allowed for email or comment")
		}
		return nil
	}
	switch input.Result {
	case "Дозвон", "Недозвон", "Перенос", "Не тот контакт", "Не тот администратор", "Обещание", "Отказ":
	default:
		return invalid("unknown call result")
	}
	if input.PeriodCode == "" {
		return invalid("period_code is required for a call")
	}
	date := input.Date
	if date.IsZero() {
		date = time.Now().UTC().Truncate(24 * time.Hour)
	}
	if input.Result == "Перенос" {
		if input.CallbackOn == nil || input.CallbackOn.Before(date) {
			return invalid("callback_on must not precede event_date")
		}
	} else if input.CallbackOn != nil {
		return invalid("callback_on is only for a postponed call")
	}
	if input.Result == "Обещание" {
		if input.PromisedAt == nil || input.PromisedAt.Before(date) {
			return invalid("promised_at must not precede event_date")
		}
	} else if input.PromisedAt != nil {
		return invalid("promised_at is only for a document promise")
	}
	return nil
}
