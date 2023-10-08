package actions

import (
	"context"
	"fmt"
	"log"

	"github.com/PoteeDev/admin/api/database"
	managerModels "github.com/PoteeDev/scenario-manager/src/models"
	scoreModels "github.com/PoteeDev/scores/models"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo/options"
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

func checkServiceStatus(service managerModels.Services) int {
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
		score := scoreModels.Score{}
		filter := bson.D{primitive.E{Key: "id", Value: fmt.Sprintf("%d", teamID)}}
		scoreboard := database.GetCollection(database.DB, "scoreboard")
		if err := scoreboard.FindOne(context.TODO(), filter).Decode(&score); err != nil {
			log.Println(err)
		}
		var totalServiceScore float64
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
						score.TotalLost += 1
						service.Reputation -= exploit.Cost
					} else {
						service.Gained += 1
						score.TotalGained += 1
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
			totalServiceScore += service.Score
			score.Srv[serviceName] = service
		}
		score.TotalScore = totalServiceScore / float64(len(score.Srv))
		scoreboard.ReplaceOne(context.TODO(), filter, score)
	}

}

func (a *Actions) UpdatePlaces() {
	col := database.GetCollection(database.DB, "scoreboard")
	opts := options.Find().SetSort(bson.D{{Key: "total_score", Value: 1}, {Key: "total_lost", Value: -1}})
	cursor, err := col.Find(context.TODO(), bson.D{}, opts)
	if err != nil {
		log.Println(err)
	}
	var results []scoreModels.Score
	if err = cursor.All(context.TODO(), &results); err != nil {
		panic(err)
	}

	for place, result := range results {
		update := bson.D{{Key: "$set", Value: bson.D{
			{Key: "last_place", Value: result.Place},
			{Key: "place", Value: place + 1}}},
		}
		filter := bson.D{{Key: "id", Value: result.ID}}
		col.UpdateOne(context.TODO(), filter, update)
	}
}
