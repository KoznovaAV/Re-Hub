package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/KoznovaAV/Re-Hub/backend/internal/api"
	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"github.com/KoznovaAV/Re-Hub/backend/internal/probe"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pythonURL := strings.TrimRight(env("PYTHON_SERVICE_URL", "http://127.0.0.1:8001"), "/")

	var pool *pgxpool.Pool
	var data *store.Store
	if databaseURL := env("DATABASE_URL", ""); databaseURL != "" {
		var err error
		pool, err = db.Open(ctx, databaseURL)
		if err != nil {
			log.Fatalf("database connection failed: %v", err)
		}
		defer pool.Close()
		if applied, err := db.Migrate(ctx, pool); err != nil {
			log.Fatalf("database migration failed: %v", err)
		} else {
			log.Printf("database ready, migrations applied: %d", len(applied))
		}
		data = store.New(pool)
	} else {
		log.Printf("DATABASE_URL is empty; data API is disabled")
	}

	mux := http.NewServeMux()
	mux.Handle("GET /api/probe", probe.NewHandler(pythonURL))
	writeTimeout := 120 * time.Second
	api.New(pool, data, pythonURL).Register(mux)

	server := &http.Server{
		Addr:              env("BACKEND_ADDR", "127.0.0.1:8080"),
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       30 * time.Second,
	}

	go func() {
		log.Printf("Go API listening on %s", server.Addr)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server failed: %v", err)
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("server shutdown: %v", err)
	}
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
