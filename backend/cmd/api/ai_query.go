package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"time"
)

// Wait longer than the Python demo client so its response can reach the browser.
const aiQueryTimeout = 95 * time.Second

func aiQuery(pythonURL string) http.HandlerFunc {
	client := &http.Client{
		Timeout:       aiQueryTimeout,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
	}
	return func(w http.ResponseWriter, r *http.Request) {
		contentType, _, _ := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if contentType != "application/json" {
			writeJSON(w, http.StatusUnsupportedMediaType, map[string]string{"error": "expected_json"})
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 32768)
		body, err := io.ReadAll(r.Body)
		if err != nil {
			var limit *http.MaxBytesError
			if errors.As(err, &limit) {
				writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "body_too_large"})
			} else {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_body"})
			}
			return
		}
		upstream, err := http.NewRequestWithContext(r.Context(), http.MethodPost, pythonURL+"/ai/query", bytes.NewReader(body))
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "python_unavailable"})
			return
		}
		upstream.Header.Set("Content-Type", "application/json")
		result, err := client.Do(upstream)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "python_unavailable"})
			return
		}
		defer result.Body.Close()
		reply, err := io.ReadAll(io.LimitReader(result.Body, 65537))
		if err != nil || len(reply) > 65536 || !json.Valid(reply) ||
			(result.StatusCode >= 300 && result.StatusCode < 400) {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "invalid_python_response"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(result.StatusCode)
		_, _ = w.Write(reply)
	}
}
