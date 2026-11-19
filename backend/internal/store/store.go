package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNotFound = errors.New("not found")
	ErrConflict = errors.New("conflict")
)

type Store struct {
	pool *pgxpool.Pool
}

func New(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

func (s *Store) Pool() *pgxpool.Pool {
	return s.pool
}

func (s *Store) ListPeriods(ctx context.Context) ([]Period, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, label, year, quarter
		FROM report_periods
		ORDER BY year, quarter`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var periods []Period
	for rows.Next() {
		var item Period
		if err := rows.Scan(&item.ID, &item.Code, &item.Year, &item.Quarter); err != nil {
			return nil, err
		}
		item.Label = item.Code
		periods = append(periods, item)
	}
	return periods, rows.Err()
}

func (s *Store) LatestPeriod(ctx context.Context) (string, error) {
	var code string
	err := s.pool.QueryRow(ctx, `
		SELECT rp.label
		FROM slices s
		JOIN report_periods rp ON rp.id = s.period_id
		ORDER BY s.slice_date DESC, s.id DESC
		LIMIT 1`).Scan(&code)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", nil
	}
	return code, err
}

func (s *Store) ListClients(ctx context.Context, f ListFilters) ([]Client, int, error) {
	if f.Limit <= 0 || f.Limit > 1000 {
		f.Limit = 200
	}
	args := make([]any, 0, 8)
	where := []string{"1=1"}

	if f.ExternalID != "" {
		args = append(args, f.ExternalID)
		where = append(where, fmt.Sprintf("c.external_id = $%d", len(args)))
	}
	if f.INN != "" {
		args = append(args, f.INN)
		where = append(where, fmt.Sprintf("c.inn = $%d", len(args)))
	}
	if f.Stage != "" {
		args = append(args, f.Stage)
		where = append(where, fmt.Sprintf("c.stage = $%d", len(args)))
	}
	if f.Excluded != nil {
		args = append(args, *f.Excluded)
		where = append(where, fmt.Sprintf("c.excluded = $%d", len(args)))
	}
	if f.Inactive != nil {
		args = append(args, *f.Inactive)
		where = append(where, fmt.Sprintf("c.inactive = $%d", len(args)))
	}
	if f.Assigned == "free" {
		where = append(where, "c.assigned_to IS NULL")
	} else if f.Assigned == "assigned" {
		where = append(where, "c.assigned_to IS NOT NULL")
	} else if f.Assigned == "mine" && f.UserID != "" {
		args = append(args, f.UserID)
		where = append(where, fmt.Sprintf("c.assigned_to = $%d::uuid", len(args)))
	}
	if f.Tag != "" {
		args = append(args, f.Tag)
		where = append(where, fmt.Sprintf("EXISTS (SELECT 1 FROM client_tags ct WHERE ct.client_id = c.id AND ct.tag = $%d)", len(args)))
	}
	if f.Contacted == "yes" {
		where = append(where, "EXISTS (SELECT 1 FROM client_events ce WHERE ce.client_id = c.id AND ce.event_type = 'call')")
	} else if f.Contacted == "no" {
		where = append(where, "NOT EXISTS (SELECT 1 FROM client_events ce WHERE ce.client_id = c.id AND ce.event_type = 'call')")
	}
	if f.MinShare != nil {
		args = append(args, *f.MinShare)
		where = append(where, fmt.Sprintf(`COALESCE(latest.total_docs, prev.total_docs) > 0
			AND (latest.not_sent_docs::numeric / COALESCE(latest.total_docs, prev.total_docs)) * 100 >= $%d`, len(args)))
	}

	sortColumn := "c.name"
	switch f.Sort {
	case "external_id":
		sortColumn = "c.external_id"
	case "stage":
		sortColumn = "c.stage"
	case "promised_at":
		sortColumn = "c.promised_at"
	case "updated_at":
		sortColumn = "c.updated_at"
	case "share":
		sortColumn = "(latest.not_sent_docs::numeric / NULLIF(COALESCE(latest.total_docs, prev.total_docs), 0))"
	case "unsent":
		sortColumn = "latest.not_sent_docs"
	}
	direction := "ASC"
	if f.Desc {
		direction = "DESC"
	}
	args = append(args, f.Limit, f.Offset)

	query := fmt.Sprintf(`
		SELECT c.id::text, c.external_id, c.name, COALESCE(c.inn, ''), COALESCE(c.kpp, ''),
			c.stage, COALESCE(c.assigned_to::text, ''), COALESCE(u.username, ''),
			c.excluded, c.inactive, COALESCE(c.excluded_reason, ''),
			c.promised_at, c.last_contact_at,
			COALESCE(c.contact_name, ''), COALESCE(c.contact_phone, ''), COALESCE(c.contact_email, ''),
			COALESCE((SELECT array_agg(ct.tag ORDER BY ct.tag) FROM client_tags ct WHERE ct.client_id = c.id), '{}'),
			latest.period_code, latest.slice_date, latest.total_docs, latest.not_sent_docs,
			prev.period_code, prev.slice_date, prev.total_docs, prev.not_sent_docs,
			COUNT(*) OVER() AS total
		FROM clients c
		LEFT JOIN users u ON u.id = c.assigned_to
		LEFT JOIN LATERAL (
			SELECT rp.label AS period_code, s.slice_date, sr.total_docs, sr.not_sent_docs
			FROM slice_records sr
			JOIN slices s ON s.id = sr.slice_id
			JOIN report_periods rp ON rp.id = s.period_id
			WHERE sr.client_id = c.id
			ORDER BY s.slice_date DESC, s.id DESC
			LIMIT 1
		) latest ON TRUE
		LEFT JOIN LATERAL (
			SELECT rp.label AS period_code, s.slice_date, sr.total_docs, sr.not_sent_docs
			FROM slice_records sr
			JOIN slices s ON s.id = sr.slice_id
			JOIN report_periods rp ON rp.id = s.period_id
			WHERE sr.client_id = c.id
			ORDER BY s.slice_date DESC, s.id DESC
			OFFSET 1 LIMIT 1
		) prev ON TRUE
		WHERE %s
		ORDER BY %s %s NULLS LAST, c.name
		LIMIT $%d OFFSET $%d`,
		strings.Join(where, " AND "), sortColumn, direction, len(args)-1, len(args))

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	results := make([]Client, 0)
	total := 0
	for rows.Next() {
		client, rowTotal, err := scanClient(rows)
		if err != nil {
			return nil, 0, err
		}
		total = rowTotal
		results = append(results, client)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	return results, total, nil
}

func scanClient(row pgx.Row) (Client, int, error) {
	var (
		client                   Client
		promised, lastContact    pgtype.Date
		latestPeriod, prevPeriod pgtype.Text
		latestDate, prevDate     pgtype.Date
		latestTotal, prevTotal   pgtype.Int4
		latestUnsent, prevUnsent pgtype.Int4
		total                    int64
	)
	err := row.Scan(
		&client.ID, &client.ExternalID, &client.Name, &client.INN, &client.KPP,
		&client.Stage, &client.AssignedTo, &client.AssignedName,
		&client.Excluded, &client.Inactive, &client.ExcludedReason,
		&promised, &lastContact,
		&client.ContactName, &client.ContactPhone, &client.ContactEmail,
		&client.Tags,
		&latestPeriod, &latestDate, &latestTotal, &latestUnsent,
		&prevPeriod, &prevDate, &prevTotal, &prevUnsent,
		&total,
	)
	if err != nil {
		return client, 0, err
	}
	client.Active = !client.Inactive
	client.PromisedAt = datePtr(promised)
	client.LastContactAt = datePtr(lastContact)
	if latestPeriod.Valid {
		client.Latest = &Record{
			PeriodCode:  latestPeriod.String,
			SliceDate:   dateValue(latestDate),
			TotalDocs:   intPtr(latestTotal),
			NotSentDocs: intValue(latestUnsent),
		}
		client.Latest.Share = share(client.Latest.TotalDocs, client.Latest.NotSentDocs)
	}
	if prevPeriod.Valid {
		client.Previous = &Record{
			PeriodCode:  prevPeriod.String,
			SliceDate:   dateValue(prevDate),
			TotalDocs:   intPtr(prevTotal),
			NotSentDocs: intValue(prevUnsent),
		}
		client.Previous.Share = share(client.Previous.TotalDocs, client.Previous.NotSentDocs)
	}
	if client.Latest != nil && client.Latest.TotalDocs == nil && client.Previous != nil {
		client.Latest.TotalDocs = client.Previous.TotalDocs
		client.Latest.Inherited = true
		client.Latest.Share = share(client.Latest.TotalDocs, client.Latest.NotSentDocs)
	}
	return client, int(total), nil
}

func (s *Store) MarkMissing(client *Client, latestPeriod string) {
	if client == nil {
		return
	}
	client.Missing = client.Active && (latestPeriod == "" || client.Latest == nil || client.Latest.PeriodCode != latestPeriod)
}

func (s *Store) markMissing(client *Client, latestPeriod string) {
	s.MarkMissing(client, latestPeriod)
}

func (s *Store) GetClient(ctx context.Context, externalID string) (*Client, error) {
	clients, _, err := s.ListClients(ctx, ListFilters{ExternalID: externalID, Limit: 1})
	if err != nil {
		return nil, err
	}
	if len(clients) == 0 {
		return nil, ErrNotFound
	}
	latest, err := s.LatestPeriod(ctx)
	if err != nil {
		return nil, err
	}
	client := &clients[0]
	s.markMissing(client, latest)
	history, err := s.History(ctx, client.ID)
	if err != nil {
		return nil, err
	}
	if len(history) > 0 {
		client.Latest = &history[len(history)-1]
		if len(history) > 1 {
			client.Previous = &history[len(history)-2]
		}
		s.markMissing(client, latest)
	}
	return client, nil
}

func (s *Store) History(ctx context.Context, clientID string) ([]Record, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT rp.label, s.slice_date, sr.total_docs, sr.not_sent_docs
		FROM slice_records sr
		JOIN slices s ON s.id = sr.slice_id
		JOIN report_periods rp ON rp.id = s.period_id
		WHERE sr.client_id = $1::uuid
		ORDER BY s.slice_date, s.id`, clientID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var records []Record
	for rows.Next() {
		var (
			record Record
			total  pgtype.Int4
		)
		if err := rows.Scan(&record.PeriodCode, &record.SliceDate, &total, &record.NotSentDocs); err != nil {
			return nil, err
		}
		record.TotalDocs = intPtr(total)
		record.Share = share(record.TotalDocs, record.NotSentDocs)
		if len(records) > 0 && record.TotalDocs == nil {
			record.TotalDocs = records[len(records)-1].TotalDocs
			record.Inherited = true
			record.Share = share(record.TotalDocs, record.NotSentDocs)
		}
		records = append(records, record)
	}
	return records, rows.Err()
}

func (s *Store) Events(ctx context.Context, clientID string) ([]Event, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT e.id::text, e.client_id::text, e.event_type, e.event_date,
			COALESCE(e.result, ''), e.promised_at, COALESCE(e.comment, ''),
			COALESCE(e.author_id::text, ''), COALESCE(u.username, ''), e.created_at
		FROM client_events e
		LEFT JOIN users u ON u.id = e.author_id
		WHERE e.client_id = $1::uuid
		ORDER BY e.event_date DESC, e.created_at DESC`, clientID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []Event
	for rows.Next() {
		var (
			event    Event
			promised pgtype.Date
		)
		if err := rows.Scan(&event.ID, &event.ClientID, &event.Type, &event.Date,
			&event.Result, &promised, &event.Comment, &event.AuthorID, &event.AuthorName, &event.CreatedAt); err != nil {
			return nil, err
		}
		event.PromisedAt = datePtr(promised)
		events = append(events, event)
	}
	return events, rows.Err()
}

type EventInput struct {
	Type       string
	Result     string
	Comment    string
	Stage      string
	PromisedAt *time.Time
	Date       time.Time
}

func (s *Store) AddEvent(ctx context.Context, externalID, userID string, input EventInput) (*Event, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID string
	if err := tx.QueryRow(ctx, "SELECT id::text FROM clients WHERE external_id = $1", externalID).Scan(&clientID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}

	date := input.Date
	if date.IsZero() {
		date = time.Now()
	}
	var promised any
	if input.PromisedAt != nil {
		promised = *input.PromisedAt
	}
	var author any
	if userID != "" {
		author = userID
	}
	var eventID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO client_events (client_id, event_type, event_date, result, promised_at, comment, author_id)
		VALUES ($1::uuid, $2, $3::date, NULLIF($4, ''), $5::date, NULLIF($6, ''), $7::uuid)
		RETURNING id::text`,
		clientID, input.Type, date, input.Result, promised, input.Comment, author).Scan(&eventID); err != nil {
		return nil, err
	}

	stage := input.Stage
	if input.Result == "Отказ" {
		stage = "Закрыт"
	}
	if _, err := tx.Exec(ctx, `
		UPDATE clients
		SET last_contact_at = $1::date,
			stage = COALESCE(NULLIF($2, ''), stage),
			promised_at = COALESCE($3::date, promised_at),
			updated_at = NOW()
		WHERE id = $4::uuid`, date, stage, promised, clientID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	events, err := s.Events(ctx, clientID)
	if err != nil {
		return nil, err
	}
	for _, event := range events {
		if event.ID == eventID {
			return &event, nil
		}
	}
	return &Event{ID: eventID}, nil
}

func (s *Store) Take(ctx context.Context, externalID, userID string) (*Client, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID string
	if err := tx.QueryRow(ctx, `
		UPDATE clients
		SET assigned_to = $1::uuid, stage = 'В работе', updated_at = NOW()
		WHERE external_id = $2 AND assigned_to IS NULL AND stage <> 'Закрыт'
		RETURNING id::text`, userID, externalID).Scan(&clientID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrConflict
		}
		return nil, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO client_events (client_id, event_type, event_date, comment, author_id)
		VALUES ($1::uuid, 'system', CURRENT_DATE, 'Клиент взят в работу', NULLIF($2, '')::uuid)`,
		clientID, userID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetClient(ctx, externalID)
}

func (s *Store) Reassign(ctx context.Context, externalID, userID, actorID string) (*Client, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID string
	if err := tx.QueryRow(ctx, `
		UPDATE clients
		SET assigned_to = $1::uuid, stage = 'В работе', updated_at = NOW()
		WHERE external_id = $2 AND stage <> 'Закрыт'
		RETURNING id::text`, userID, externalID).Scan(&clientID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO client_events (client_id, event_type, event_date, comment, author_id)
		VALUES ($1::uuid, 'system', CURRENT_DATE, 'Клиент переназначен', NULLIF($2, '')::uuid)`,
		clientID, actorID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetClient(ctx, externalID)
}

func share(total *int, unsent int) *float64 {
	if total == nil || *total <= 0 {
		return nil
	}
	value := float64(unsent) / float64(*total) * 100
	return &value
}

func intValue(value pgtype.Int4) int {
	if !value.Valid {
		return 0
	}
	return int(value.Int32)
}

func intPtr(value pgtype.Int4) *int {
	if !value.Valid {
		return nil
	}
	result := int(value.Int32)
	return &result
}

func dateValue(value pgtype.Date) time.Time {
	if !value.Valid {
		return time.Time{}
	}
	return value.Time
}

func datePtr(value pgtype.Date) *time.Time {
	if !value.Valid {
		return nil
	}
	result := value.Time
	return &result
}
