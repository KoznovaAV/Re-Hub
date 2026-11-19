package migrations

import "embed"

// FS contains the ordered SQL migrations applied by internal/db.
//
//go:embed *.sql
var FS embed.FS
