package probe

import (
	"bytes"
	"encoding/json"
	"io"
	"mime"
	"net/http"
	"strings"
	"time"
)

const (
	RequestJSON = `{"schema_version":1,"request_id":"skeleton"}`
	maxResponse = 4096
)

type Result struct {
	Version   int    `json:"schema_version"`
	RequestID string `json:"request_id"`
	Status    string `json:"status"`
}

func NewHandler(pythonURL string) http.Handler {
	client := &http.Client{
		Timeout:       2 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	url := strings.TrimRight(pythonURL, "/") + "/probe"

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, url, strings.NewReader(RequestJSON))
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

		result, ok := readResult(resp)
		if !ok {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "invalid_python_response"})
			return
		}
		writeJSON(w, http.StatusOK, result)
	})
}

func readResult(resp *http.Response) (Result, bool) {
	var result Result
	mediaType, _, err := mime.ParseMediaType(resp.Header.Get("Content-Type"))
	if resp.StatusCode != http.StatusOK || err != nil || mediaType != "application/json" {
		return result, false
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxResponse+1))
	if err != nil || len(body) > maxResponse {
		return result, false
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&result) != nil || decoder.Decode(new(any)) != io.EOF {
		return result, false
	}
	return result, result == (Result{Version: 1, RequestID: "skeleton", Status: "ok"})
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
