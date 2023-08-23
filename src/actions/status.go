package actions

import "github.com/PoteeDev/admin/api/database"

type RoundInfo struct {
	TeamName string
	TeamHost string
	Services map[string]Services
}

type Services struct {
	PingStatus int
	Checkers   map[string]Checker
	Exploits   map[string]Exploit //exploit name and status
}

type Checker struct {
	GetStatus int
	PutStatus int
}

type Exploit struct {
	Cost   int
	Status int
}

// function for initializate new round
func (a *Actions) NewRound() {
	info := map[int]RoundInfo{}
	entities, _ := database.GetAllEntities()
	for id, entity := range entities {
		services := map[string]Services{}
		for serviceName, service := range a.Scenario.Services {
			chekcers := map[string]Checker{}
			for _, chekerName := range service.Checkers {
				chekcers[chekerName] = Checker{
					PutStatus: Mumbled,
					GetStatus: Mumbled,
				}
			}

			exploits := map[string]Exploit{}
			for name, exploit := range service.Exploits {
				exploits[name] = Exploit{
					Cost:   exploit.Cost,
					Status: NotSet,
				}
			}
			services[serviceName] = Services{
				PingStatus: Unreacheble,
				Checkers:   chekcers,
				Exploits:   exploits,
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
	// r.Services[serviceName].Checkers[chekcerName] = Checker{GetStatus: status, PutStatus: Mumbled}
	if checker, ok := r.Services[serviceName].Checkers[chekcerName]; ok {
		checker.GetStatus = status
		r.Services[serviceName].Checkers[chekcerName] = checker
	}
}

func (r *RoundInfo) SetPutStatus(serviceName, chekcerName string, status int) {
	// r.Services[serviceName].Checkers[chekcerName] = Checker{GetStatus: status, PutStatus: Mumbled}
	if checker, ok := r.Services[serviceName].Checkers[chekcerName]; ok {
		checker.PutStatus = status
		r.Services[serviceName].Checkers[chekcerName] = checker
	}
}

func (r *RoundInfo) SetExploitStatus(serviceName, exploitName string, status int) {
	if exploit, ok := r.Services[serviceName].Exploits[exploitName]; ok {
		exploit.Status = status
		r.Services[serviceName].Exploits[exploitName] = exploit
	}
}
