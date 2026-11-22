-- Дата повторного звонка отделена от срока передачи документов.
ALTER TABLE client_events ADD COLUMN callback_on DATE;
ALTER TABLE client_events ADD COLUMN period_code TEXT REFERENCES report_periods(label);
ALTER TABLE client_events ADD CONSTRAINT callback_requires_transfer CHECK (
    (event_type = 'call' AND result = 'Перенос' AND callback_on IS NOT NULL AND callback_on >= event_date)
    OR (callback_on IS NULL AND COALESCE(result, '') <> 'Перенос')
) NOT VALID;

-- Старые события без даты переноса сохраняются, новые проходят проверку.
