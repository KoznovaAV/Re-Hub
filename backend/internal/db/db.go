package db

import (
	"context"
	"fmt"
	"io/fs"
	"log"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/KoznovaAV/Re-Hub/backend/migrations"
)

func Open(ctx context.Context, url string) (*pgxpool.Pool, error) {
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("parse database url: %w", err)
	}
	config.MaxConns = 10
	config.MinConns = 1
	config.MaxConnLifetime = time.Hour
	config.MaxConnIdleTime = 15 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("create database pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}
	return pool, nil
}

func Healthy(ctx context.Context, pool *pgxpool.Pool) error {
	if pool == nil {
		return fmt.Errorf("database is not configured")
	}
	return pool.Ping(ctx)
}

func Migrate(ctx context.Context, pool *pgxpool.Pool) ([]string, error) {
	if pool == nil {
		return nil, fmt.Errorf("database is not configured")
	}
	if _, err := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)`); err != nil {
		return nil, fmt.Errorf("create schema_migrations: %w", err)
	}

	entries, err := fs.ReadDir(migrations.FS, ".")
	if err != nil {
		return nil, fmt.Errorf("read migrations: %w", err)
	}
	var files []string
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".sql") {
			files = append(files, entry.Name())
		}
	}
	sort.Strings(files)

	applied := make([]string, 0, len(files))
	for _, name := range files {
		var exists bool
		if err := pool.QueryRow(ctx, "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)", name).Scan(&exists); err != nil {
			return applied, fmt.Errorf("check migration %s: %w", name, err)
		}
		if exists {
			continue
		}

		body, err := fs.ReadFile(migrations.FS, name)
		if err != nil {
			return applied, fmt.Errorf("read migration %s: %w", name, err)
		}
		tx, err := pool.Begin(ctx)
		if err != nil {
			return applied, fmt.Errorf("begin migration %s: %w", name, err)
		}
		if err := applyStatements(ctx, tx, string(body)); err != nil {
			_ = tx.Rollback(ctx)
			return applied, fmt.Errorf("apply migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, "INSERT INTO schema_migrations (version) VALUES ($1)", name); err != nil {
			_ = tx.Rollback(ctx)
			return applied, fmt.Errorf("record migration %s: %w", name, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return applied, fmt.Errorf("commit migration %s: %w", name, err)
		}
		applied = append(applied, name)
		log.Printf("applied migration %s", name)
	}
	return applied, nil
}

// applyStatements executes the simple SQL files in this repository one statement
// at a time. The files contain no procedural blocks or quoted semicolons.
func applyStatements(ctx context.Context, tx pgx.Tx, body string) error {
	var clean strings.Builder
	for _, line := range strings.Split(body, "\n") {
		if index := strings.Index(line, "--"); index >= 0 {
			line = line[:index]
		}
		clean.WriteString(line)
		clean.WriteByte('\n')
	}
	for _, statement := range strings.Split(clean.String(), ";") {
		statement = strings.TrimSpace(statement)
		if statement == "" {
			continue
		}
		if _, err := tx.Exec(ctx, statement); err != nil {
			return err
		}
	}
	return nil
}
