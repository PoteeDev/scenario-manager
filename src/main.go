package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/PoteeDev/scenario-manager/src/actions"
	"github.com/PoteeDev/scenario-manager/src/scenario"
	"github.com/PoteeDev/scenario-manager/src/storage"
)

var (
	scenarioFileName = flag.String("config", "scenario.yml", "scenario config")
	dbUrl            = flag.String("db", "postgresql://root@localhost:26257/scoreboard?sslmode=disable", "scenario config")
)

type Server struct {
	Timer   *time.Ticker
	Actions *actions.Actions
}

func (s *Server) startServer() {
	http.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, "{\"message\": \"ping\"}")
	})
	http.HandleFunc("/start", func(w http.ResponseWriter, r *http.Request) {
		period, _ := time.ParseDuration(s.Actions.Scenario.Period)
		s.Timer = time.NewTicker(time.Duration(period.Seconds()) * time.Second)
		go s.Actions.StartManager(s.Timer)
		fmt.Fprintf(w, "manager started")
	})
	http.HandleFunc("/stop", func(w http.ResponseWriter, r *http.Request) {
		s.Timer.Stop()
		fmt.Fprintf(w, "manager stoped")
	})
	log.Println("start manager server")
	address := fmt.Sprintf(":%s", os.Getenv("PORT"))
	log.Fatalln(http.ListenAndServe(address, nil))

}

func main() {
	//db := storage.ConnectDB(*dbUrl)
	cache := storage.InitCache()
	s := scenario.LoadScenario(*scenarioFileName)

	storage.InitScoreboard(s)
	a := actions.Actions{Scenario: s, Cache: cache}
	server := Server{Actions: &a}
	server.startServer()
}
