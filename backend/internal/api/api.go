package api

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/KoznovaAV/Re-Hub/backend/internal/parser"
	"github.com/KoznovaAV/Re-Hub/backend/internal/store"
)

const (
	demoOperatorID = "00000000-0000-0000-0000-000000000002"
	demoAdminID    = "00000000-0000-0000-0000-000000000001"
)

type Server struct {
	pool   *pgxpool.Pool
	store  *store.Store
	parser *parser.Client
}

func New(pool *pgxpool.Pool, data *store.Store, parserURL string) *Server {
	return &Server{pool: pool, store: data, parser: parser.New(parserURL)}
}

func (s *Server) Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /api/v1/workspace", s.workspace)
	mux.HandleFunc("GET /api/v1/periods", s.listPeriods)
	mux.HandleFunc("GET /api/v1/slices", s.listSlices)
	mux.HandleFunc("GET /api/v1/clients", s.listClients)
	mux.HandleFunc("GET /api/v1/clients/{external_id}", s.getClient)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/take", s.takeClient)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/take-over", s.takeOverClient)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/events", s.addEvent)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/release", s.releaseClient)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/reassign", s.reassignClient)
	mux.HandleFunc("POST /api/v1/clients/{external_id}/actions", s.addClientAction)
	mux.HandleFunc("POST /api/v1/pool", s.addToPool)
	mux.HandleFunc("POST /api/v1/clients/import", s.importClients)
	mux.HandleFunc("GET /api/v1/imports/{id}/errors.csv", s.downloadImportErrorsCSV)
	mux.HandleFunc("GET /api/v1/call-list", s.callList)
	mux.HandleFunc("GET /api/v1/today", s.today)
	mux.HandleFunc("POST /api/v1/slices", s.importSnapshot)
}

func (s *Server) ready(w http.ResponseWriter) bool {
	if s.store == nil || s.pool == nil {
		writeError(w, http.StatusServiceUnavailable, "DB_UNAVAILABLE", "Database is not configured")
		return false
	}
	return true
}

func actorID(r *http.Request) string {
	if value := strings.TrimSpace(r.Header.Get("X-User-Id")); value != "" {
		return value
	}
	return demoOperatorID
}

func isAdmin(r *http.Request) bool {
	return strings.EqualFold(strings.TrimSpace(r.Header.Get("X-Role")), "admin")
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		log.Printf("encode response: %v", err)
	}
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"code": code, "message": message})
}

func parseLimit(r *http.Request) (int, int) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 || limit > 1000 {
		limit = 200
	}
	offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
	if offset < 0 {
		offset = 0
	}
	return limit, offset
}

func parseBool(value string) *bool {
	if value == "" {
		return nil
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return nil
	}
	return &parsed
}

func parseShare(value string) *float64 {
	if value == "" {
		return nil
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil || parsed < 0 || parsed > 100 || math.IsNaN(parsed) || math.IsInf(parsed, 0) {
		return nil
	}
	return &parsed
}

func (s *Server) listPeriods(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	periods, err := s.store.ListPeriods(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load periods")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": periods})
}

func (s *Server) listSlices(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	limit, offset := parseLimit(r)
	slices, total, err := s.store.ListSlices(r.Context(), limit, offset)
	if err != nil {
		log.Printf("list slices: %v", err)
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load slices")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"data": slices,
		"meta": map[string]int{"total": total, "limit": limit, "offset": offset},
	})
}

func (s *Server) listClients(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	limit, offset := parseLimit(r)
	query := r.URL.Query()
	filters := store.ListFilters{
		WorkOnly:   !isAdmin(r),
		PoolOnly:   query.Get("pool") == "true",
		PeriodCode: query.Get("period"),
		ExternalID: strings.TrimSpace(query.Get("external_id")),
		INN:        strings.TrimSpace(query.Get("inn")),
		Stage:      strings.TrimSpace(query.Get("stage")),
		Assigned:   strings.TrimSpace(query.Get("assigned")),
		UserID:     actorID(r),
		Tag:        strings.TrimSpace(query.Get("tag")),
		Contacted:  strings.TrimSpace(query.Get("contacted")),
		MinShare:   parseShare(query.Get("min_share")),
		Excluded:   parseBool(query.Get("excluded")),
		Inactive:   parseBool(query.Get("inactive")),
		Limit:      limit,
		Offset:     offset,
		Sort:       strings.TrimSpace(query.Get("sort")),
		Desc:       query.Get("order") == "desc",
	}
	clients, total, err := s.store.ListClients(r.Context(), filters)
	if err != nil {
		log.Printf("list clients: %v", err)
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load clients")
		return
	}
	if latest, err := s.store.LatestPeriod(r.Context()); err == nil {
		for i := range clients {
			s.store.MarkMissing(&clients[i], latest)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"data": clients,
		"meta": map[string]int{"total": total, "limit": limit, "offset": offset},
	})
}

