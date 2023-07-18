package actions

import "github.com/PoteeDev/admin/api/database"

type RoundInfo struct {
	TeamName string
	TeamHost string
	Services map[string]Services
}

type Services struct {
	PingStatus int
	Checkers   map[string]Checkers
}

type Checkers struct {
	GetStatus int
	PutStatus int
}

func (a *Actions) NewRound() {
	info := map[int]RoundInfo{}
	entities, _ := database.GetAllEntities()
	for id, entity := range entities {
		services := map[string]Services{}
		for serviceName, service := range a.Scenario.Services {
			chekcers := map[string]Checkers{}
			for _, chekerName := range service.Checkers {
				chekcers[chekerName] = Checkers{
					PutStatus: Mumbled,
					GetStatus: Mumbled,
				}
			}
			services[serviceName] = Services{
				PingStatus: Unreacheble,
				Checkers:   chekcers,
			}
		}
		info[id+1] = RoundInfo{
			TeamName: entity.Login,
			TeamHost: entity.IP,
			Services: services,
		}
	}
	a.RoundInfo = info
	a.Cache.IncrementRound()
	a.CurrentRound = a.Cache.CurrentRound()
}

func (r *RoundInfo) SetPingStatus(serviceName string, status int) {
	if service, ok := r.Services[serviceName]; ok {
		service.PingStatus = status
		r.Services[serviceName] = service
	}
}

func (r *RoundInfo) SetGetStatus(serviceName, chekcerName string, status int) {
	r.Services[serviceName].Checkers[chekcerName] = Checkers{GetStatus: status, PutStatus: Mumbled}
	if checker, ok := r.Services[serviceName].Checkers[chekcerName]; ok {
		checker.GetStatus = status
		r.Services[serviceName].Checkers[chekcerName] = checker
	}
}

func (r *RoundInfo) SetPutStatus(serviceName, chekcerName string, status int) {
	r.Services[serviceName].Checkers[chekcerName] = Checkers{GetStatus: status, PutStatus: Mumbled}
	if checker, ok := r.Services[serviceName].Checkers[chekcerName]; ok {
		checker.PutStatus = status
		r.Services[serviceName].Checkers[chekcerName] = checker
	}
}
