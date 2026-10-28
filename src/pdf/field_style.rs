//! Default appearance data. /DA, /DS, canonical values and rich spans are distinct.
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};

pub fn color(appearance: &str) -> Result<Value> {
    let tokens: Vec<_> = appearance.split_whitespace().collect();
    let mut result = json!(["G", 0]);
    for (index, token) in tokens.iter().enumerate() {
        let (space, count) = match *token {
            "g" => ("G", 1),
            "rg" => ("RGB", 3),
            "k" => ("CMYK", 4),
            _ => continue,
        };
        let start = index
            .checked_sub(count)
            .context("Missing default appearance color operands")?;
        let mut channels = vec![json!(space)];
        for token in &tokens[start..index] {
            let n: f64 = token
                .parse()
                .context("Invalid default appearance color operand")?;
            if !n.is_finite() || !(0.0..=1.0).contains(&n) {
                bail!("Invalid default appearance color channel")
            }
            // Reader exposes PDF default-appearance channels as 16-bit fixed point.
            channels.push(json!((n * 65536.).round() / 65536.));
        }
        result = Value::Array(channels);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn default_color_uses_last_color_operator_independently_of_font_position() {
        assert_eq!(
            color("0 g /SegoeUI 9 Tf 0 0 1 rg").unwrap(),
            json!(["RGB", 0., 0., 1.])
        );
        assert_eq!(color("1 0 0 rg /Helv 8 Tf 0 g").unwrap(), json!(["G", 0.]));
        assert!(color("/Helv 9 Tf rg").is_err());
    }
    #[test]
    fn source_decimal_colors_match_reader_fixed_point_channels() {
        assert_eq!(
            color("/SegoeUI 7 Tf 0.615 0.627 0.635 rg").unwrap(),
            json!([
                "RGB",
                0.6150054931640625,
                0.6269989013671875,
                0.6349945068359375
            ])
        );
        assert_eq!(
            color("/ZaDb 7 Tf 0.890 0.023 0.074 rg").unwrap(),
            json!([
                "RGB",
                0.8899993896484375,
                0.0229949951171875,
                0.074005126953125
            ])
        );
        assert!(color("/Helv 7 Tf 0 2 0 rg").is_err());
    }
}
