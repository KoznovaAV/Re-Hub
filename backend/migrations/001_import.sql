-- Включаем расширение для UUID, если его нет
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Пользователи (Админы и Операторы)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Клиенты
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Внутренний UUID
    external_id TEXT UNIQUE NOT NULL,               -- Внешний код КЦР
    inn TEXT NOT NULL,                              -- Не уникален
    kpp TEXT,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Отчётные периоды (Например: 2026-Q1)
CREATE TABLE report_periods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    year INT NOT NULL,
    quarter INT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    label TEXT NOT NULL UNIQUE,
    UNIQUE (year, quarter)
);

-- 4. Срезы (История загрузок)
CREATE TABLE slices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_id UUID NOT NULL REFERENCES report_periods(id),
    slice_date DATE NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (period_id, slice_date) -- Защита от дублей срезов
);

-- 5. Записи внутри среза (Сколько должен / Сколько не передан)
CREATE TABLE slice_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slice_id UUID NOT NULL REFERENCES slices(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id),
    total_docs INT,
    not_sent_docs INT NOT NULL,
    UNIQUE (slice_id, client_id) -- Один клиент - одна запись в срезе
);