func (s *Server) callList(w http.ResponseWriter, r *http.Request) {
	if !isAdmin(r) {
		writeError(w, 403, "FORBIDDEN", "Only administrators prepare call lists")
		return
	}
	if !s.ready(w) {
		return
	}
	limit, offset := parseLimit(r)
	q := r.URL.Query()
	period := strings.TrimSpace(q.Get("period"))
	periods, err := s.store.ListPeriods(r.Context())
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not load periods")
		return
	}
	if period == "" {
		period, err = s.store.LatestPeriod(r.Context())
		if err != nil {
			writeError(w, 500, "DB_ERROR", "Could not resolve period")
			return
		}
	}
	known := false
	for _, p := range periods {
		if p.Code == period {
			known = true
		}
	}
	if !known {
		writeError(w, 422, "UNKNOWN_PERIOD", "Select an available period")
		return
	}
	minimum := 0
	if q.Get("min_unsent") != "" {
		value, e := strconv.Atoi(q.Get("min_unsent"))
		if e != nil || value < 0 {
			writeError(w, 422, "INVALID_FILTER", "min_unsent must be a nonnegative integer")
			return
		}
		minimum = value
	}
	if q.Get("min_share") != "" && parseShare(q.Get("min_share")) == nil {
		writeError(w, 422, "INVALID_FILTER", "min_share must be between 0 and 100")
		return
	}
	contacted := q.Get("contacted")
	if contacted != "" && contacted != "yes" && contacted != "no" {
		writeError(w, 422, "INVALID_FILTER", "contacted must be yes or no")
		return
	}
	excluded, inactive := false, false
	filters := store.ListFilters{PeriodCode: period, MinUnsent: minimum, CallList: true, Stage: q.Get("stage"), Tag: q.Get("tag"), Contacted: contacted, MinShare: parseShare(q.Get("min_share")), Excluded: &excluded, Inactive: &inactive, Assigned: "free", Limit: limit, Offset: offset, Sort: "external_id"}
	clients, total, err := s.store.ListClients(r.Context(), filters)
	if err != nil {
		log.Printf("call list: %v", err)
		writeError(w, 500, "DB_ERROR", "Could not build call list")
		return
	}
	if clients == nil {
		clients = []store.Client{}
	}
	writeJSON(w, 200, map[string]any{"data": clients, "meta": map[string]any{"total": total, "returned": len(clients), "limit": limit, "offset": offset, "filters": map[string]any{"period": period, "min_unsent": minimum, "min_share": filters.MinShare, "contacted": contacted, "excluded": false, "inactive": false, "assigned": "free"}}})
}

func (s *Server) getClient(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	client, err := s.store.GetClient(r.Context(), r.PathValue("external_id"))
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "CLIENT_NOT_FOUND", "Client not found")
		return
	}
	if err != nil {
		log.Printf("get client: %v", err)
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load client")
		return
	}
	if !isAdmin(r) && !client.InPool && client.AssignedTo == "" {
		writeError(w, 403, "FORBIDDEN", "Client is outside the work pool")
		return
	}
	history, err := s.store.History(r.Context(), client.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load history")
		return
	}
	events, err := s.store.Events(r.Context(), client.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not load events")
		return
	}
	actions, err := s.store.Actions(r.Context(), client.ID)
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not load actions")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": client, "history": history, "events": events, "actions": actions})
}

func (s *Server) today(w http.ResponseWriter, r *http.Request) {
	if !s.ready(w) {
		return
	}
	limit, offset := parseLimit(r)
	clients, _, err := s.store.ListClients(r.Context(), store.ListFilters{Assigned: "mine", UserID: actorID(r), Limit: limit, Offset: offset, Sort: "external_id"})
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not load callbacks")
		return
	}
	now := time.Now().UTC().Truncate(24 * time.Hour)
	tasks := make([]map[string]any, 0)
	for _, client := range clients {
		events, e := s.store.Events(r.Context(), client.ID)
		if e != nil {
			writeError(w, 500, "DB_ERROR", "Could not load callbacks")
			return
		}
		for _, event := range events {
			if event.Type != "call" {
				continue
			}
			if event.CallbackOn != nil && !event.CallbackOn.After(now) {
				tasks = append(tasks, map[string]any{"client_external_id": client.ExternalID, "client_name": client.Name, "task_type": "callback_due", "due_date": event.CallbackOn.Format("2006-01-02")})
			}
			break
		}
	}
	writeJSON(w, 200, tasks)
}

