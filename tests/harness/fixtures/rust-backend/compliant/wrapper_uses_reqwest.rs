use reqwest::Client;
use std::time::Duration;

pub fn build_client() -> Result<Client, reqwest::Error> {
    Client::builder().timeout(Duration::from_secs(5)).build()
}
