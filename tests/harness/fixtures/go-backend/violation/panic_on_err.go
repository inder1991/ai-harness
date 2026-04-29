package handlers

import "fmt"

func MustWrite() {
	_, err := fmt.Println("hello")
	if err != nil {
		panic(err)
	}
}
