package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

type probe struct {
	Version   int    `json:"schema_version"`
	RequestID string `json:"request_id"`
}

type probeResult struct {
	probe
	Status string `json:"status"`
}

func main() {
	pythonURL := strings.TrimRight(env("PYTHON_SERVICE_URL", "http://127.0.0.1:8001"), "/")
	client := &http.Client{Timeout: 2 * time.Second}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "backend"})
	})
	mux.HandleFunc("GET /api/probe", func(w http.ResponseWriter, r *http.Request) {
		payload := probe{Version: 1, RequestID: "skeleton"}
		body, err := json.Marshal(payload)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "probe_encoding_failed"})
			return
		}
		req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, pythonURL+"/probe", bytes.NewReader(body))
		if err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "python_unavailable"})
			return
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "python_unavailable"})
			return
		}
		defer resp.Body.Close()

		var result probeResult
		err = json.NewDecoder(io.LimitReader(resp.Body, 4096)).Decode(&result)
		if resp.StatusCode != http.StatusOK || err != nil || result.probe != payload || result.Status != "ok" {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "invalid_python_response"})
			return
		}
		writeJSON(w, http.StatusOK, result)
	})

	addr := env("BACKEND_ADDR", "127.0.0.1:8080")
	server := &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 3 * time.Second, WriteTimeout: 5 * time.Second}
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
