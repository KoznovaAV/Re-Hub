package api

import (
	"encoding/json"
	"errors"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
	"net/http"
	"time"
)

func (s *Server) assignmentResult(w http.ResponseWriter, c *store.Client, err error) {
	if errors.Is(err, store.ErrForbidden) {
		writeError(w, 403, "FORBIDDEN", "Only the assigned operator may transfer or release a client")
		return
	}
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, 404, "CLIENT_NOT_FOUND", "Active client not found")
		return
	}
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not change assignment")
		return
	}
	writeJSON(w, 200, map[string]any{"data": c})
}
func (s *Server) releaseClient(w http.ResponseWriter, r *http.Request) {
	if !operatorAction(w, r) || !s.ready(w) {
		return
	}
	c, err := s.store.Transfer(r.Context(), r.PathValue("external_id"), actorID(r), "")
	s.assignmentResult(w, c, err)
}
func (s *Server) reassignClient(w http.ResponseWriter, r *http.Request) {
	if !operatorAction(w, r) || !s.ready(w) {
		return
	}
	var p struct {
		Target string `json:"user_id"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&p); err != nil || p.Target == "" {
		writeError(w, 400, "INVALID_BODY", "user_id is required")
		return
	}
	// The prototype exposes two seeded operators. Unknown and administrative targets
	// are rejected before the value reaches a UUID cast.
	if p.Target != demoOperatorID && p.Target != "00000000-0000-0000-0000-000000000003" {
		writeError(w, 422, "INVALID_OPERATOR", "Select an available operator")
		return
	}
	c, err := s.store.Transfer(r.Context(), r.PathValue("external_id"), actorID(r), p.Target)
	s.assignmentResult(w, c, err)
}
func (s *Server) addToPool(w http.ResponseWriter, r *http.Request) {
	if !isAdmin(r) {
		writeError(w, 403, "FORBIDDEN", "Only administrators prepare the pool")
		return
	}
	if !s.ready(w) {
		return
	}
	var p struct {
		IDs    []string `json:"ids"`
		Period string   `json:"period"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 128<<10)).Decode(&p); err != nil || len(p.IDs) == 0 || len(p.IDs) > 5000 {
		writeError(w, 400, "INVALID_BODY", "Supply 1 to 5000 client codes")
		return
	}
	if p.Period == "" {
		p.Period, _ = s.store.LatestPeriod(r.Context())
	}
	n, err := s.store.AddToPool(r.Context(), p.IDs, p.Period, actorID(r))
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not prepare pool")
		return
	}
	writeJSON(w, 200, map[string]any{"changed": n})
}
func (s *Server) addClientAction(w http.ResponseWriter, r *http.Request) {
	if !isAdmin(r) {
		writeError(w, 403, "FORBIDDEN", "Only administrators record claims and sanctions")
		return
	}
	if !s.ready(w) {
		return
	}
	var p struct {
		Kind    string `json:"kind"`
		Number  string `json:"number"`
		Date    string `json:"date"`
		Status  string `json:"status"`
		Comment string `json:"comment"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&p); err != nil {
		writeError(w, 400, "INVALID_BODY", "Invalid JSON")
		return
	}
	date, err := time.Parse("2006-01-02", p.Date)
	if err != nil {
		writeError(w, 422, "INVALID_DATE", "date must be YYYY-MM-DD")
		return
	}
	a, err := s.store.AddAction(r.Context(), r.PathValue("external_id"), actorID(r), store.ClientAction{Kind: p.Kind, Number: p.Number, Date: date, Status: p.Status, Comment: p.Comment})
	if errors.Is(err, store.ErrInvalidEvent) {
		writeError(w, 422, "INVALID_ACTION", "kind, letter number, date and status are required")
		return
	}
	if errors.Is(err, store.ErrForbidden) {
		writeError(w, 403, "FORBIDDEN", "Administrative action required")
		return
	}
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not record action")
		return
	}
	writeJSON(w, 201, map[string]any{"data": a})
}
