package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAdministratorCannotPerformOperatorActions(t *testing.T) {
	mux := http.NewServeMux()
	New(nil, nil, "").Register(mux)
	for _, path := range []string{"take", "take-over", "events", "release", "reassign"} {
		for _, header := range []string{"role", "identity"} {
			req := httptest.NewRequest("POST", "/api/v1/clients/test/"+path, strings.NewReader("{}"))
			if header == "role" {
				req.Header.Set("X-Role", "admin")
			} else {
				req.Header.Set("X-User-Id", demoAdminID)
			}
			res := httptest.NewRecorder()
			mux.ServeHTTP(res, req)
			if res.Code != 403 {
				t.Fatalf("%s %s: %d %s", path, header, res.Code, res.Body.String())
			}
		}
	}
}
