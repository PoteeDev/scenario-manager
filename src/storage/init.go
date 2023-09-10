package storage

import (
	"context"
	"fmt"
	"log"

	"github.com/PoteeDev/admin/api/database"
	"github.com/PoteeDev/scenario-manager/src/scenario"
	"github.com/PoteeDev/scores/models"
	"go.mongodb.org/mongo-driver/bson"
)

const (
	Reputation = 1000
)

func InitScoreboard(scenario *scenario.Scenario) {
	scoreboard := database.GetCollection(database.DB, "scoreboard")
	// get exists scoreboard
	count, _ := scoreboard.CountDocuments(context.TODO(), bson.D{})

	// check if rows already not exists

	log.Println("init count:", count)
	if count == 0 {
		// add scoreboard documents
		entities, _ := database.GetEntities()

		for id, entity := range entities {
			score := models.Score{
				ID:   fmt.Sprintf("%d", id+1),
				Name: entity.Login,
			}
			score.Srv = make(map[string]models.Service)
			for serviceName := range scenario.Services {
				score.Srv[serviceName] = models.Service{
					Reputation: Reputation,
					Gained:     0,
					Lost:       0,
					Score:      Reputation,
				}
			}
			result, err := scoreboard.InsertOne(
				context.TODO(),
				score,
			)
			if err != nil {
				log.Println("init error:", err)
			}
			log.Println(result.InsertedID)
		}
	}
}
