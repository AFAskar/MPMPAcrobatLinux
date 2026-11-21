//! Default appearance data. /DA, /DS, canonical values and rich spans are distinct.
use super::{resolved, text};
use anyhow::{bail, Context, Result};
use lopdf::{dictionary, Document, ObjectId};
use serde_json::{json, Value};

/// Explicitly borderless widgets use the whole width for plain text in Reader.
/// Other border layouts retain the existing inset until separately qualified.
pub fn plain_text_inset(doc: &Document, widget: ObjectId) -> Result<f32> {
    let widget = doc.get_dictionary(widget)?;
    let width = if let Ok(bs) = widget.get(b"BS") {
        resolved(doc, bs)?
            .as_dict()?
            .get(b"W")
            .ok()
            .and_then(|width| width.as_float().ok())
    } else {
        widget
            .get(b"Border")
            .ok()
            .and_then(|border| resolved(doc, border).ok())
            .and_then(|border| border.as_array().ok())
            .and_then(|border| border.get(2))
            .and_then(|width| width.as_float().ok())
    };
    Ok(if width == Some(0.) { 0. } else { 1. })
}

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

pub fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| same(a, b))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len() && a.iter().all(|(k, v)| b.get(k).is_some_and(|b| same(v, b)))
        }
        _ => a == b,
    }
}

pub fn appearance(doc: &Document, font: &str, size: f64, color: &Value) -> Result<String> {
    if !size.is_finite() || size < 0. {
        bail!("Invalid persisted field font size")
    }
    let form = resolved(doc, doc.catalog()?.get(b"AcroForm")?)?.as_dict()?;
    let resources = resolved(doc, form.get(b"DR")?)?.as_dict()?;
    let fonts = resolved(doc, resources.get(b"Font")?)?.as_dict()?;
    let key = if fonts.has(font.as_bytes()) {
        font.as_bytes().to_vec()
    } else {
        fonts
            .iter()
            .find_map(|(key, value)| {
                let dictionary = resolved(doc, value).ok()?.as_dict().ok()?;
                (text(doc, dictionary.get(b"BaseFont").ok()?) == font).then(|| key.clone())
            })
            .with_context(|| {
                format!("Persisted field font absent from AcroForm resources: {font}")
            })?
    };
    let name = key
        .iter()
        .map(|byte| {
            if (33..=126).contains(byte) && !b"#%()/<>[]{}".contains(byte) {
                (*byte as char).to_string()
            } else {
                format!("#{byte:02X}")
            }
        })
        .collect::<String>();
    Ok(format!("/{name} {size} Tf {}", color_operator(color)?))
}

/// Pushbuttons (including icon-only buttons) may lack an existing AcroForm font
/// resource matching their default font name. Resolve an existing widget/form
/// font or register a standard Helvetica resource before emitting /DA.
pub fn button_appearance(
    doc: &mut Document,
    widget: Option<ObjectId>,
    font: &str,
    size: f64,
    color: &Value,
) -> Result<String> {
    if let Ok(da) = appearance(doc, font, size, color) {
        return Ok(da);
    }
    if let Some(widget_id) = widget {
        if let Ok(Some(existing)) = widget_font(doc, widget_id) {
            if let Ok(da) = appearance(doc, &existing, size, color) {
                return Ok(da);
            }
        }
    }
    for candidate in ["Helv", "Helvetica"] {
        if let Ok(da) = appearance(doc, candidate, size, color) {
            return Ok(da);
        }
    }
    if !size.is_finite() || size < 0. {
        bail!("Invalid persisted field font size")
    }
    let helv_id = doc.add_object(lopdf::dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Name" => "Helv",
    });
    if let Ok(form_ref) = doc
        .catalog()
        .and_then(|c| c.get(b"AcroForm"))
        .and_then(|v| v.as_reference())
    {
        let dr_ref = doc
            .get_dictionary(form_ref)
            .ok()
            .and_then(|d| d.get(b"DR").ok())
            .and_then(|v| v.as_reference().ok());
        if let Some(dr_id) = dr_ref {
            let font_ref = doc
                .get_dictionary(dr_id)
                .ok()
                .and_then(|d| d.get(b"Font").ok())
                .and_then(|v| v.as_reference().ok());
            if let Some(font_id) = font_ref {
                if let Ok(fonts) = doc.get_dictionary_mut(font_id) {
                    fonts.set("Helv", helv_id);
                }
            } else if let Ok(dr) = doc.get_dictionary_mut(dr_id) {
                if let Ok(fonts) = dr.get_mut(b"Font").and_then(|v| v.as_dict_mut()) {
                    fonts.set("Helv", helv_id);
                } else {
                    dr.set("Font", lopdf::dictionary! {"Helv" => helv_id});
                }
            }
        } else if let Ok(form) = doc.get_dictionary_mut(form_ref) {
            if let Ok(dr) = form.get_mut(b"DR").and_then(|v| v.as_dict_mut()) {
                if let Ok(fonts) = dr.get_mut(b"Font").and_then(|v| v.as_dict_mut()) {
                    fonts.set("Helv", helv_id);
                } else {
                    dr.set("Font", lopdf::dictionary! {"Helv" => helv_id});
                }
            } else {
                form.set(
                    "DR",
                    lopdf::dictionary! {"Font" => lopdf::dictionary! {"Helv" => helv_id}},
                );
            }
        }
    }
    Ok(format!("/Helv {size} Tf {}", color_operator(color)?))
}

