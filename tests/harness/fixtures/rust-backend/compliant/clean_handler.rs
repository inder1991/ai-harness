use std::env;

pub fn config() -> Result<String, env::VarError> {
    let raw = env::var("CONFIG")?;
    Ok(raw)
}
