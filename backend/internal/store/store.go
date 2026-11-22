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
	ErrNotFound     = errors.New("not found")
	ErrConflict     = errors.New("conflict")
	ErrForbidden    = errors.New("forbidden")
	ErrInvalidEvent = errors.New("invalid event")
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
		ORDER BY rp.year DESC, rp.quarter DESC, s.slice_date DESC, s.id DESC
		LIMIT 1`).Scan(&code)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", nil
	}
	return code, err
}

func (s *Store) ListClients(ctx context.Context, f ListFilters) ([]Client, int, error) {
	if f.Limit <= 0 || f.Limit > 5000 {
		f.Limit = 200
	}
	args := make([]any, 0, 8)
	where := []string{"1=1"}

	if len(f.ExternalIDs) > 0 {
		args = append(args, f.ExternalIDs)
		where = append(where, fmt.Sprintf("c.external_id=ANY($%d::text[])", len(args)))
	}
	if f.WorkOnly {
		where = append(where, "(c.in_pool OR c.assigned_to IS NOT NULL)")
	}
	if f.PoolOnly {
		where = append(where, "c.in_pool")
	}
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
	if f.Contacted == "yes" || f.Contacted == "no" {
		scope := ""
		if f.PeriodCode != "" {
			args = append(args, f.PeriodCode)
			p := fmt.Sprintf("$%d", len(args))
			if f.Contacted == "yes" {
				scope = " AND ce.period_code=" + p
			} else {
				scope = " AND (ce.period_code=" + p + " OR ce.period_code IS NULL)"
			}
		}
		clause := "EXISTS (SELECT 1 FROM client_events ce WHERE ce.client_id=c.id AND ce.event_type='call'" + scope + ")"
		if f.Contacted == "no" {
			clause = "NOT " + clause
		}
		where = append(where, clause)
	}
	if f.MinShare != nil {
		args = append(args, *f.MinShare)
		where = append(where, fmt.Sprintf(`COALESCE(latest.total_docs, prev.total_docs) > 0
			AND (latest.not_sent_docs::numeric / COALESCE(latest.total_docs, prev.total_docs)) * 100 >= $%d`, len(args)))
	}

	latestScope, prevScope, prevOffset := "", "", "OFFSET 1"
	if f.PeriodCode != "" {
		args = append(args, f.PeriodCode)
		parameter := fmt.Sprintf("$%d", len(args))
		latestScope = " AND rp.label=" + parameter
		prevScope = " AND rp.label=" + parameter + " AND (s.slice_date,s.id)<(latest.slice_date,latest.slice_id)"
		prevOffset = ""
	}
	if f.MinUnsent > 0 {
		args = append(args, f.MinUnsent)
		where = append(where, fmt.Sprintf("latest.not_sent_docs >= $%d", len(args)))
	}
	if f.CallList {
		where = append(where, "c.stage <> 'Закрыт' AND latest.not_sent_docs > 0 AND latest.slice_date=(SELECT max(s2.slice_date) FROM slices s2 JOIN report_periods p2 ON p2.id=s2.period_id WHERE p2.label=latest.period_code) AND (COALESCE(latest.total_docs,prev.total_docs)>0 AND latest.not_sent_docs::numeric/COALESCE(latest.total_docs,prev.total_docs)>=0.05 OR c.joined_on BETWEEN CURRENT_DATE - INTERVAL '6 months' AND CURRENT_DATE OR EXISTS(SELECT 1 FROM client_tags nt WHERE nt.client_id=c.id AND nt.tag IN ('Новичок','newcomer')))")
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
			c.promised_at, c.last_contact_at, c.in_pool, c.joined_on,
			COALESCE(c.contact_details, ''), COALESCE(c.contact_name, ''), COALESCE(c.contact_phone, ''), COALESCE(c.contact_email, ''),
			COALESCE((SELECT array_agg(ct.tag ORDER BY ct.tag) FROM client_tags ct WHERE ct.client_id = c.id), '{}'),
			latest.period_code, latest.slice_date, latest.total_docs, latest.not_sent_docs, COALESCE(latest.inherited,false),
			prev.period_code, prev.slice_date, prev.total_docs, prev.not_sent_docs, COALESCE(prev.inherited,false),
			latest.slice_date IS DISTINCT FROM (SELECT max(sd.slice_date) FROM slices sd JOIN report_periods pd ON pd.id=sd.period_id WHERE pd.label=latest.period_code),
 COUNT(*) OVER() AS total
		FROM clients c
		LEFT JOIN users u ON u.id = c.assigned_to
		LEFT JOIN LATERAL (
			SELECT rp.label AS period_code, s.id AS slice_id, s.slice_date, COALESCE(sr.total_docs,(SELECT r2.total_docs FROM slice_records r2 JOIN slices s2 ON s2.id=r2.slice_id WHERE r2.client_id=c.id AND s2.period_id=s.period_id AND s2.slice_date<=s.slice_date AND r2.total_docs IS NOT NULL ORDER BY s2.slice_date DESC,s2.id DESC LIMIT 1)) AS total_docs, sr.not_sent_docs, (sr.total_source_record_id IS NOT NULL OR sr.total_docs IS NULL) AS inherited
            FROM slice_records sr
			JOIN slices s ON s.id = sr.slice_id
			JOIN report_periods rp ON rp.id = s.period_id
			WHERE sr.client_id = c.id %s
			ORDER BY rp.year DESC, rp.quarter DESC, s.slice_date DESC, s.id DESC
			LIMIT 1
		) latest ON TRUE
		LEFT JOIN LATERAL (
			SELECT rp.label AS period_code, s.id AS slice_id, s.slice_date, COALESCE(sr.total_docs,(SELECT r2.total_docs FROM slice_records r2 JOIN slices s2 ON s2.id=r2.slice_id WHERE r2.client_id=c.id AND s2.period_id=s.period_id AND s2.slice_date<=s.slice_date AND r2.total_docs IS NOT NULL ORDER BY s2.slice_date DESC,s2.id DESC LIMIT 1)) AS total_docs, sr.not_sent_docs, (sr.total_source_record_id IS NOT NULL OR sr.total_docs IS NULL) AS inherited
            FROM slice_records sr
			JOIN slices s ON s.id = sr.slice_id
			JOIN report_periods rp ON rp.id = s.period_id
			WHERE sr.client_id = c.id %s
			ORDER BY rp.year DESC, rp.quarter DESC, s.slice_date DESC, s.id DESC
			%s LIMIT 1
		) prev ON TRUE
		WHERE %s
		ORDER BY %s %s NULLS LAST, c.name
		LIMIT $%d OFFSET $%d`,
		latestScope, prevScope, prevOffset, strings.Join(where, " AND "), sortColumn, direction, len(args)-1, len(args))

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
		joined                         pgtype.Date
		client                         Client
		promised, lastContact          pgtype.Date
		latestPeriod, prevPeriod       pgtype.Text
		latestDate, prevDate           pgtype.Date
		latestTotal, prevTotal         pgtype.Int4
		latestUnsent, prevUnsent       pgtype.Int4
		total                          int64
		latestInherited, prevInherited bool
	)
	err := row.Scan(
		&client.ID, &client.ExternalID, &client.Name, &client.INN, &client.KPP,
		&client.Stage, &client.AssignedTo, &client.AssignedName,
		&client.Excluded, &client.Inactive, &client.ExcludedReason,
		&promised, &lastContact, &client.InPool, &joined,
		&client.ContactDetails, &client.ContactName, &client.ContactPhone, &client.ContactEmail,
		&client.Tags,
		&latestPeriod, &latestDate, &latestTotal, &latestUnsent, &latestInherited,
		&prevPeriod, &prevDate, &prevTotal, &prevUnsent, &prevInherited, &client.Missing,
		&total,
	)
	if err != nil {
		return client, 0, err
	}
	client.JoinedOn = datePtr(joined)
	client.Active = !client.Inactive
	client.PromisedAt = datePtr(promised)
	client.LastContactAt = datePtr(lastContact)
	if latestPeriod.Valid {
		client.Latest = &Record{
			PeriodCode:  latestPeriod.String,
			SliceDate:   dateValue(latestDate),
			TotalDocs:   intPtr(latestTotal),
			NotSentDocs: intValue(latestUnsent),
			Inherited:   latestInherited,
		}
		client.Latest.Share = share(client.Latest.TotalDocs, client.Latest.NotSentDocs)
	}
	if prevPeriod.Valid {
		client.Previous = &Record{
			PeriodCode:  prevPeriod.String,
			SliceDate:   dateValue(prevDate),
			TotalDocs:   intPtr(prevTotal),
			NotSentDocs: intValue(prevUnsent),
			Inherited:   prevInherited,
		}
		client.Previous.Share = share(client.Previous.TotalDocs, client.Previous.NotSentDocs)
	}
	if client.Latest != nil && client.Latest.TotalDocs == nil && client.Previous != nil && client.Latest.PeriodCode == client.Previous.PeriodCode {
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
	client.Missing = client.Missing || client.Active && (latestPeriod == "" || client.Latest == nil || client.Latest.PeriodCode != latestPeriod)
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
		client.Previous = nil
		if len(history) > 1 && history[len(history)-2].PeriodCode == client.Latest.PeriodCode {
			client.Previous = &history[len(history)-2]
		}
		s.markMissing(client, latest)
	}
	return client, nil
}

