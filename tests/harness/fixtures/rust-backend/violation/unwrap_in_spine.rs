use std::env;

pub fn config() -> String {
    let raw = env::var("CONFIG").unwrap();
    raw
}
