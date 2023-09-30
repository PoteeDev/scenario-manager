package actions

import (
	"context"
	"time"

	"github.com/PoteeDev/admin/api/database"
	managerModels "github.com/PoteeDev/scenario-manager/src/models"
	"go.mongodb.org/mongo-driver/bson"
)

// function for initializate new round
func (a *Actions) NewRound() {
	info := map[int]managerModels.RoundInfo{}
	entities, _ := database.GetEntities()
	for id, entity := range entities {
		if !entity.Visible || entity.Blocked {
			continue
		}
		services := map[string]managerModels.Services{}
		for serviceName, service := range a.Scenario.Services {
			chekcers := map[string]managerModels.Checker{}
			for _, chekerName := range service.Checkers {
				chekcers[chekerName] = managerModels.Checker{
					PutStatus: Mumbled,
					GetStatus: Mumbled,
				}
			}

			exploits := map[string]managerModels.Exploit{}
			for name, exploit := range service.Exploits {
				exploits[name] = managerModels.Exploit{
					Cost:   exploit.Cost,
					Status: NotSet,
				}
			}
			services[serviceName] = managerModels.Services{
				PingStatus: Unreacheble,
				Checkers:   chekcers,
				Exploits:   exploits,
			}
		}
		info[id+1] = managerModels.RoundInfo{
			TeamName: entity.Login,
			TeamHost: entity.IP,
			Services: services,
		}
	}
	a.RoundInfo = info
	a.Cache.IncrementRound()
	a.CurrentRound = a.Cache.CurrentRound()
}

func (a *Actions) SaveRoundEvents() {
	eventsCollection := database.GetCollection(database.DB, "events")
	eventsCollection.InsertOne(context.Background(), bson.M{"events": a.RoundInfo, "timestamp": time.Now().Unix()})
}
