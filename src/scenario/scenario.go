package scenario

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"os"
	"time"

	"github.com/PoteeDev/admin/api/database"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
	"gopkg.in/yaml.v3"
)

type Scenario struct {
	ID            string             `bson:"id,omitempty"`
	Time          string             `yaml:"time" bson:"time,omitempty"`
	Period        string             `yaml:"period" bson:"period,omitempty"`
	GlobalActions []string           `yaml:"global_actions" bson:"global_actions,omitempty"`
	Actions       []string           `yaml:"actions" bson:"actions,omitempty"`
	Services      map[string]Service `yaml:"services" bson:"services,omitempty"`
	NewsChatID    int                `yaml:"news_chat_id" bson:"news_chat_id,omitempty"`
	News          []News             `yaml:"news" bson:"news,omitempty"`
}

type Service struct {
	Name        string             `yaml:"name" bson:"name,omitempty"`
	Description string             `yaml:"description" bson:"description,omitempty"`
	Reputation  int                `yaml:"reputation" bson:"reputation,omitempty"`
	Domain      string             `yaml:"domain" bson:"domain,omitempty"`
	Script      string             `yaml:"script" bson:"script,omitempty"`
	Checkers    []string           `yaml:"checkers" bson:"checkers,omitempty"`
	Exploits    map[string]Exploit `yaml:"exploits" bson:"exploits,omitempty"`
}

type Exploit struct {
	StartAt string `yaml:"startAt" bson:"start_at,omitempty"`
	Period  string `yaml:"period" bson:"period,omitempty"`
	Cost    int    `yaml:"cost" bson:"cost,omitempty"`
	Rounds  []int  `bson:"rounds,omitempty"`
}

type News struct {
	Round int    `yaml:"round" bson:"round,omitempty"`
	Text  string `yaml:"text" bson:"text,omitempty"`
	Mode  string `yaml:"mode" bson:"mode,omitempty"`
}

func GenerateExploitRounds(allTime, roundPeriod string, exploitInfo Exploit) []int {

	allTimeDuration, _ := time.ParseDuration(allTime)
	roundPeriodDuration, _ := time.ParseDuration(roundPeriod)
	exploitPeriodDuration, _ := time.ParseDuration(exploitInfo.Period)
	startAtDuration, _ := time.ParseDuration(exploitInfo.StartAt)
	roundCounts := allTimeDuration.Seconds() / roundPeriodDuration.Seconds()
	startRound := startAtDuration.Seconds() / roundPeriodDuration.Seconds()
	intervalRound := exploitPeriodDuration.Seconds() / roundPeriodDuration.Seconds()
	fmt.Println(roundCounts, exploitPeriodDuration, startAtDuration, startRound, intervalRound)
	rounds := []int{int(startRound)}
	round := rounds[0]
	for {
		round += int(intervalRound)
		if round > int(roundCounts) {
			break
		}
		rounds = append(rounds, round+rand.Intn(int(intervalRound))-int(intervalRound*0.5))
	}
	return rounds
}

func (s *Scenario) SaveToDB() {
	s.ID = "scenario"
	client := database.ConnectDB()
	coll := database.GetCollection(client, "settings")
	filter := bson.M{"id": "scenario"}
	update := bson.D{{Key: "$set", Value: s}}
	opts := options.Update().SetUpsert(true)
	result, err := coll.UpdateOne(context.TODO(), filter, update, opts)
	if err != nil {
		panic(err)
	}
	log.Println(result)
}

func LoadScenario(filename string) *Scenario {
	data, err := os.ReadFile(filename)
	if err != nil {
		fmt.Println(err)
		return nil
	}

	// Create a struct to hold the YAML data
	var scenario Scenario

	// Unmarshal the YAML data into the struct
	err = yaml.Unmarshal(data, &scenario)
	if err != nil {
		fmt.Println(err)
		return nil
	}

	for _, service := range scenario.Services {
		for exploitName, exploit := range service.Exploits {
			if exploit.Rounds == nil {
				// log.Println(scenario.Time, scenario.Period, serviceName, exploitName)
				rounds := GenerateExploitRounds(scenario.Time, scenario.Period, exploit)
				exploit.Rounds = rounds
			}
			service.Exploits[exploitName] = exploit
		}

	}

	// Print the data
	return &scenario
}