func (s *Store) History(ctx context.Context, clientID string) ([]Record, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT rp.label, s.slice_date, sr.total_docs, sr.not_sent_docs, sr.total_source_record_id IS NOT NULL
		FROM slice_records sr
		JOIN slices s ON s.id = sr.slice_id
		JOIN report_periods rp ON rp.id = s.period_id
		WHERE sr.client_id = $1::uuid
		ORDER BY rp.year, rp.quarter, s.slice_date, s.id`, clientID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	records := make([]Record, 0)
	for rows.Next() {
		var (
			record Record
			total  pgtype.Int4
		)
		if err := rows.Scan(&record.PeriodCode, &record.SliceDate, &total, &record.NotSentDocs, &record.Inherited); err != nil {
			return nil, err
		}
		record.TotalDocs = intPtr(total)
		record.Share = share(record.TotalDocs, record.NotSentDocs)
		if len(records) > 0 && record.TotalDocs == nil && records[len(records)-1].PeriodCode == record.PeriodCode {
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
			COALESCE(e.author_id::text, ''), COALESCE(u.username, ''), e.created_at, e.callback_on, COALESCE(e.period_code, ''), COALESCE(e.promise_label, '')
		FROM client_events e
		LEFT JOIN users u ON u.id = e.author_id
		WHERE e.client_id = $1::uuid
		ORDER BY e.event_date DESC, e.created_at DESC`, clientID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	events := make([]Event, 0)
	for rows.Next() {
		var (
			event    Event
			promised pgtype.Date
			callback pgtype.Date
		)
		if err := rows.Scan(&event.ID, &event.ClientID, &event.Type, &event.Date,
			&event.Result, &promised, &event.Comment, &event.AuthorID, &event.AuthorName, &event.CreatedAt, &callback, &event.PeriodCode, &event.PromiseLabel); err != nil {
			return nil, err
		}
		event.PromisedAt = datePtr(promised)
		event.CallbackOn = datePtr(callback)
		events = append(events, event)
	}
	return events, rows.Err()
}