fn color_operator(value: &Value) -> Result<String> {
    let values = value.as_array().context("Invalid field text color")?;
    let (count, operator) = match values.first().and_then(Value::as_str) {
        Some("G") => (1, "g"),
        Some("RGB") => (3, "rg"),
        Some("CMYK") => (4, "k"),
        _ => bail!("Unsupported persisted field text color"),
    };
    if values.len() != count + 1 {
        bail!("Invalid field text color arity")
    }
    let mut operands = Vec::new();
    for value in &values[1..] {
        let n = value.as_f64().context("Invalid field text color channel")?;
        if !n.is_finite() || !(0.0..=1.0).contains(&n) {
            bail!("Invalid field text color channel")
        }
        operands.push(n.to_string());
    }
    Ok(format!("{} {operator}", operands.join(" ")))
}

pub fn widget_font(doc: &Document, widget: ObjectId) -> Result<Option<String>> {
    let mut next = Some(widget);
    let mut seen = std::collections::BTreeSet::new();
    while let Some(id) = next {
        if !seen.insert(id) {
            bail!("Cyclic widget style inheritance")
        }
        let dictionary = doc.get_dictionary(id)?;
        if let Ok(da) = dictionary.get(b"DA") {
            let da = text(doc, da);
            let content = lopdf::content::Content::decode(da.as_bytes())?;
            let font = content
                .operations
                .iter()
                .rev()
                .find(|op| op.operator == "Tf")
                .and_then(|op| op.operands.first())
                .and_then(|value| value.as_name().ok());
            return font
                .map(|name| String::from_utf8(name.to_vec()).map_err(Into::into))
                .transpose();
        }
        next = dictionary
            .get(b"Parent")
            .ok()
            .and_then(|parent| parent.as_reference().ok());
    }
    Ok(None)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn border_style_precedes_legacy_border_and_defaults_remain_distinct() {
        let mut doc = Document::with_version("1.7");
        let legacy =
            doc.add_object(lopdf::dictionary! {"Border" => vec![0.into(), 0.into(), 0.into()]});
        assert_eq!(plain_text_inset(&doc, legacy).unwrap(), 0.);
        let bs = doc.add_object(lopdf::dictionary! {"W" => 1});
        doc.get_dictionary_mut(legacy).unwrap().set("BS", bs);
        assert_eq!(plain_text_inset(&doc, legacy).unwrap(), 1.);
        doc.get_dictionary_mut(bs).unwrap().set("W", 0);
        assert_eq!(plain_text_inset(&doc, legacy).unwrap(), 0.);
        doc.get_dictionary_mut(bs).unwrap().remove(b"W");
        assert_eq!(plain_text_inset(&doc, legacy).unwrap(), 1.);
        let absent = doc.add_object(lopdf::Dictionary::new());
        assert_eq!(plain_text_inset(&doc, absent).unwrap(), 1.);
    }
    #[test]
    fn style_numeric_representation_does_not_rewrite_unchanged_metadata() {
        assert!(same(
            &json!({"textSize":7.0,"textColor":["RGB",0.0,0.0,0.0]}),
            &json!({"textColor":["RGB",0,0,0],"textSize":7})
        ));
        assert!(!same(&json!({"textSize":7.0}), &json!({"textSize":9})));
    }
    #[test]
    fn serialized_default_colors_roundtrip_and_reject_invalid_input() {
        for value in [json!(["G", 0.0]), json!(["RGB", 0.25, 0.5, 1.0])] {
            assert_eq!(color(&color_operator(&value).unwrap()).unwrap(), value);
        }
        assert!(color_operator(&json!(["RGB", 0, 2, 0])).is_err());
    }
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
