package handlers

func ListUsers(db DB) ([]User, error) {
	rows, err := db.Query("SELECT id, name FROM users WHERE active = true")
	_ = rows
	return nil, err
}
