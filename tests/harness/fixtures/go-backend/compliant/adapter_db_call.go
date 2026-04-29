package dbadapter

func ListUsers(db DB) ([]User, error) {
	rows, err := db.Query("SELECT id, name FROM users WHERE active = $1", true)
	_ = rows
	return nil, err
}
