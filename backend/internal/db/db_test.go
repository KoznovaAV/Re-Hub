package db

import (
	"context"
	"os"
	"testing"
	"time"
)

func TestMigrateAndSeed(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := Open(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	if _, err := Migrate(ctx, pool); err != nil {
		t.Fatal(err)
	}
	var periods, users, migrations int
	if err := pool.QueryRow(ctx, "SELECT COUNT(*) FROM report_periods").Scan(&periods); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, "SELECT COUNT(*) FROM users").Scan(&users); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, "SELECT COUNT(*) FROM schema_migrations").Scan(&migrations); err != nil {
		t.Fatal(err)
	}
	if periods < 4 || users < 3 || migrations < 2 {
		t.Fatalf("unexpected seed: periods=%d users=%d migrations=%d", periods, users, migrations)
	}

	applied, err := Migrate(ctx, pool)
	if err != nil {
		t.Fatal(err)
	}
	if len(applied) != 0 {
		t.Fatalf("second migrate applied %v", applied)
	}
}
