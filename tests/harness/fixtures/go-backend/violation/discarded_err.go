package handlers

import "fmt"

func MaybeWrite() {
	_, err := fmt.Println("hello")
	_ = err
}
