package scenario

import (
	"fmt"
	"math/rand"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type Scenario struct {
	Time          string             `yaml:"time"`
	Period        string             `yaml:"period"`
	GlobalActions []string           `yaml:"global_actions"`
	Actions       []string           `yaml:"actions"`
	Services      map[string]Service `yaml:"services"`
	NewsChatID    int                `yaml:"news_chat_id"`
	News          []News             `yaml:"news"`
}

type Service struct {
	Name        string             `yaml:"name"`
	Description string             `yaml:"description"`
	Reputation  int                `yaml:"reputation"`
	Domain      string             `yaml:"domain"`
	Script      string             `yaml:"script"`
	Checkers    []string           `yaml:"checkers"`
	Exploits    map[string]Exploit `yaml:"exploits"`
}

type Exploit struct {
	StartAt string `yaml:"startAt"`
	Period  string `yaml:"period"`
	Cost    int    `yaml:"cost"`
	Rounds  []int
}

type News struct {
	Round int    `yaml:"round"`
	Text  string `yaml:"text"`
	Mode  string `yaml:"mode"`
}

func GenerateExploitRounds(allTime, roundPeriod string, exploitInfo Exploit) []int {
	rand.Seed(time.Now().UnixNano())

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
