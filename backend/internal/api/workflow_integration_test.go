package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

func TestWorkflowThroughHTTPAndPostgres(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	pool, err := db.Open(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	if _, err = db.Migrate(ctx, pool); err != nil {
		t.Fatal(err)
	}
	const code = "WFTEST01"
	const b = "00000000-0000-0000-0000-000000000003"
	_, err = pool.Exec(ctx, `INSERT INTO clients(external_id,name,assigned_to,stage,promised_at) VALUES($1,'Workflow regression',$2::uuid,'В работе','2026-12-10') ON CONFLICT(external_id) DO UPDATE SET assigned_to=$2::uuid, stage='В работе', inactive=false,promised_at='2026-12-10'`, code, demoOperatorID)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Exec(context.Background(), "DELETE FROM clients WHERE external_id=$1", code)
	mux := http.NewServeMux()
	New(pool, store.New(pool), "").Register(mux)
	request := func(method, path, actor, body string, want int) map[string]any {
		t.Helper()
		r := httptest.NewRequest(method, "/api/v1/clients/"+code+path, strings.NewReader(body))
		r.Header.Set("X-User-Id", actor)
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, r)
		if w.Code != want {
			t.Fatalf("%s %s: %d %s", method, path, w.Code, w.Body.String())
		}
		var result map[string]any
		json.Unmarshal(w.Body.Bytes(), &result)
		return result
	}
	request("POST", "/take-over", demoAdminID, "{}", 403)
	request("POST", "/events", b, `{"event_type":"call","result":"Недозвон","period_code":"2026Q3"}`, 403)
	request("POST", "/take-over", b, `{"user_id":"`+demoOperatorID+`"}`, 400)
	request("POST", "/events", demoOperatorID, `{"event_type":"call","result":"Отказ","period_code":"2026Q3","event_date":"2026-11-22"}`, 201)
	var stage string
	var inactive bool
	var promise string
	if err := pool.QueryRow(ctx, "SELECT stage,inactive,promised_at::text FROM clients WHERE external_id=$1", code).Scan(&stage, &inactive, &promise); err != nil {
		t.Fatal(err)
	}
	if stage != "В работе" || inactive || promise != "2026-12-10" {
		t.Fatalf("refusal changed workflow: %s %v %s", stage, inactive, promise)
	}
	request("POST", "/take-over", b, "{}", 200)
	request("POST", "/events", demoOperatorID, `{"event_type":"comment","comment":"stale owner"}`, 403)
	request("POST", "/events", b, `{"event_type":"call","result":"Перенос","period_code":"2026Q3","event_date":"2026-11-22"}`, 422)
	response := request("POST", "/events", b, `{"event_type":"call","result":"Перенос","period_code":"2026Q3","callback_on":"2026-12-01","event_date":"2026-11-22"}`, 201)
	event := response["data"].(map[string]any)
	if event["callback_on"] != "2026-12-01T00:00:00Z" || event["period_code"] != "2026Q3" {
		t.Fatalf("callback lost: %#v", event)
	}
	read := request("GET", "", b, "", 200)
	events := read["events"].([]any)
	found := false
	for _, raw := range events {
		item := raw.(map[string]any)
		if item["id"] == event["id"] {
			found = item["callback_on"] == event["callback_on"]
		}
	}
	if !found {
		t.Fatal("callback did not survive a new HTTP read")
	}
	request("POST", "/events", b, `{"event_type":"call","result":"Отказ","period_code":"UNKNOWN"}`, 422)
}
