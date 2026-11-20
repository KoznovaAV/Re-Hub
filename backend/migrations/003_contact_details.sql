-- Контакты из справочника сохраняются отдельно от названия организации.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_details TEXT;
