// Seeds only a dedicated synthetic benchmark database.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"github.com/jackc/pgx/v5"
	"os"
	"time"
)

type client struct {
	ID, Name                   string
	Excluded, Inactive, Closed bool
}
type row struct {
	ID, Period                                      string
	Unsent, Total                                   int
	Excluded, Inactive, Contacted, Observed, Closed bool
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	if len(os.Args) != 2 {
		return fmt.Errorf("usage: h00-fixture data.json")
	}
	cfg, err := pgx.ParseConfig(os.Getenv("H00_BENCH_DATABASE_URL"))
	if err != nil {
		return err
	}
	if cfg.Database != "h00_benchmark" {
		return fmt.Errorf("only the disposable h00_benchmark database is allowed")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	admin := cfg.Copy()
	admin.Database = "postgres"
	conn, err := pgx.ConnectConfig(ctx, admin)
	if err != nil {
		return err
	}
	var exists bool
	err = conn.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='h00_benchmark')").Scan(&exists)
	if err == nil && !exists {
		_, err = conn.Exec(ctx, "CREATE DATABASE h00_benchmark")
	}
	conn.Close(ctx)
	if err != nil {
		return err
	}
	pool, err := db.Open(ctx, os.Getenv("H00_BENCH_DATABASE_URL"))
	if err != nil {
		return err
	}
	defer pool.Close()
	if _, err = db.Migrate(ctx, pool); err != nil {
		return err
	}
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		return err
	}
	var data struct {
		Synthetic bool
		Clients   []client
		Rows      []row
	}
	if err = json.Unmarshal(raw, &data); err != nil {
		return err
	}
	if !data.Synthetic {
		return fmt.Errorf("synthetic input required")
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, "TRUNCATE clients, slices, import_jobs CASCADE"); err != nil {
		return err
	}
	batch := &pgx.Batch{}
	for _, c := range data.Clients {
		stage := "Не в работе"
		if c.Closed {
			stage = "Закрыт"
		}
		batch.Queue("INSERT INTO clients(external_id,name,excluded,inactive,stage) VALUES($1,$2,$3,$4,$5)", c.ID, c.Name, c.Excluded, c.Inactive, stage)
	}
	if err = tx.SendBatch(ctx, batch).Close(); err != nil {
		return err
	}
	for _, p := range []string{"2026Q2", "2026Q3"} {
		date := "2026-07-20"
		if p == "2026Q3" {
			date = "2026-10-20"
		}
		if _, err = tx.Exec(ctx, "INSERT INTO slices(period_id,slice_date,file_name) SELECT id,$1::date,'H00 synthetic benchmark' FROM report_periods WHERE label=$2", date, p); err != nil {
			return err
		}
	}
	batch = &pgx.Batch{}
	for _, r := range data.Rows {
		if r.Observed {
			var total any
			if r.Total > 0 {
				total = r.Total
			}
			batch.Queue(`INSERT INTO slice_records(slice_id,client_id,total_docs,not_sent_docs) SELECT s.id,c.id,$1,$2 FROM clients c CROSS JOIN slices s JOIN report_periods p ON p.id=s.period_id WHERE c.external_id=$3 AND p.label=$4`, total, r.Unsent, r.ID, r.Period)
		}
		if r.Contacted {
			batch.Queue(`INSERT INTO client_events(client_id,event_type,event_date,result,period_code) SELECT id,'call','2026-11-22','Дозвон',$1 FROM clients WHERE external_id=$2`, r.Period, r.ID)
		}
	}
	if err = tx.SendBatch(ctx, batch).Close(); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
