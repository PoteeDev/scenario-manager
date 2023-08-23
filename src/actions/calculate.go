package actions

import (
	"context"
	"fmt"
	"log"

	"github.com/PoteeDev/admin/api/database"
	"github.com/PoteeDev/scores/models"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

const (
	// services
	ServiceOk   = 1
	Mumbled     = 0
	Unreacheble = -1
	// exploits
	Exploitable = 1
	Safety      = 0
	NotSet      = -1
)

func checkServiceStatus(service Services) int {
	if service.PingStatus == ServiceOk {
		for _, checker := range service.Checkers {
			if checker.GetStatus != ServiceOk || checker.PutStatus != ServiceOk {
				return Mumbled
			}
		}
		return ServiceOk
	}
	return Unreacheble
}

func (a *Actions) UpdateServicesStatus() {
	for teamID, round := range a.RoundInfo {
		score := models.Score{}
		filter := bson.D{primitive.E{Key: "id", Value: fmt.Sprintf("%d", teamID)}}
		scoreboard := database.GetCollection(database.DB, "scoreboard")
		if err := scoreboard.FindOne(context.TODO(), filter).Decode(&score); err != nil {
			log.Println(err)
		}
		for serviceName, serviceInfo := range round.Services {
			service := score.Srv[serviceName]

			// update Status
			service.Status = checkServiceStatus(serviceInfo)

			// state 0 - not worked or 1 - worked
			state := 0.0
			if service.Status > 0 {
				state = 1.0
			}
			// update exploits
			for _, exploit := range serviceInfo.Exploits {
				if exploit.Status != NotSet {
					if exploit.Status == Exploitable {
						service.Lost += 1
						service.Reputation -= exploit.Cost
					} else {
						service.Gained += 1
					}
				}
			}
			// update SLA
			if a.CurrentRound > 0 {
				service.SLA = (score.Srv[serviceName].SLA*(float64(a.CurrentRound)-1) + float64(state)) / float64(a.CurrentRound)
			} else {
				service.SLA = float64(state)
			}

			// update Score
			service.Score = float64(service.Reputation) * service.SLA

			score.Srv[serviceName] = service
			scoreboard.ReplaceOne(context.TODO(), filter, score)
		}
	}

}
