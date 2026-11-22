package store

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5"
	"strings"
	"time"
)

// Transfer and release are explicit operator actions. A row lock serializes them
// with contact updates, so a former owner cannot write after a transfer.
func (s *Store) Transfer(ctx context.Context, externalID, actor, target string) (*Client, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	var id, owner string
	err = tx.QueryRow(ctx, `SELECT id::text,COALESCE(assigned_to::text,'') FROM clients WHERE external_id=$1 AND NOT inactive AND NOT excluded AND stage<>'Закрыт' FOR UPDATE`, externalID).Scan(&id, &owner)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	if owner != actor {
		return nil, ErrForbidden
	}
	var operator bool
	err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM users WHERE id=$1::uuid AND role='operator')`, actor).Scan(&operator)
	if err != nil {
		return nil, err
	}
	if !operator {
		return nil, ErrForbidden
	}
	if target != "" {
		err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM users WHERE id=$1::uuid AND role='operator')`, target).Scan(&operator)
		if err != nil {
			return nil, err
		}
		if !operator {
			return nil, ErrForbidden
		}
	}
	var assigned any
	if target != "" {
		assigned = target
	}
	_, err = tx.Exec(ctx, `UPDATE clients SET assigned_to=$1::uuid,in_pool=($1::uuid IS NULL),stage=CASE WHEN $1::uuid IS NULL THEN 'Не в работе' ELSE 'В работе' END,updated_at=now() WHERE id=$2::uuid`, assigned, id)
	if err != nil {
		return nil, err
	}
	_, err = tx.Exec(ctx, `INSERT INTO client_events(client_id,event_type,event_date,comment,author_id) VALUES($1::uuid,'system',CURRENT_DATE,$2,$3::uuid)`, id, "Ответственный: "+owner+" -> "+target, actor)
	if err != nil {
		return nil, err
	}
	if err = tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetClient(ctx, externalID)
}

func (s *Store) AddToPool(ctx context.Context, ids []string, period string, actor string) (int, error) {
	no := false
	candidates, _, err := s.ListClients(ctx, ListFilters{ExternalIDs: ids, PeriodCode: period, CallList: true, Assigned: "free", Excluded: &no, Inactive: &no, Limit: 5000})
	if err != nil {
		return 0, err
	}
	allowed := map[string]bool{}
	for _, c := range candidates {
		allowed[c.ExternalID] = true
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)
	count := 0
	seen := map[string]bool{}
	for _, id := range ids {
		if seen[id] || !allowed[id] {
			continue
		}
		seen[id] = true
		var clientID string
		err = tx.QueryRow(ctx, `UPDATE clients SET in_pool=true,updated_at=now() WHERE external_id=$1 AND assigned_to IS NULL AND NOT in_pool AND NOT inactive AND NOT excluded AND stage<>'Закрыт' RETURNING id::text`, id).Scan(&clientID)
		if errors.Is(err, pgx.ErrNoRows) {
			continue
		}
		if err != nil {
			return 0, err
		}
		_, err = tx.Exec(ctx, `INSERT INTO client_events(client_id,event_type,event_date,comment,author_id) VALUES($1::uuid,'system',CURRENT_DATE,'Добавлен в пул обзвона',$2::uuid)`, clientID, actor)
		if err != nil {
			return 0, err
		}
		count++
	}
	if err = tx.Commit(ctx); err != nil {
		return 0, err
	}
	return count, nil
}

type ClientAction struct {
	ID       string    `json:"id"`
	Kind     string    `json:"kind"`
	Number   string    `json:"number"`
	Date     time.Time `json:"date"`
	Status   string    `json:"status"`
	Comment  string    `json:"comment"`
	AuthorID string    `json:"author_id"`
}

func (s *Store) Actions(ctx context.Context, clientID string) ([]ClientAction, error) {
	rows, err := s.pool.Query(ctx, `SELECT id::text,kind,letter_number,letter_date,status,comment,author_id::text FROM client_actions WHERE client_id=$1::uuid ORDER BY letter_date DESC,created_at DESC`, clientID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ClientAction{}
	for rows.Next() {
		var a ClientAction
		if err = rows.Scan(&a.ID, &a.Kind, &a.Number, &a.Date, &a.Status, &a.Comment, &a.AuthorID); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

func (s *Store) AddAction(ctx context.Context, externalID, actor string, a ClientAction) (*ClientAction, error) {
	if (a.Kind != "claim" && a.Kind != "sanction") || strings.TrimSpace(a.Number) == "" || a.Date.IsZero() || strings.TrimSpace(a.Status) == "" {
		return nil, ErrInvalidEvent
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	var clientID string
	err = tx.QueryRow(ctx, `SELECT c.id::text FROM clients c WHERE c.external_id=$1 AND EXISTS(SELECT 1 FROM users WHERE id=$2::uuid AND role='admin') FOR UPDATE`, externalID, actor).Scan(&clientID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrForbidden
	}
	if err != nil {
		return nil, err
	}
	err = tx.QueryRow(ctx, `INSERT INTO client_actions(client_id,kind,letter_number,letter_date,status,comment,author_id) VALUES($1::uuid,$2,$3,$4,$5,$6,$7::uuid) RETURNING id::text`, clientID, a.Kind, a.Number, a.Date, a.Status, a.Comment, actor).Scan(&a.ID)
	if err != nil {
		return nil, err
	}
	_, err = tx.Exec(ctx, `INSERT INTO client_events(client_id,event_type,event_date,comment,author_id) VALUES($1::uuid,'claim',$2,$3,$4::uuid)`, clientID, a.Date, a.Kind+" № "+a.Number+": "+a.Status+". "+a.Comment, actor)
	if err != nil {
		return nil, err
	}
	if err = tx.Commit(ctx); err != nil {
		return nil, err
	}
	a.AuthorID = actor
	return &a, nil
}
