package actions

import (
	"context"
	"fmt"
	"log"
	"os"
	"sync"
	"time"

	pb "github.com/PoteeDev/potee-tasks-checker/proto"
	managerModels "github.com/PoteeDev/scenario-manager/src/models"
	"github.com/PoteeDev/scenario-manager/src/scenario"
	"github.com/PoteeDev/scenario-manager/src/storage"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"gorm.io/gorm"
)

type Actions struct {
	Scenario     *scenario.Scenario
	DB           *gorm.DB
	Cache        *storage.Cache
	ChckerClient pb.CheckerClient
	RoundInfo    map[int]managerModels.RoundInfo
	CurrentRound int
}

type Host struct {
	Name string
	Host string
	ID   int64
}

func (a *Actions) Ping(serviceName string) {
	pingReq := &pb.PingRequest{
		Service: serviceName,
	}
	for id, host := range a.RoundInfo {
		pingReq.Data = append(pingReq.Data, &pb.PingData{
			Host: host.TeamHost,
			Id:   int64(id),
		})
	}
	pingReply, err := a.ChckerClient.Ping(context.Background(), pingReq)
	if err != nil {
		log.Println("ping request error:", err)
	}
	for _, result := range pingReply.Results {
		// save ping status
		if result.Status == 0 {
			status := a.RoundInfo[int(result.Id)]
			status.SetPingStatus(serviceName, ServiceOk)
		}
	}
}

func (a *Actions) Get(serviceName string) {
	if a.CurrentRound == 1 {
		return
	}
	for _, checkerName := range a.Scenario.Services[serviceName].Checkers {
		getReq := &pb.GetRequest{
			Service: serviceName,
			Name:    checkerName,
		}

		for id, host := range a.RoundInfo {

			if a.RoundInfo[id].Services[serviceName].PingStatus != ServiceOk {
				continue
			}
			getData := a.Cache.Get(
				fmt.Sprintf("%d", id),
				serviceName,
				checkerName,
				"get",
			)
			// if data for etract is empty
			if getData.Value == "" && a.CurrentRound > 1 {
				continue
			}
			getReq.Data = append(getReq.Data, &pb.GetData{
				Host:  host.TeamHost,
				Id:    int64(id),
				Value: getData.Value,
			})
		}

		if len(getReq.Data) > 0 {
			getReply, _ := a.ChckerClient.Get(context.Background(), getReq)
			// validate flag
			for _, result := range getReply.Results {
				if result.Status != 0 {
					continue
				}
				data := a.Cache.Get(
					fmt.Sprintf("%d", result.Id),
					serviceName,
					checkerName,
					"put",
				)
				if data.Value == result.Answer {
					//log.Println(result.Id, serviceName, "valid")
					status := a.RoundInfo[int(result.Id)]
					status.SetGetStatus(serviceName, checkerName, ServiceOk)
				}
			}
		}
	}
}
func (a *Actions) Put(serviceName string) {
	for _, checkerName := range a.Scenario.Services[serviceName].Checkers {
		putReq := &pb.PutRequest{
			Service: serviceName,
			Name:    checkerName,
		}
		for id, host := range a.RoundInfo {
			if a.RoundInfo[id].Services[serviceName].PingStatus != ServiceOk {
				continue
			}
			flag := "qwe"
			putReq.Data = append(putReq.Data, &pb.PutData{
				Host: host.TeamHost,
				Id:   int64(id),
				Flag: flag,
			})
			data := storage.ActionData{
				TeamID:  fmt.Sprintf("%d", id),
				Service: serviceName,
				Action:  "put",
				Checker: checkerName,
				Value:   flag,
			}
			a.Cache.Save(&data)
		}
		if len(putReq.Data) > 0 {
			putReply, _ := a.ChckerClient.Put(context.Background(), putReq)

			for _, result := range putReply.Results {
				if result.Status == 0 {
					data := storage.ActionData{
						TeamID:  fmt.Sprintf("%d", result.Id),
						Service: serviceName,
						Checker: checkerName,
						Action:  "get",
						Value:   result.Answer,
					}
					status := a.RoundInfo[int(result.Id)]
					status.SetPutStatus(serviceName, checkerName, ServiceOk)

					a.Cache.Save(&data)
				}
			}
		}
	}
}
func (a *Actions) Exploit(serviceName string) {
	// Generate Exploit data
	for exploitName, exploitScenario := range a.Scenario.Services[serviceName].Exploits {
		for _, round := range exploitScenario.Rounds {
			if a.Cache.CurrentRound() == round {
				log.Println(exploitScenario)
				exploitReq := &pb.ExploitRequest{
					Service: serviceName,
					Name:    exploitName,
				}
				for id, host := range a.RoundInfo {

					exploitReq.Data = append(exploitReq.Data, &pb.ExploitData{
						Host: host.TeamHost,
						Id:   int64(id),
					})
				}
				exploitReply, _ := a.ChckerClient.Exploit(context.Background(), exploitReq)
				log.Println(serviceName, "exploit: ", exploitReply)
				for _, result := range exploitReply.Results {
					status := a.RoundInfo[int(result.Id)]
					if result.Status == 0 && result.Answer == "yes" {
						status.SetExploitStatus(serviceName, exploitName, Exploitable)
					} else if result.Status == 0 && result.Answer == "no" {
						status.SetExploitStatus(serviceName, exploitName, Safety)
					}
				}
			}
		}
	}
}

func (a *Actions) Run() {
	conn, err := grpc.Dial(
		fmt.Sprintf("dns:///%s:%s", os.Getenv("CHECKER_HOST"), os.Getenv("CHECKER_PORT")),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultServiceConfig(`{"loadBalancingPolicy":"round_robin"}`),
	)
	if err != nil {
		log.Println("checker connection error:", err)
	}
	a.ChckerClient = pb.NewCheckerClient(conn)
	wg := &sync.WaitGroup{}
	for serviceName := range a.Scenario.Services {
		wg.Add(1)
		serviceName := serviceName
		go func() {
			for _, action := range a.Scenario.Actions {
				switch action {
				case "ping":
					a.Ping(serviceName)
				case "get":
					a.Get(serviceName)
				case "put":
					a.Put(serviceName)
				case "exploit":
					a.Exploit(serviceName)
				}
			}
			wg.Done()
		}()
	}
	wg.Wait()
}

func (a *Actions) StartManager(ticker *time.Ticker) {
	totalTime, err := time.ParseDuration(a.Scenario.Time)
	if err != nil {
		log.Println("scenario total time parce error:", err)
	}
	period, err := time.ParseDuration(a.Scenario.Period)
	if err != nil {
		log.Println("scenario period time parce error:", err)
	}
	totalRounds := totalTime.Seconds() / period.Seconds()

	var wg sync.WaitGroup
	wg.Add(1)

	//done := make(chan bool)
	go func() {
		for ; true; <-ticker.C {
			// increment round and clear round history
			a.NewRound()
			log.Println(a.CurrentRound)
			if a.CurrentRound >= int(totalRounds) {
				wg.Done()
				return
			}
			// run actions
			a.Run()
			// update results
			a.UpdateServicesStatus()
			a.SaveRoundEvents()
		}
	}()
	wg.Wait()
}
