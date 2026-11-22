package store

import "time"

type Period struct {
	ID      string `json:"id"`
	Code    string `json:"code"`
	Label   string `json:"label"`
	Year    int    `json:"year"`
	Quarter int    `json:"quarter"`
}

type Record struct {
	PeriodCode  string    `json:"period_code"`
	SliceDate   time.Time `json:"slice_date"`
	TotalDocs   *int      `json:"total_docs"`
	NotSentDocs int       `json:"not_sent_docs"`
	Share       *float64  `json:"share"`
	Inherited   bool      `json:"inherited"`
}

type Client struct {
	InPool         bool       `json:"in_pool"`
	JoinedOn       *time.Time `json:"joined_on,omitempty"`
	ID             string     `json:"id"`
	ExternalID     string     `json:"external_id"`
	Name           string     `json:"name"`
	INN            string     `json:"inn"`
	KPP            string     `json:"kpp"`
	Stage          string     `json:"stage"`
	AssignedTo     string     `json:"assigned_to,omitempty"`
	AssignedName   string     `json:"assigned_name,omitempty"`
	Excluded       bool       `json:"excluded"`
	Inactive       bool       `json:"inactive"`
	ExcludedReason string     `json:"excluded_reason,omitempty"`
	Tags           []string   `json:"tags"`
	PromisedAt     *time.Time `json:"promised_at,omitempty"`
	LastContactAt  *time.Time `json:"last_contact_at,omitempty"`
	ContactDetails string     `json:"contact_details,omitempty"`
	ContactName    string     `json:"contact_name,omitempty"`
	ContactPhone   string     `json:"contact_phone,omitempty"`
	ContactEmail   string     `json:"contact_email,omitempty"`
	Latest         *Record    `json:"latest,omitempty"`
	Previous       *Record    `json:"previous,omitempty"`
	Missing        bool       `json:"missing"`
	Active         bool       `json:"active"`
}

type Event struct {
	PromiseLabel string     `json:"promise_label,omitempty"`
	CallbackOn   *time.Time `json:"callback_on,omitempty"`
	PeriodCode   string     `json:"period_code,omitempty"`
	ID           string     `json:"id"`
	ClientID     string     `json:"client_id"`
	Type         string     `json:"event_type"`
	Date         time.Time  `json:"event_date"`
	Result       string     `json:"result,omitempty"`
	PromisedAt   *time.Time `json:"promised_at,omitempty"`
	Comment      string     `json:"comment,omitempty"`
	AuthorID     string     `json:"author_id,omitempty"`
	AuthorName   string     `json:"author_name,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
}

type ListFilters struct {
	ExternalIDs []string
	WorkOnly    bool
	PoolOnly    bool
	PeriodCode  string
	MinUnsent   int
	CallList    bool
	ExternalID  string
	INN         string
	Stage       string
	Assigned    string
	UserID      string
	Tag         string
	Contacted   string
	MinShare    *float64
	Excluded    *bool
	Inactive    *bool
	Limit       int
	Offset      int
	Sort        string
	Desc        bool
}

type NewClientData struct {
	ContactDetails *string
	ExternalID     string
	Name           string
	Tags           []string
	Excluded       bool
	Active         *bool
	SourceRow      int
}

type ParsedRow struct {
	ExternalID string
	PeriodCode string
	TotalDocs  *int
	NotSent    int
	Sheet      string
	Row        int
}

type ParsedError struct {
	Scope      string `json:"scope"`
	Row        *int   `json:"row,omitempty"`
	Column     string `json:"column,omitempty"`
	Code       string `json:"code"`
	Message    string `json:"message"`
	RawValue   string `json:"raw_value,omitempty"`
	ExternalID string `json:"external_id,omitempty"`
	PeriodCode string `json:"period_code,omitempty"`
}

type ImportResult struct {
	ImportID    string
	Kind        string
	RowsTotal   int
	RowsOK      int
	RowsErrors  int
	Created     int
	Updated     int
	PeriodScope []string
	Status      string
	Errors      []ParsedError
}
