package models

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
