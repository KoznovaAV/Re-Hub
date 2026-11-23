package api

import (
	"context"
	"encoding/json"
	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestCustomerRequirementsPersistThroughAPI(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TEST_DATABASE_URL required")
	}
	ctx := context.Background()
	pool, err := db.Open(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	if _, err = db.Migrate(ctx, pool); err != nil {
		t.Fatal(err)
	}
	data := store.New(pool)
	mux := http.NewServeMux()
	New(pool, data, "").Register(mux)
	const b = "00000000-0000-0000-0000-000000000003"
	codes := []string{"REQ-A", "REQ-MISSING", "REQ-LOW", "REQ-NEW"}
	defer pool.Exec(ctx, `DELETE FROM clients WHERE external_id=ANY($1::text[])`, codes)
	defer pool.Exec(ctx, `DELETE FROM slices WHERE file_name='customer-requirements-test'`)
	pool.Exec(ctx, `DELETE FROM clients WHERE external_id=ANY($1::text[])`, codes)
	for _, code := range codes {
		_, err = pool.Exec(ctx, `INSERT INTO clients(external_id,name) VALUES($1,$1)`, code)
		if err != nil {
			t.Fatal(err)
		}
	}
	_, err = pool.Exec(ctx, `INSERT INTO client_tags(client_id,tag) SELECT id,'newcomer' FROM clients WHERE external_id='REQ-NEW'`)
	if err != nil {
		t.Fatal(err)
	}
	total := 100
	date := func(value string) time.Time { d, _ := time.Parse("2006-01-02", value); return d }
	save := func(day string, rows []store.ParsedRow) {
		t.Helper()
		if _, e := data.SaveSnapshot(ctx, "customer-requirements-test", []string{"2026Q3"}, date(day), demoAdminID, len(rows), rows, nil); e != nil {
			t.Fatal(e)
		}
	}
	save("2026-11-25", []store.ParsedRow{{ExternalID: codes[0], PeriodCode: "2026Q3", TotalDocs: &total, NotSent: 40}, {ExternalID: codes[1], PeriodCode: "2026Q3", TotalDocs: &total, NotSent: 40}})
	save("2026-11-26", []store.ParsedRow{{ExternalID: codes[0], PeriodCode: "2026Q3", NotSent: 20}, {ExternalID: codes[2], PeriodCode: "2026Q3", TotalDocs: &total, NotSent: 4}, {ExternalID: codes[3], PeriodCode: "2026Q3", TotalDocs: &total, NotSent: 4}})
	c, err := data.GetClient(ctx, codes[0])
	if err != nil {
		t.Fatal(err)
	}
	history, err := data.History(ctx, c.ID)
	if err != nil || len(history) != 2 || c.Previous == nil || c.Previous.NotSentDocs != 40 || c.Latest.NotSentDocs != 20 || c.Latest.TotalDocs == nil || *c.Latest.TotalDocs != 100 {
		t.Fatalf("snapshot history lost: %+v %+v %v", c, history, err)
	}
	request := func(method, path, actor, role, body string, want int) map[string]any {
		t.Helper()
		r := httptest.NewRequest(method, "/api/v1"+path, strings.NewReader(body))
		r.Header.Set("X-User-Id", actor)
		r.Header.Set("X-Role", role)
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, r)
		if w.Code != want {
			t.Fatalf("%s %s: %d %s", method, path, w.Code, w.Body.String())
		}
		var result map[string]any
		if e := json.Unmarshal(w.Body.Bytes(), &result); e != nil {
			t.Fatal(e)
		}
		return result
	}
	// Candidate list is independent from membership in the operator pool.
	list := request("GET", "/call-list?period=2026Q3", demoAdminID, "admin", "", 200)
	found := map[string]bool{}
	for _, raw := range list["data"].([]any) {
		found[raw.(map[string]any)["external_id"].(string)] = true
	}
	if !found[codes[0]] || found[codes[1]] || found[codes[2]] || !found[codes[3]] {
		t.Fatalf("bad candidate list: %v", found)
	}
	request("GET", "/clients/REQ-A", demoOperatorID, "operator", "", 403)
	request("POST", "/clients/REQ-A/take", demoOperatorID, "operator", "{}", 409)
	request("POST", "/pool", demoOperatorID, "operator", `{"ids":["REQ-A"]}`, 403)
	request("POST", "/pool", demoAdminID, "admin", `{"ids":["REQ-A","REQ-LOW"],"period":"2026Q3"}`, 200)
	request("POST", "/clients/REQ-A/take", demoOperatorID, "operator", "{}", 200)
	request("POST", "/clients/REQ-A/reassign", demoAdminID, "admin", `{"user_id":"`+b+`"}`, 403)
	request("POST", "/clients/REQ-A/reassign", demoOperatorID, "operator", `{"user_id":"`+b+`"}`, 200)
	request("POST", "/clients/REQ-A/events", demoOperatorID, "operator", `{"event_type":"comment","comment":"former owner"}`, 403)
	request("POST", "/clients/REQ-A/events", b, "operator", `{"event_type":"comment","event_date":"2026-10-01","comment":"Historical note"}`, 201)
	request("POST", "/clients/REQ-A/release", b, "operator", "{}", 200)
	c, err = data.GetClient(ctx, "REQ-A")
	if err != nil || c.AssignedTo != "" || !c.InPool {
		t.Fatalf("release not persisted: %+v %v", c, err)
	}
	request("POST", "/clients/REQ-A/actions", b, "operator", `{"kind":"claim","number":"42","date":"2026-11-01","status":"Направлена"}`, 403)
	request("POST", "/clients/REQ-A/actions", demoAdminID, "admin", `{"kind":"claim","number":"42","date":"2026-11-01","status":"Направлена"}`, 201)
	read := request("GET", "/clients/REQ-A", demoAdminID, "admin", "", 200)
	if len(read["history"].([]any)) != 2 || len(read["actions"].([]any)) != 1 {
		t.Fatal("history/actions lost after new read")
	}
	events := read["events"].([]any)
	historical := false
	for _, raw := range events {
		e := raw.(map[string]any)
		if e["comment"] == "Historical note" {
			historical = strings.HasPrefix(e["event_date"].(string), "2026-10-01")
		}
	}
	if !historical {
		t.Fatal("actual historical event date lost")
	}
	request("GET", "/workspace", b, "operator", "", 200)
}
