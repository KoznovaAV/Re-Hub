package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"time"

	"github.com/KoznovaAV/Re-Hub/backend/internal/probe"
	"github.com/gin-gonic/gin"
	"github.com/go-chi/chi/v5"
)

const path = "/api/probe"

func main() {
	router := flag.String("router", "net/http", "net/http, chi or gin")
	mode := flag.String("mode", "route", "route or probe")
	pythonURL := flag.String("python", "http://127.0.0.1:8001", "Python service URL")
	flag.Parse()

	var endpoint http.Handler
	switch *mode {
	case "route":
		endpoint = http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"schema_version":1,"request_id":"skeleton","status":"ok"}`))
		})
	case "probe":
		endpoint = probe.NewHandler(*pythonURL)
	default:
		log.Fatal("invalid mode")
	}

	var handler http.Handler
	switch *router {
	case "net/http":
		mux := http.NewServeMux()
		mux.Handle("GET "+path, endpoint)
		handler = mux
	case "chi":
		mux := chi.NewRouter()
		mux.Method(http.MethodGet, path, endpoint)
		handler = mux
	case "gin":
		gin.SetMode(gin.ReleaseMode)
		mux := gin.New()
		mux.GET(path, gin.WrapH(endpoint))
		handler = mux
	default:
		log.Fatal("invalid router")
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(listener.Addr().(*net.TCPAddr).Port)
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 3 * time.Second, IdleTimeout: 30 * time.Second}
	log.Fatal(server.Serve(listener))
}