type EventInput struct {
	PromiseLabel string
	CallbackOn   *time.Time
	PeriodCode   string
	Type         string
	Result       string
	Comment      string
	Stage        string
	PromisedAt   *time.Time
	Date         time.Time
}

func (s *Store) AddEvent(ctx context.Context, externalID, userID string, input EventInput) (*Event, error) {
	if err := ValidateEvent(input); err != nil {
		return nil, err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID, ownerID string
	var operator bool
	if err := tx.QueryRow(ctx, `SELECT id::text, COALESCE(assigned_to::text, ''), EXISTS(SELECT 1 FROM users WHERE id=$2::uuid AND role='operator') FROM clients WHERE external_id=$1 FOR UPDATE`, externalID, userID).Scan(&clientID, &ownerID, &operator); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}

	if !operator || ownerID != userID {
		return nil, ErrForbidden
	}
	if input.PeriodCode != "" {
		var exists bool
		if err := tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM report_periods WHERE label=$1)", input.PeriodCode).Scan(&exists); err != nil {
			return nil, err
		}
		if !exists {
			return nil, ErrInvalidEvent
		}
	}
	date := input.Date
	if date.IsZero() {
		date = time.Now()
	}
	var promised any
	if input.PromisedAt != nil {
		promised = *input.PromisedAt
	}
	var callback any
	if input.CallbackOn != nil {
		callback = *input.CallbackOn
	}
	var author any
	if userID != "" {
		author = userID
	}
	var eventID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO client_events (client_id, event_type, event_date, result, promised_at, comment, author_id, callback_on, period_code, promise_label)
		VALUES ($1::uuid, $2, $3::date, NULLIF($4, ''), $5::date, NULLIF($6, ''), $7::uuid, $8::date, NULLIF($9,''),NULLIF($10,''))
		RETURNING id::text`,
		clientID, input.Type, date, input.Result, promised, input.Comment, author, callback, input.PeriodCode, input.PromiseLabel).Scan(&eventID); err != nil {
		return nil, err
	}

	if _, err := tx.Exec(ctx, `
		UPDATE clients
		SET last_contact_at = CASE WHEN $2 IN ('call','email') THEN GREATEST($1::date,last_contact_at) ELSE last_contact_at END,
			promised_at = CASE WHEN $3::date IS NOT NULL AND $1::date>=COALESCE(last_contact_at,$1::date) THEN $3::date ELSE promised_at END,
			updated_at = NOW()
		WHERE id = $4::uuid`, date, input.Type, promised, clientID); err != nil {
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
	period, err := s.LatestPeriod(ctx)
	if err != nil {
		return nil, err
	}
	no := false
	candidates, _, err := s.ListClients(ctx, ListFilters{ExternalID: externalID, PeriodCode: period, CallList: true, Assigned: "free", Excluded: &no, Inactive: &no, Limit: 1})
	if err != nil {
		return nil, err
	}
	if len(candidates) == 0 {
		return nil, ErrConflict
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID string
	if err := tx.QueryRow(ctx, `
		UPDATE clients
		SET assigned_to = $1::uuid, in_pool=false, stage = 'В работе', updated_at = NOW()
		WHERE external_id = $2 AND in_pool AND assigned_to IS NULL AND stage <> 'Закрыт' AND NOT excluded AND NOT inactive
 AND EXISTS(SELECT 1 FROM users WHERE id=$1::uuid AND role='operator')
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

func (s *Store) TakeOver(ctx context.Context, externalID, userID string) (*Client, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var clientID string
	if err := tx.QueryRow(ctx, `
		UPDATE clients
		SET assigned_to = $1::uuid, in_pool=false, stage = 'В работе', updated_at = NOW()
		WHERE external_id = $2 AND assigned_to IS NOT NULL AND stage <> 'Закрыт' AND NOT excluded AND NOT inactive
 AND EXISTS(SELECT 1 FROM users WHERE id=$1::uuid AND role='operator')
		RETURNING id::text`, userID, externalID).Scan(&clientID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO client_events (client_id, event_type, event_date, comment, author_id)
		VALUES ($1::uuid, 'system', CURRENT_DATE, 'Клиент переназначен', NULLIF($2, '')::uuid)`,
		clientID, userID); err != nil {
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
