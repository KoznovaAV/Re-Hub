package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/KoznovaAV/Re-Hub/backend/internal/probe"
)

func main() {
	pythonURL := strings.TrimRight(env("PYTHON_SERVICE_URL", "http://127.0.0.1:8001"), "/")
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "backend"})
	})
	mux.Handle("GET /api/probe", probe.NewHandler(pythonURL))
	writeTimeout := 5 * time.Second
	if os.Getenv("REHUB_AI_DEMO") == "1" {
		mux.HandleFunc("POST /ai/query", aiQuery(pythonURL))
		// Даём Python дождаться Ollama до истечения таймаута ответа Go.
		writeTimeout = 35 * time.Second
	}

	addr := env("BACKEND_ADDR", "127.0.0.1:8080")
	server := &http.Server{
		Addr: addr, Handler: mux,
		ReadHeaderTimeout: 3 * time.Second, IdleTimeout: 30 * time.Second,
		WriteTimeout: writeTimeout,
	}
	log.Printf("Go API listening on %s", addr)
	log.Fatal(server.ListenAndServe())
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
