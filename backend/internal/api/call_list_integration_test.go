package api

import (
	"context"
	"encoding/json"
	"github.com/KoznovaAV/Re-Hub/backend/internal/db"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCallListAgainstThirtyControlClients(t *testing.T) {
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
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "contracts", "testing", "h00", "data-30.json"))
	if err != nil {
		t.Fatal(err)
	}
	var input struct {
		Clients []struct {
			ID, Name                   string
			Excluded, Inactive, Closed bool
		}
		Rows []struct {
			ID, Period          string
			Unsent, Total       int
			Observed, Contacted bool
		}
		Expected map[string][]string
	}
	if err = json.Unmarshal(raw, &input); err != nil {
		t.Fatal(err)
	}
	id := func(s string) string { return strings.Replace(s, "BCH", "CLCASE", 1) }
	cleanup := func() {
		pool.Exec(context.Background(), "DELETE FROM slice_records WHERE client_id IN (SELECT id FROM clients WHERE external_id LIKE 'CLCASE%')")
		pool.Exec(context.Background(), "DELETE FROM clients WHERE external_id LIKE 'CLCASE%'")
		pool.Exec(context.Background(), "DELETE FROM slices WHERE file_name='H00-control'")
	}
	cleanup()
	defer cleanup()
	for _, c := range input.Clients {
		stage := "Не в работе"
		if c.Closed {
			stage = "Закрыт"
		}
		_, err = pool.Exec(ctx, "INSERT INTO clients(external_id,name,excluded,inactive,stage) VALUES($1,$2,$3,$4,$5)", id(c.ID), c.Name, c.Excluded, c.Inactive, stage)
		if err != nil {
			t.Fatal(err)
		}
		_, err = pool.Exec(ctx, "INSERT INTO client_tags(client_id,tag) SELECT id,'h00-control' FROM clients WHERE external_id=$1", id(c.ID))
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, period := range []string{"2026Q2", "2026Q3"} {
		_, err = pool.Exec(ctx, "INSERT INTO slices(period_id,slice_date,file_name) SELECT id,'2026-11-22','H00-control' FROM report_periods WHERE label=$1 ON CONFLICT(period_id,slice_date) DO NOTHING", period)
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, r := range input.Rows {
		if r.Observed {
			var total any
			if r.Total > 0 {
				total = r.Total
			}
			_, err = pool.Exec(ctx, `INSERT INTO slice_records(slice_id,client_id,total_docs,not_sent_docs) SELECT s.id,c.id,$1,$2 FROM clients c CROSS JOIN slices s JOIN report_periods p ON p.id=s.period_id WHERE c.external_id=$3 AND p.label=$4 AND s.slice_date='2026-11-22'`, total, r.Unsent, id(r.ID), r.Period)
			if err != nil {
				t.Fatal(err)
			}
		}
		if r.Contacted {
			_, err = pool.Exec(ctx, `INSERT INTO client_events(client_id,event_type,event_date,result,period_code) SELECT id,'call','2026-11-22','Дозвон',$1 FROM clients WHERE external_id=$2`, r.Period, id(r.ID))
			if err != nil {
				t.Fatal(err)
			}
		}
	}
	mux := http.NewServeMux()
	New(pool, store.New(pool), "").Register(mux)
	for _, period := range []string{"2026Q2", "2026Q3"} {
		r := httptest.NewRequest("GET", "/api/v1/call-list?tag=h00-control&period="+period+"&min_unsent=8&min_share=30&contacted=no", nil)
		w := httptest.NewRecorder()
		r.Header.Set("X-Role", "admin")
		mux.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Fatalf("%s: %d %s", period, w.Code, w.Body.String())
		}
		var output struct {
			Data []store.Client
			Meta struct{ Total int }
		}
		if err = json.Unmarshal(w.Body.Bytes(), &output); err != nil {
			t.Fatal(err)
		}
		expected := map[string]bool{}
		for _, value := range input.Expected[period] {
			expected[id(value)] = true
		}
		if len(output.Data) != len(expected) || output.Meta.Total != len(expected) {
			t.Fatalf("%s: got %d total %d; want %d", period, len(output.Data), output.Meta.Total, len(expected))
		}
		for _, client := range output.Data {
			if !expected[client.ExternalID] || client.Latest.PeriodCode != period {
				t.Fatalf("wrong client or period: %+v", client)
			}
		}
	}
	for _, query := range []string{"period=UNKNOWN", "min_unsent=-1", "min_share=NaN", "contacted=maybe"} {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/api/v1/call-list?"+query, nil)
		r.Header.Set("X-Role", "admin")
		mux.ServeHTTP(w, r)
		if w.Code != 422 {
			t.Fatalf("invalid filter accepted: %s %d", query, w.Code)
		}
	}
}
