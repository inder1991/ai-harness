use sqlx::PgPool;

pub async fn list_users(pool: &PgPool) -> Result<Vec<String>, sqlx::Error> {
    let rows = sqlx::query!("SELECT name FROM users WHERE active = true").fetch_all(pool).await?;
    Ok(rows.into_iter().map(|r| r.name).collect())
}
