package httpclient

import (
	"net/http"
	"time"
)

var Default = &http.Client{Timeout: 5 * time.Second}
