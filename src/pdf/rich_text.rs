//! Source rich-text metadata, kept separate from appearances and canonical /V.
use anyhow::{bail, Context, Result};
use quick_xml::{
    events::{BytesDecl, BytesEnd, BytesStart, BytesText, Event},
    Reader, Writer, XmlVersion,
};
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
                style.insert("fontStretch".into(), json!(value.to_ascii_lowercase()));
            }
            "text-align" => {
                style.insert("alignment".into(), json!(value));
            }
            "color" => {
                style.insert("textColor".into(), color(value)?);
            }
            "text-decoration" => {
                for decoration in value.split_whitespace() {
                    match decoration {
                        "none" => {}
                        "underline" => {
                            style.insert("underline".into(), json!(true));
                        }
                        "line-through" => {
                            style.insert("strikethrough".into(), json!(true));
                        }
                        _ => bail!("Unsupported rich-text decoration"),
                    }
                }
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
    let mut legacy_markup = false;
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
                        b"APIVersion" if tag == "body" => {
                            legacy_markup = value == "Acroform:2.7.0.0";
                        }
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
                if legacy_markup {
                    style.insert("acrobatmarkup".into(), json!(false));
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

/// Emit the vocabulary used by the authorized rich fields. Unknown attributes
/// fail rather than silently discarding user formatting.
pub fn style_css(style: &Value) -> Result<String> {
    let mut declarations = vec![];
    if let Some(families) = style["fontFamily"].as_array() {
        let mut names = vec![];
        for family in families {
            let name = family.as_str().context("Invalid rich font family")?;
            if name.is_empty()
                || name.contains(['\'', '"', ';', '\\'])
                || name.chars().any(char::is_control)
            {
                bail!("Unsupported rich font family syntax")
            }
            names.push(
                if ["serif", "sans-serif", "monospace", "cursive", "fantasy"].contains(&name) {
                    name.to_owned()
                } else {
                    format!("'{name}'")
                },
            );
        }
        if names.is_empty() {
            bail!("Missing rich font family")
        }
        declarations.push(format!("font-family:{}", names.join(",")));
    }
    if let Some(size) = style.get("textSize") {
        let n = size.as_f64().context("Invalid rich text size")?;
        if !n.is_finite() || n < 0. {
            bail!("Invalid rich text size")
        }
        declarations.push(format!("font-size:{n}pt"));
    }
    if let Some(weight) = style.get("fontWeight") {
        let n = weight.as_u64().context("Invalid rich font weight")?;
        let keyword = match n {
            400 => "normal",
            700 => "bold",
            _ => bail!("Unsupported persisted rich font weight: {n}"),
        };
        declarations.push(format!("font-weight:{keyword}"));
    }
    for (property, css, allowed) in [
        (
            "fontStyle",
            "font-style",
            &["normal", "italic", "oblique"][..],
        ),
        (
            "fontStretch",
            "font-stretch",
            &[
                "normal",
                "ultra-condensed",
                "extra-condensed",
                "condensed",
                "semi-condensed",
                "semi-expanded",
                "expanded",
                "extra-expanded",
                "ultra-expanded",
            ][..],
        ),
        (
            "alignment",
            "text-align",
            &["left", "center", "right", "justify"][..],
        ),
    ] {
        if let Some(value) = style.get(property) {
            let value = value.as_str().context("Invalid rich style keyword")?;
            if !allowed.contains(&value) {
                bail!("Unsupported rich style keyword for {property}")
            }
            declarations.push(format!("{css}:{value}"));
        }
    }
    if let Some(color) = style.get("textColor") {
        let color = color.as_array().context("Invalid rich color")?;
        let channels = match color.first().and_then(Value::as_str) {
            Some("RGB") if color.len() == 4 => vec![&color[1], &color[2], &color[3]],
            Some("G") if color.len() == 2 => vec![&color[1]; 3],
            _ => bail!("Unsupported rich color space"),
        };
        let mut hex = String::new();
        for value in channels {
            let n = value.as_f64().context("Invalid rich color channel")?;
            if !n.is_finite() || !(0.0..=1.0).contains(&n) {
                bail!("Invalid rich color channel")
            }
            hex.push_str(&format!("{:02X}", (n * 255.).round() as u8));
        }
        declarations.push(format!("color:#{hex}"));
    }
    if let Some(spacing) = style.get("linespacing") {
        let n = spacing.as_f64().context("Invalid rich line spacing")?;
        if !n.is_finite() || n < 0. {
            bail!("Invalid rich line spacing")
        }
        declarations.push(format!("line-height:{n}pt"));
    }
    let mut decorations = vec![];
    if style["underline"] == true {
        decorations.push("underline")
    }
    if style["strikethrough"] == true {
        decorations.push("line-through")
    }
    if decorations.is_empty()
        && (style.get("underline").is_some() || style.get("strikethrough").is_some())
    {
        declarations.push("text-decoration:none".into());
    }
    if !decorations.is_empty() {
        declarations.push(format!("text-decoration:{}", decorations.join(" ")))
    }
    let order = [
        "font-size",
        "text-align",
        "color",
        "font-weight",
        "font-style",
        "font-family",
        "font-stretch",
    ];
    declarations.sort_by_key(|item| {
        order
            .iter()
            .position(|key| item.starts_with(&format!("{key}:")))
            .unwrap_or(order.len())
    });
    Ok(declarations.join(";"))
}

pub fn serialize(spans: &[Value], defaults: &Value) -> Result<String> {
    let mut writer = Writer::new(Vec::new());
    writer.write_event(Event::Decl(BytesDecl::new("1.0", None, None)))?;
    let mut body = BytesStart::new("body");
    body.push_attribute(("xmlns", "http://www.w3.org/1999/xhtml"));
    body.push_attribute(("xmlns:xfa", "http://www.xfa.org/schema/xfa-data/1.0/"));
    // Reader discards otherwise valid markup with unrecognized producer API
    // strings. Omit that optional metadata rather than impersonating Acrobat.
    // See rich-markup-version-variants-1793177445319387582.
    body.push_attribute(("xfa:spec", "2.0.2"));
    let body_css = style_css(defaults)?;
    body.push_attribute(("style", body_css.as_str()));
    writer.write_event(Event::Start(body))?;

    let mut paragraph = false;
    let mut paragraph_properties = Value::Null;
    for (index, span) in spans.iter().enumerate() {
        let object = span.as_object().context("Invalid rich span")?;
        for key in object.keys() {
            if ![
                "acrobatmarkup",
                "alignment",
                "endParagraph",
                "fontFamily",
                "fontStretch",
                "fontStyle",
                "fontWeight",
                "linespacing",
                "paradir",
                "text",
                "textColor",
                "textSize",
                "underline",
                "strikethrough",
            ]
            .contains(&key.as_str())
            {
                bail!("Unsupported stored rich span property: {key}")
            }
        }
        let text = span["text"].as_str().context("Missing rich span text")?;
        if text
            .chars()
            .any(|c| c.is_control() && !['\t', '\n', '\r'].contains(&c))
        {
            bail!("Unsupported rich-text control character")
        }
        let direction = span["paradir"].as_str().unwrap_or("ltr");
        if !["ltr", "rtl"].contains(&direction) {
            bail!("Unsupported rich paragraph direction")
        }
        let properties = json!({"alignment":span.get("alignment").or_else(|| defaults.get("alignment")),"linespacing":span.get("linespacing").or_else(|| defaults.get("linespacing"))});
        if paragraph && paragraph_properties != properties {
            bail!("Mixed alignment or line spacing inside a rich paragraph is not supported")
        }
        if !paragraph {
            paragraph_properties = properties;
            let mut p = BytesStart::new("p");
            if span.get("paradir").is_some() {
                p.push_attribute(("dir", direction));
            }
            let mut paragraph_style = Map::new();
            for key in ["alignment", "linespacing"] {
                if let Some(value) = span.get(key).filter(|v| defaults.get(key) != Some(*v)) {
                    paragraph_style.insert(key.into(), value.clone());
                }
            }
            let paragraph_css = style_css(&Value::Object(paragraph_style))?;
            if !paragraph_css.is_empty() {
                p.push_attribute(("style", paragraph_css.as_str()));
            }
            writer.write_event(Event::Start(p))?;
            paragraph = true;
        }
        let mut character_style = object.clone();
        character_style.retain(|key, value| {
            !["alignment", "linespacing"].contains(&key.as_str())
                && defaults.get(key) != Some(value)
        });
        let css = style_css(&Value::Object(character_style))?;
        let mut node = BytesStart::new("span");
        node.push_attribute(("style", css.as_str()));
        if span.get("paradir").is_some() {
            node.push_attribute(("dir", direction));
        }
        writer.write_event(Event::Start(node))?;
        let escaped = quick_xml::escape::escape(text)
            .replace('\r', "&#13;")
            .replace('\n', "&#10;")
            .replace('\t', "&#9;");
        writer.write_event(Event::Text(BytesText::from_escaped(escaped)))?;
        writer.write_event(Event::End(BytesEnd::new("span")))?;
        if span["endParagraph"] == true && index + 1 < spans.len() {
            writer.write_event(Event::End(BytesEnd::new("p")))?;
            paragraph = false;
        }
    }
    if paragraph {
        writer.write_event(Event::End(BytesEnd::new("p")))?;
    }
    writer.write_event(Event::End(BytesEnd::new("body")))?;
    Ok(String::from_utf8(writer.into_inner())?.replace("&apos;", "'"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reader_default_style_font_stretch_keyword_is_case_insensitive() {
        let value = metadata(
            "font: Helvetica 9.0pt;font-stretch:Normal; text-align:right; color:#0000FF",
            "",
            "Helvetica",
            9.,
            2,
        )
        .unwrap();
        assert_eq!(value["defaultStyle"]["fontStretch"], "normal");
    }
    #[test]
    fn edited_xml_roundtrip_preserves_spans_styles_boundaries_and_entities() {
        let defaults =
            metadata("color:#000000", "", "Helvetica", 7., 0).unwrap()["defaultStyle"].clone();
        let mut spans = vec![defaults.clone(), defaults.clone()];
        spans[0]["text"] = json!("  A<&\"\r\n\tB  ");
        spans[0]["endParagraph"] = json!(true);
        spans[0]["underline"] = json!(true);
        spans[0]["strikethrough"] = json!(true);
        spans[0]["fontWeight"] = json!(700);
        spans[1]["text"] = json!("Second");
        let xml = serialize(&spans, &defaults).unwrap();
        let loaded = metadata(&style_css(&defaults).unwrap(), &xml, "Helvetica", 7., 0).unwrap();
        assert_eq!(loaded["spans"], json!(spans));
        assert_eq!(loaded["defaultStyle"], defaults);
        assert!(serialize(&[json!({"text":"A","unsupported":true})], &defaults).is_err());
        assert!(serialize(&[json!({"text":"\u{0001}"})], &defaults).is_err());
        assert!(serialize(
            &[
                json!({"text":"A","alignment":"left"}),
                json!({"text":"B","alignment":"right"})
            ],
            &defaults
        )
        .is_err());
        assert!(serialize(&[], &defaults).unwrap().ends_with("</body>"));
    }
    #[test]
    fn legacy_marker_is_not_added_to_current_reader_markup() {
        let legacy = metadata("", "<body xmlns:xfa='http://www.xfa.org/schema/xfa-data/1.0/' xfa:APIVersion='Acroform:2.7.0.0'><p>text</p></body>", "Helvetica", 7., 0).unwrap();
        let current = metadata("", "<body><p>text</p></body>", "Helvetica", 7., 0).unwrap();
        assert_eq!(legacy["spans"][0]["acrobatmarkup"], false);
        assert!(current["spans"][0].get("acrobatmarkup").is_none());
        assert!(current["spans"][0].get("paradir").is_none());
    }
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