func (s *Server) takeClient(w http.ResponseWriter, r *http.Request) {
	if !operatorAction(w, r) {
		return
	}
	if !s.ready(w) {
		return
	}
	client, err := s.store.Take(r.Context(), r.PathValue("external_id"), actorID(r))
	if errors.Is(err, store.ErrConflict) {
		current, _ := s.store.GetClient(r.Context(), r.PathValue("external_id"))
		message := "Client is already in progress"
		if current != nil && current.AssignedName != "" {
			message = "Client is already assigned to " + current.AssignedName
		}
		writeError(w, http.StatusConflict, "ALREADY_TAKEN", message)
		return
	}
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "CLIENT_NOT_FOUND", "Client not found")
		return
	}
	if err != nil {
		log.Printf("take client: %v", err)
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not take client")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": client})
}

func (s *Server) takeOverClient(w http.ResponseWriter, r *http.Request) {
	if !operatorAction(w, r) {
		return
	}
	if !s.ready(w) {
		return
	}
	if r.ContentLength != 0 {
		var empty struct{}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&empty); err != nil {
			writeError(w, 400, "INVALID_BODY", "Take-over accepts no target user")
			return
		}
	}
	client, err := s.store.TakeOver(r.Context(), r.PathValue("external_id"), actorID(r))
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, 404, "CLIENT_NOT_FOUND", "Assigned active client not found")
		return
	}
	if err != nil {
		writeError(w, 500, "DB_ERROR", "Could not take over client")
		return
	}
	writeJSON(w, 200, map[string]any{"data": client})
}

func operatorAction(w http.ResponseWriter, r *http.Request) bool {
	if isAdmin(r) || actorID(r) == demoAdminID {
		writeError(w, 403, "OPERATOR_REQUIRED", "Administrator prepares lists; operators take clients themselves")
		return false
	}
	return true
}

func (s *Server) addEvent(w http.ResponseWriter, r *http.Request) {
	if !operatorAction(w, r) {
		return
	}
	if !s.ready(w) {
		return
	}
	var payload struct {
		PromiseLabel string `json:"promise_label"`
		EventType    string `json:"event_type"`
		CallbackOn   string `json:"callback_on"`
		PeriodCode   string `json:"period_code"`
		Result       string `json:"result"`
		Comment      string `json:"comment"`
		Stage        string `json:"stage"`
		PromisedAt   string `json:"promised_at"`
		EventDate    string `json:"event_date"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "Invalid JSON body")
		return
	}
	switch payload.EventType {
	case "call", "email", "comment":
	default:
		writeError(w, http.StatusUnprocessableEntity, "INVALID_EVENT_TYPE", "event_type must be call, email or comment")
		return
	}
	input := store.EventInput{PromiseLabel: payload.PromiseLabel, Type: payload.EventType, Result: payload.Result, Comment: payload.Comment, Stage: payload.Stage, PeriodCode: payload.PeriodCode}
	if payload.CallbackOn != "" {
		value, err := time.Parse("2006-01-02", payload.CallbackOn)
		if err != nil {
			writeError(w, 422, "INVALID_CALLBACK_DATE", "callback_on must be YYYY-MM-DD")
			return
		}
		input.CallbackOn = &value
	}
	if payload.PromisedAt != "" {
		value, err := time.Parse("2006-01-02", payload.PromisedAt)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_PROMISE_DATE", "promised_at must be YYYY-MM-DD")
			return
		}
		input.PromisedAt = &value
	}
	if payload.EventDate != "" {
		value, err := time.Parse("2006-01-02", payload.EventDate)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_EVENT_DATE", "event_date must be YYYY-MM-DD")
			return
		}
		input.Date = value
	}
	if err := store.ValidateEvent(input); err != nil {
		writeError(w, 422, "INVALID_EVENT", err.Error())
		return
	}
	event, err := s.store.AddEvent(r.Context(), r.PathValue("external_id"), actorID(r), input)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, 404, "CLIENT_NOT_FOUND", "Client not found")
		return
	}
	if errors.Is(err, store.ErrForbidden) {
		writeError(w, 403, "FORBIDDEN", "Only the assigned operator can record interaction")
		return
	}
	if errors.Is(err, store.ErrInvalidEvent) {
		writeError(w, 422, "INVALID_EVENT", "Unknown period or invalid event")
		return
	}
	if err != nil {
		log.Printf("add event: %v", err)
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "Could not save event")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"data": event})
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	status := "disabled"
	code := http.StatusOK
	if s.pool != nil {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := s.pool.Ping(ctx); err != nil {
			status = "unavailable"
			code = http.StatusServiceUnavailable
		} else {
			status = "ok"
		}
	}
	serviceStatus := "ok"
	if code != http.StatusOK {
		serviceStatus = "degraded"
	}
	writeJSON(w, code, map[string]string{"status": serviceStatus, "service": "backend", "db": status})
}
