package api

import (
	"encoding/json"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
	"net/http"
)

// Read a page and its histories in bulk, avoiding a request per client.
func (s *Server) workspace(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	limit, offset := parseLimit(r)
	clients, total, err := s.store.ListClients(r.Context(), store.ListFilters{WorkOnly: !isAdmin(r), Limit: limit, Offset: offset, Sort: "external_id"})
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not load workspace")
		return
	}
	ids := []string{}
	for _, c := range clients {
		ids = append(ids, c.ID)
	}
	sections := map[string]map[string]json.RawMessage{}
	queries := map[string]string{
		"history": `SELECT sr.client_id::text,jsonb_agg(jsonb_build_object('period_code',p.label,'slice_date',s.slice_date,'total_docs',sr.total_docs,'not_sent_docs',sr.not_sent_docs) ORDER BY p.year,p.quarter,s.slice_date,s.id) FROM slice_records sr JOIN slices s ON s.id=sr.slice_id JOIN report_periods p ON p.id=s.period_id WHERE sr.client_id=ANY($1::uuid[]) GROUP BY sr.client_id`,
		"events":  `SELECT e.client_id::text,jsonb_agg(jsonb_build_object('id',e.id,'event_type',e.event_type,'event_date',e.event_date,'result',e.result,'promised_at',e.promised_at,'promise_label',e.promise_label,'callback_on',e.callback_on,'period_code',e.period_code,'comment',e.comment,'author_name',u.username,'created_at',e.created_at) ORDER BY e.event_date DESC,e.created_at DESC) FROM client_events e LEFT JOIN users u ON u.id=e.author_id WHERE e.client_id=ANY($1::uuid[]) GROUP BY e.client_id`,
		"actions": `SELECT client_id::text,jsonb_agg(jsonb_build_object('id',id,'kind',kind,'number',letter_number,'date',letter_date,'status',status,'comment',comment) ORDER BY letter_date DESC,created_at DESC) FROM client_actions WHERE client_id=ANY($1::uuid[]) GROUP BY client_id`,
	}
	for section, q := range queries {
		rows, e := s.pool.Query(r.Context(), q, ids)
		if e != nil {
			writeError(w, 500, "DB_ERROR", "Could not load history")
			return
		}
		values := map[string]json.RawMessage{}
		for rows.Next() {
			var id string
			var raw []byte
			if e = rows.Scan(&id, &raw); e != nil {
				rows.Close()
				writeError(w, 500, "DB_ERROR", "Could not read history")
				return
			}
			values[id] = json.RawMessage(raw)
		}
		e = rows.Err()
		rows.Close()
		if e != nil {
			writeError(w, 500, "DB_ERROR", "Could not read history")
			return
		}
		sections[section] = values
	}
	writeJSON(w, 200, map[string]any{"data": clients, "meta": map[string]int{"total": total, "limit": limit, "offset": offset}, "history": sections["history"], "events": sections["events"], "actions": sections["actions"]})
}
