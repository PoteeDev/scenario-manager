package storage

import (
	"context"
	"fmt"
	"log"
	"strconv"

	"github.com/redis/go-redis/v9"
)

type ActionData struct {
	TeamID  string
	Service string
	Checker string
	Action  string
	Value   string
}

type Cache struct {
	Client *redis.Client
}

var ctx = context.Background()

func InitCache() *Cache {

	client := redis.NewClient(&redis.Options{
		Addr:     "localhost:6379",
		Password: "eYVX7EwVmmxKPCDmwMtyKVge8oLd2t81",
		DB:       0,
	})
	return &Cache{Client: client}
}

func (c *Cache) Save(data *ActionData) {
	err := c.Client.Set(
		ctx,
		fmt.Sprintf("%s:%s:%s:%s", data.TeamID, data.Service, data.Checker, data.Action),
		data.Value,
		0,
	).Err()
	if err != nil {
		log.Fatal(err)
	}
}

func (c *Cache) Get(teamID, service, checker, action string) *ActionData {
	result := c.Client.Get(
		ctx,
		fmt.Sprintf("%s:%s:%s:%s", teamID, service, checker, action),
	).Val()
	// if err != nil {
	// 	log.Fatal("redis get error:", err)
	// }

	data := ActionData{
		TeamID:  teamID,
		Service: service,
		Checker: checker,
		Action:  action,
		Value:   result,
	}

	return &data
}

func (c *Cache) IncrementRound() {
	c.Client.SetNX(ctx, "round", "0", 0)
	c.Client.Incr(ctx, "round")
}

func (c *Cache) CurrentRound() int {
	value := c.Client.Get(ctx, "round").Val()
	if value == "" {
		return 0
	}
	round, err := strconv.Atoi(value)
	if err != nil {
		log.Println(err.Error())
		return 0
	}
	return round
}
