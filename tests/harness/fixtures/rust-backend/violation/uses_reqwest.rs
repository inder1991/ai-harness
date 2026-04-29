use reqwest;

pub async fn fetch_user(id: &str) -> Result<String, Box<dyn std::error::Error>> {
    let body = reqwest::get(&format!("/u/{}", id)).await?.text().await?;
    Ok(body)
}
