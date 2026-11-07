package probe

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestProbeResponseValidation(t *testing.T) {
	const valid = `{"schema_version":1,"request_id":"skeleton","status":"ok"}`
	tests := []struct {
		name, contentType, body string
		upstream, expected      int
	}{
		{"valid", "application/json; charset=utf-8", valid, 200, 200},
		{"wrong identifier", "application/json", strings.Replace(valid, "skeleton", "other", 1), 200, 502},
		{"wrong content type", "text/plain", valid, 200, 502},
		{"trailing value", "application/json", valid + "{}", 200, 502},
		{"unexpected field", "application/json", strings.TrimSuffix(valid, "}") + `,"extra":true}`, 200, 502},
		{"oversize", "application/json", valid + strings.Repeat(" ", 4096), 200, 502},
		{"upstream error", "application/json", valid, 500, 502},
		{"redirect", "application/json", valid, 302, 502},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != http.MethodPost || r.URL.Path != "/probe" {
					t.Errorf("unexpected upstream request: %s %s", r.Method, r.URL.Path)
				}
				w.Header().Set("Content-Type", test.contentType)
				if test.upstream == http.StatusFound {
					w.Header().Set("Location", "/redirected")
				}
				w.WriteHeader(test.upstream)
				_, _ = w.Write([]byte(test.body))
			}))
			defer upstream.Close()
			result := httptest.NewRecorder()
			NewHandler(upstream.URL).ServeHTTP(result, httptest.NewRequest(http.MethodGet, "/api/probe", nil))
			if result.Code != test.expected {
				t.Fatalf("got status %d, want %d: %s", result.Code, test.expected, result.Body)
			}
			if result.Header().Get("Cache-Control") != "no-store" {
				t.Fatal("probe response is cacheable")
			}
		})
	}
}

func TestProbeUnavailable(t *testing.T) {
	upstream := httptest.NewServer(http.NotFoundHandler())
	url := upstream.URL
	upstream.Close()

	result := httptest.NewRecorder()
	NewHandler(url).ServeHTTP(result, httptest.NewRequest(http.MethodGet, "/api/probe", nil))
	if result.Code != http.StatusServiceUnavailable {
		t.Fatalf("got %d, want 503", result.Code)
	}
}
