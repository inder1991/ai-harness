package handlers

import (
	"net/http"
)

func Hello() {
	http.Get("/")
}
