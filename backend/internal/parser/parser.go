package parser

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Source struct {
	Sheet  string  `json:"sheet"`
	Row    int     `json:"row"`
	Column *string `json:"column,omitempty"`
}

type Error struct {
	Scope    string  `json:"scope"`
	Code     string  `json:"code"`
	Message  string  `json:"message"`
	Source   *Source `json:"source"`
	RawValue any     `json:"raw_value"`
	KeyHint  struct {
		ExternalID *string `json:"external_id"`
		PeriodCode *string `json:"period_code"`
	} `json:"key_hint"`
}

type Row struct {
	Source Source          `json:"source"`
	Data   json.RawMessage `json:"data"`
}

type Result struct {
	ContractVersion  string  `json:"contract_version"`
	FileKind         string  `json:"file_kind"`
	KeyMode          string  `json:"key_mode"`
	NonemptyRowCount int     `json:"nonempty_row_count"`
	Rows             []Row   `json:"rows"`
	Errors           []Error `json:"errors"`
}

type SnapshotData struct {
	ExternalID string `json:"external_id"`
	PeriodCode string `json:"period_code"`
	TotalDocs  *int   `json:"total_docs"`
	UnsentDocs int    `json:"unsent_docs"`
}

type ClientData struct {
	INN             *string  `json:"inn"`
	KPP             *string  `json:"kpp"`
	JoinedOn        *string  `json:"joined_on"`
	Blocked         *bool    `json:"blocked"`
	ExcludedReason  *string  `json:"excluded_reason"`
	EKBOffsetHours  *int     `json:"ekb_offset_hours"`
	SourceStatusRaw *string  `json:"source_status_raw"`
	ExternalID      string   `json:"external_id"`
	Name            string   `json:"name"`
	ContactDetails  *string  `json:"contact_details"`
	Tags            []string `json:"tags"`
	Excluded        *bool    `json:"excluded"`
	Active          *bool    `json:"active"`
}

type Client struct {
	baseURL string
	http    *http.Client
}

func New(baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http: &http.Client{
			Timeout: 90 * time.Second,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}
}

func (c *Client) Parse(ctx context.Context, filePath string, parseContext map[string]any) (*Result, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", filepath.Base(filePath))
	if err != nil {
		return nil, err
	}
	if _, err := io.Copy(part, file); err != nil {
		return nil, err
	}
	contextJSON, err := json.Marshal(parseContext)
	if err != nil {
		return nil, err
	}
	if err := writer.WriteField("context", string(contextJSON)); err != nil {
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/parse", &body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call parser: %w", err)
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("parser returned %d: %s", resp.StatusCode, strings.TrimSpace(string(payload)))
	}
	var result Result
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&result); err != nil {
		return nil, fmt.Errorf("decode parser result: %w", err)
	}
	if result.ContractVersion != "1.0" || len(result.Rows)+len(result.Errors) == 0 && result.NonemptyRowCount == 0 {
		return nil, fmt.Errorf("parser returned an unsupported result")
	}
	if decoder.Decode(new(any)) != io.EOF {
		return nil, fmt.Errorf("trailing parser data")
	}
	if result.FileKind != parseContext["file_kind"] || result.KeyMode != parseContext["key_mode"] {
		return nil, fmt.Errorf("parser context mismatch")
	}
	for _, row := range result.Rows {
		d := json.NewDecoder(bytes.NewReader(row.Data))
		d.DisallowUnknownFields()
		var err error
		if result.FileKind == "clients" {
			var data ClientData
			err = d.Decode(&data)
		} else {
			var data SnapshotData
			err = d.Decode(&data)
		}
		if err != nil {
			return nil, fmt.Errorf("invalid row contract: %w", err)
		}
	}
	return &result, nil
}
