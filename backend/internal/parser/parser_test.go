package parser

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestParseTransfersContextAndContacts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/parse" {
			t.Error("unexpected route")
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Error(err)
			w.WriteHeader(400)
			return
		}
		f, _, err := r.FormFile("file")
		if err != nil {
			t.Error(err)
			return
		}
		f.Close()
		var ctx map[string]any
		if err := json.Unmarshal([]byte(r.FormValue("context")), &ctx); err != nil || ctx["file_kind"] != "clients" {
			t.Error("context lost")
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"contract_version":"1.0","file_kind":"clients","key_mode":"anonymous","nonempty_row_count":1,"rows":[{"source":{"sheet":"Все КЦР","row":3},"data":{"external_id":"AAA00001","contact_details":"Контакт 1","excluded":true,"active":false}}],"errors":[]}`))
	}))
	defer server.Close()
	path := filepath.Join(t.TempDir(), "clients.xlsx")
	if err := os.WriteFile(path, []byte("fixture"), 0600); err != nil {
		t.Fatal(err)
	}
	result, err := New(server.URL).Parse(context.Background(), path, map[string]any{"file_kind": "clients"})
	if err != nil {
		t.Fatal(err)
	}
	var row ClientData
	if err := json.Unmarshal(result.Rows[0].Data, &row); err != nil {
		t.Fatal(err)
	}
	if row.ContactDetails == nil || *row.ContactDetails != "Контакт 1" || row.Name != "" || row.Excluded == nil || !*row.Excluded || row.Active == nil || *row.Active {
		t.Fatalf("contact or flags lost: %#v", row)
	}
}
