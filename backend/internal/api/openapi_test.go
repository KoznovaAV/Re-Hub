package api

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

// Detect advertised routes without handlers, and handlers missing from the API contract.
func TestOpenAPIRoutesMatchHandlers(t *testing.T) {
	spec, err := os.ReadFile("../../contracts/openapi.yaml")
	if err != nil {
		t.Fatal(err)
	}
	declared := map[string]bool{}
	pathRE := regexp.MustCompile(`^  (/[^:]*):$`)
	methodRE := regexp.MustCompile(`^    (get|post|put|patch|delete):$`)
	path := ""
	for _, line := range strings.Split(string(spec), "\n") {
		if match := pathRE.FindStringSubmatch(line); match != nil {
			path = match[1]
		}
		if match := methodRE.FindStringSubmatch(line); match != nil && path != "" {
			prefix := "/api/v1"
			if path == "/health" || path == "/api/probe" {
				prefix = ""
			}
			declared[strings.ToUpper(match[1])+" "+prefix+path] = true
		}
	}
	implemented := map[string]bool{}
	for _, file := range []string{"api.go", "../../cmd/api/main.go"} {
		tree, err := parser.ParseFile(token.NewFileSet(), file, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		ast.Inspect(tree, func(node ast.Node) bool {
			call, ok := node.(*ast.CallExpr)
			if !ok || len(call.Args) == 0 {
				return true
			}
			sel, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || (sel.Sel.Name != "HandleFunc" && sel.Sel.Name != "Handle") {
				return true
			}
			literal, ok := call.Args[0].(*ast.BasicLit)
			if !ok || literal.Kind != token.STRING {
				return true
			}
			value, err := strconv.Unquote(literal.Value)
			if err == nil && strings.Contains(value, " ") {
				implemented[value] = true
			}
			return true
		})
	}
	if len(declared) == 0 || len(implemented) == 0 {
		t.Fatal("route discovery returned no routes")
	}
	for route := range declared {
		if !implemented[route] {
			t.Errorf("OpenAPI advertises an unimplemented route: %s", route)
		}
	}
	for route := range implemented {
		if !declared[route] {
			t.Errorf("handler has no OpenAPI operation: %s", route)
		}
	}
}
