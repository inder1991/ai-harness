package handlers

import "fmt"

func MaybeWrite() error {
	_, err := fmt.Println("hello")
	if err != nil {
		return fmt.Errorf("println: %w", err)
	}
	return nil
}
