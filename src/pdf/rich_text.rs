//! Source rich-text metadata, kept separate from appearances and canonical /V.
use anyhow::{bail, Context, Result};
use quick_xml::{events::Event, Reader, XmlVersion};
use serde_json::{json, Map, Value};

type Style = Map<String, Value>;

fn points(value: &str) -> Result<f64> {
    let number: f64 = value.trim().trim_end_matches("pt").parse()?;
    if !number.is_finite() || number < 0. {
        bail!("Invalid rich-text point size")
    }
    Ok(number)
}
fn families(value: &str) -> Value {
    json!(value
        .split(',')
        .map(|s| s.trim().trim_matches(['\'', '"']).to_owned())
        .collect::<Vec<_>>())
}
fn color(value: &str) -> Result<Value> {
    let hex = value
        .trim()
        .strip_prefix('#')
        .context("Unsupported rich-text color")?;
    if hex.len() != 6 || !hex.is_ascii() {
        bail!("Unsupported rich-text color")
    }
    let rgb = (0..3)
        .map(|i| {
            u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16)
                .map(|n| (f64::from(n) / 255. * 65536.).round() / 65536.)
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(json!(["RGB", rgb[0], rgb[1], rgb[2]]))
}
fn css(style: &mut Style, input: &str) -> Result<()> {
    for declaration in input.split(';').filter(|s| !s.trim().is_empty()) {
        let (key, value) = declaration
            .split_once(':')
            .context("Invalid rich-text style declaration")?;
        let value = value.trim();
        match key.trim() {
            "font" => {
                // AcroForm /DS uses family-before-size, unlike normal CSS.
                let mut parts: Vec<_> = value.split_whitespace().collect();
                while let Some(token) = parts.first().copied() {
                    match token {
                        "italic" | "oblique" => {
                            style.insert("fontStyle".into(), json!(token));
                        }
                        "bold" => {
                            style.insert("fontWeight".into(), json!(700));
                        }
                        "normal" => {}
                        _ => break,
                    }
                    parts.remove(0);
                }
                let index = parts
                    .iter()
                    .position(|s| s.ends_with("pt"))
                    .context("Missing rich-text font size")?;
                style.insert("textSize".into(), json!(points(parts.remove(index))?));
                let family = parts.join(" ");
                if family.is_empty() {
                    bail!("Missing rich-text font family")
                }
                style.insert("fontFamily".into(), families(&family));
            }
            "font-family" => {
                style.insert("fontFamily".into(), families(value));
            }
            "font-size" => {
                style.insert("textSize".into(), json!(points(value)?));
            }
            "font-weight" => {
                let weight = match value {
                    "normal" => 400,
                    "bold" => 700,
                    _ => value.parse::<u32>()?,
                };
                style.insert("fontWeight".into(), json!(weight));
            }
            "font-style" => {
                style.insert("fontStyle".into(), json!(value));
            }
            "font-stretch" => {
                style.insert("fontStretch".into(), json!(value));
            }
            "text-align" => {
                style.insert("alignment".into(), json!(value));
            }
            "color" => {
                style.insert("textColor".into(), color(value)?);
            }
            "line-height" => {
                style.insert("linespacing".into(), json!(points(value)?));
            }
            "margin-top" | "margin-bottom" if points(value)? == 0. => {}
            // Preserve the literal spacerun text; do not collapse its spaces.
            "xfa-spacerun" if value == "yes" => {}
            other => bail!("Unsupported rich-text style property: {other}"),
        }
    }
    Ok(())
}

pub fn metadata(ds: &str, rv: &str, font: &str, size: f64, alignment: i64) -> Result<Value> {
    let mut defaults = json!({"alignment":match alignment {1=>"center",2=>"right",_=>"left"},"fontFamily":[font],"fontStretch":"normal","fontStyle":"normal","fontWeight":400,"textColor":["RGB",0,0,0],"textSize":size}).as_object().unwrap().clone();
    css(&mut defaults, ds)?;
    let spans = if rv.is_empty() {
        vec![]
    } else {
        parse(rv, &defaults)?
    };
    Ok(json!({"defaultStyle":defaults,"spans":spans}))
}

fn parse(xml: &str, defaults: &Style) -> Result<Vec<Value>> {
    struct Frame {
        tag: String,
        style: Style,
        first_span: usize,
        spacerun: bool,
    }
    fn flush(text: &mut String, style: &Style, spacerun: bool, spans: &mut Vec<Value>) {
        if !text.is_empty() {
            let mut span = style.clone();
            let value = std::mem::take(text);
            span.insert(
                "text".into(),
                json!(if spacerun {
                    value.replace('\u{a0}', " ")
                } else {
                    value
                }),
            );
            spans.push(Value::Object(span));
        }
    }
    let mut reader = Reader::from_str(xml);
    reader.config_mut().expand_empty_elements = true;
    let mut stack: Vec<Frame> = vec![];
    let mut spans = vec![];
    let mut text = String::new();
    let mut in_paragraph = false;
    loop {
        match reader.read_event()? {
            Event::Start(node) => {
                // All source rich values use non-empty body/p/span elements.
                // Empty XML elements still receive normal paragraph handling.
                if in_paragraph {
                    flush(
                        &mut text,
                        &stack.last().context("Missing rich-text parent")?.style,
                        stack.last().unwrap().spacerun,
                        &mut spans,
                    );
                }
                let tag = String::from_utf8(node.local_name().as_ref().to_vec())?;
                if !matches!(tag.as_str(), "body" | "p" | "span") {
                    bail!("Unsupported rich-text element: {tag}")
                }
                let mut style = stack
                    .last()
                    .map(|f| f.style.clone())
                    .unwrap_or_else(|| defaults.clone());
                style.insert("acrobatmarkup".into(), json!(false));
                if tag == "p" {
                    if in_paragraph {
                        bail!("Nested rich-text paragraph")
                    }
                    in_paragraph = true;
                }
                let mut spacerun = stack.last().is_some_and(|f| f.spacerun);
                for attr in node.attributes() {
                    let attr = attr?;
                    let value = attr.normalized_value(XmlVersion::Implicit1_0)?;
                    match attr.key.local_name().as_ref() {
                        b"style" => {
                            css(&mut style, &value)?;
                            spacerun |= value.split(';').any(|s| {
                                s.split_once(':').is_some_and(|(key, value)| {
                                    key.trim() == "xfa-spacerun" && value.trim() == "yes"
                                })
                            });
                        }
                        b"dir" => {
                            style.insert("paradir".into(), json!(value));
                        }
                        _ => {}
                    }
                }
                stack.push(Frame {
                    tag,
                    style,
                    first_span: spans.len(),
                    spacerun,
                });
            }
            Event::End(_) => {
                let frame = stack.pop().context("Unbalanced rich-text XML")?;
                if in_paragraph {
                    flush(&mut text, &frame.style, frame.spacerun, &mut spans);
                }
                if frame.tag == "p" {
                    if spans.len() == frame.first_span {
                        let mut empty = frame.style;
                        empty.insert("text".into(), json!(""));
                        spans.push(Value::Object(empty));
                    }
                    spans.last_mut().unwrap()["endParagraph"] = json!(true);
                    in_paragraph = false;
                }
            }
            Event::Text(node) if in_paragraph => text.push_str(&node.decode()?),
            Event::CData(node) if in_paragraph => text.push_str(&node.decode()?),
            Event::GeneralRef(node) if in_paragraph => {
                if let Some(c) = node.resolve_char_ref()? {
                    text.push(c);
                } else {
                    text.push_str(match node.decode()?.as_ref() {
                        "amp" => "&",
                        "lt" => "<",
                        "gt" => ">",
                        "quot" => "\"",
                        "apos" => "'",
                        _ => bail!("Unsupported rich-text entity"),
                    });
                }
            }
            Event::Decl(node) if node.version()?.as_ref() != b"1.0" => {
                bail!("Unsupported rich-text XML version")
            }
            Event::DocType(_) => bail!("Unsupported rich-text document type"),
            Event::Eof => break,
            _ => {}
        }
    }
    if !stack.is_empty() {
        bail!("Unbalanced rich-text XML")
    }
    if let Some(last) = spans.last_mut().and_then(Value::as_object_mut) {
        last.remove("endParagraph");
    }
    Ok(spans)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn default_style_and_xml_spaceruns_keep_source_styles_and_paragraphs() {
        let value = metadata("font: italic bold 'Demo Sans',sans-serif 7pt; color:#000000; text-align:left", "<body><p dir='ltr' style=\"line-height:11pt;font-family:'Demo Sans'\">Heading &amp; text</p><p dir='ltr'><span style='xfa-spacerun:yes'> &#160;</span>body&#160;text</p></body>", "Helvetica", 0., 0).unwrap();
        assert_eq!(
            value["defaultStyle"]["fontFamily"],
            json!(["Demo Sans", "sans-serif"])
        );
        assert_eq!(value["defaultStyle"]["fontWeight"], 700);
        assert_eq!(value["spans"].as_array().unwrap().len(), 3);
        assert_eq!(value["spans"][0]["text"], "Heading & text");
        assert_eq!(value["spans"][0]["endParagraph"], true);
        assert_eq!(value["spans"][0]["linespacing"], 11.);
        assert_eq!(value["spans"][1]["text"], "  ");
        assert_eq!(value["spans"][2]["text"], "body\u{a0}text");
        assert!(value["spans"][2].get("endParagraph").is_none());
    }
    #[test]
    fn rich_color_channels_match_reader_css_fixed_point_conversion() {
        let value = metadata("color:#4080BF", "", "Helvetica", 7., 0).unwrap();
        assert_eq!(
            value["defaultStyle"]["textColor"],
            json!(["RGB", 0.2509765625, 0.5019683837890625, 0.7490234375])
        );
    }
    #[test]
    fn empty_paragraphs_and_span_boundaries_remain_distinct() {
        let value = metadata(
            "",
            "<body><p/><p>A<span>B</span>C</p></body>",
            "Helvetica",
            7.,
            0,
        )
        .unwrap();
        let spans = value["spans"].as_array().unwrap();
        assert_eq!(spans.len(), 4);
        assert_eq!(spans[0]["text"], "");
        assert_eq!(spans[0]["endParagraph"], true);
        assert_eq!(spans[1]["text"], "A");
        assert_eq!(spans[2]["text"], "B");
        assert_eq!(spans[3]["text"], "C");
        assert!(spans[3].get("endParagraph").is_none());
    }
    #[test]
    fn unsupported_styles_and_entities_are_explicit() {
        assert!(metadata("letter-spacing:3pt", "", "Helvetica", 7., 0).is_err());
        assert!(metadata("", "<body><p>&external;</p></body>", "Helvetica", 7., 0).is_err());
    }
}
