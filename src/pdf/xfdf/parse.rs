//! Extract form data without mutating a document or following XFDF links.
use anyhow::{bail, Context, Result};
use quick_xml::{events::Event, Reader, XmlVersion};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub(crate) struct ImportedField {
    pub name: String,
    pub values: Vec<String>,
    pub rich_xml: Option<String>,
}
#[derive(Default)]
struct Field {
    name: String,
    values: Vec<String>,
    rich_xml: Option<String>,
    children: usize,
}

pub(crate) fn read(xml: &str) -> Result<Vec<ImportedField>> {
    let xml = xml.strip_prefix('\u{feff}').unwrap_or(xml);
    let mut reader = Reader::from_str(xml);
    reader.config_mut().expand_empty_elements = true;
    let mut tags: Vec<String> = vec![];
    let mut fields: Vec<Field> = vec![];
    let mut output = vec![];
    let mut rich_capture: Option<(usize, usize)> = None;
    let mut root_seen = false;
    loop {
        let before = reader.buffer_position() as usize;
        let event = reader.read_event()?;
        if let Some((start, depth)) = &mut rich_capture {
            match &event {
                Event::Start(_) => *depth += 1,
                Event::End(_) => {
                    *depth -= 1;
                    if *depth == 0 {
                        fields
                            .last_mut()
                            .context("Rich data outside a field")?
                            .rich_xml =
                            Some(xml[*start..reader.buffer_position() as usize].to_owned());
                        rich_capture = None;
                    }
                }
                Event::DocType(_) | Event::Decl(_) => {
                    bail!("Unsupported declaration inside rich XFDF data")
                }
                Event::Eof => bail!("Unclosed rich XFDF data"),
                _ => {}
            }
            continue;
        }
        match event {
            Event::Start(node) => {
                let tag = std::str::from_utf8(node.name().as_ref())?.to_owned();
                match (tags.last().map(String::as_str), tag.as_str()) {
                    (None, "xfdf") if !root_seen => {
                        let mut namespace = None;
                        for attr in node.attributes() {
                            let attr = attr?;
                            if attr.key.as_ref() == b"xmlns" {
                                namespace = Some(
                                    attr.normalized_value(XmlVersion::Implicit1_0)?.into_owned(),
                                );
                            }
                        }
                        if namespace.as_deref() != Some("http://ns.adobe.com/xfdf/") {
                            bail!("Unsupported XFDF namespace")
                        }
                        root_seen = true;
                    }
                    (Some("xfdf"), "f" | "ids" | "fields") => {}
                    (Some("fields" | "field"), "field") => {
                        let mut name = None;
                        for attr in node.attributes() {
                            let attr = attr?;
                            if attr.key.as_ref() == b"name" {
                                name = Some(
                                    attr.normalized_value(XmlVersion::Implicit1_0)?.into_owned(),
                                );
                            }
                        }
                        let name = name
                            .filter(|s| !s.is_empty())
                            .context("Missing XFDF field name")?;
                        if let Some(parent) = fields.last_mut() {
                            parent.children += 1;
                        }
                        fields.push(Field {
                            name,
                            ..Default::default()
                        });
                    }
                    (Some("field"), "value") => fields
                        .last_mut()
                        .context("Value outside a field")?
                        .values
                        .push(String::new()),
                    (Some("field"), "value-richtext") => {
                        if fields
                            .last()
                            .context("Rich value outside a field")?
                            .rich_xml
                            .is_some()
                        {
                            bail!("Multiple rich values for a field")
                        }
                    }
                    (Some("value-richtext"), "body") => {
                        rich_capture = Some((before, 1));
                        continue;
                    }
                    _ => bail!("Unsupported XFDF element: {tag}"),
                }
                tags.push(tag);
            }
            Event::End(node) => {
                let tag = std::str::from_utf8(node.name().as_ref())?.to_owned();
                if tags.pop().as_deref() != Some(&tag) {
                    bail!("Mismatched XFDF element")
                }
                if tag == "field" {
                    let field = fields.pop().context("Missing XFDF field")?;
                    if field.children == 0 || !field.values.is_empty() || field.rich_xml.is_some() {
                        let name = fields
                            .iter()
                            .map(|f| f.name.as_str())
                            .chain(std::iter::once(field.name.as_str()))
                            .collect::<Vec<_>>()
                            .join(".");
                        output.push(ImportedField {
                            name,
                            values: field.values,
                            rich_xml: field.rich_xml,
                        });
                    }
                }
            }
            Event::Text(node) => {
                let text = node.xml10_content()?;
                if tags.last().is_some_and(|tag| tag == "value") {
                    fields
                        .last_mut()
                        .and_then(|f| f.values.last_mut())
                        .context("Missing XFDF value")?
                        .push_str(&text);
                } else if !text.trim().is_empty() {
                    bail!("Unexpected XFDF text")
                }
            }
            Event::CData(node) if tags.last().is_some_and(|tag| tag == "value") => fields
                .last_mut()
                .and_then(|f| f.values.last_mut())
                .context("Missing XFDF value")?
                .push_str(&node.xml10_content()?),
            Event::GeneralRef(node) if tags.last().is_some_and(|tag| tag == "value") => {
                let value = fields
                    .last_mut()
                    .and_then(|f| f.values.last_mut())
                    .context("Missing XFDF value")?;
                if let Some(c) = node.resolve_char_ref()? {
                    value.push(c);
                } else {
                    value.push_str(match node.decode()?.as_ref() {
                        "amp" => "&",
                        "lt" => "<",
                        "gt" => ">",
                        "quot" => "\"",
                        "apos" => "'",
                        _ => bail!("Unsupported XFDF entity"),
                    });
                }
            }
            Event::Decl(node) => {
                if node.version()?.as_ref() != b"1.0" {
                    bail!("Unsupported XFDF XML version")
                }
                if let Some(encoding) = node.encoding() {
                    if !encoding?.eq_ignore_ascii_case(b"utf-8") {
                        bail!("XFDF import requires UTF-8")
                    }
                }
            }
            Event::DocType(_) => bail!("XFDF document types are unsupported"),
            Event::Eof => break,
            Event::Comment(_) | Event::PI(_) => {}
            _ => bail!("Unsupported XFDF content"),
        }
    }
    if !root_seen || !tags.is_empty() || !fields.is_empty() {
        bail!("Incomplete XFDF document")
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_values_and_absent_values_remain_distinct() {
        let xml = "<xfdf xmlns=\"http://ns.adobe.com/xfdf/\"><fields><field name=\"Attack\"><field name=\"1\"><field name=\"empty\"/><field name=\"text\"><value/></field><field name=\"choice\"><value>A&amp;B</value><value>Ω</value></field></field></field></fields></xfdf>";
        let fields = read(xml).unwrap();
        assert_eq!(fields[0].name, "Attack.1.empty");
        assert!(fields[0].values.is_empty());
        assert_eq!(fields[1].values, [""]);
        assert_eq!(fields[2].values, ["A&B", "Ω"]);
    }
    #[test]
    fn rich_xml_stays_intact_and_plain_xml_newlines_normalize() {
        let body = "<body xmlns=\"http://www.w3.org/1999/xhtml\"><p><span style=\"font-weight:bold\">A&#13;Ω</span></p></body>";
        let xml = format!("<xfdf xmlns=\"http://ns.adobe.com/xfdf/\"><fields><field name=\"plain\"><value>A\r\nB&#13;C</value></field><field name=\"rich\"><value-richtext>{body}</value-richtext></field></fields></xfdf>");
        let fields = read(&xml).unwrap();
        assert_eq!(fields[0].values, ["A\nB\rC"]);
        assert_eq!(fields[1].rich_xml.as_deref(), Some(body));
    }
    #[test]
    fn malformed_or_unqualified_data_is_rejected() {
        for xml in [
            "<xfdf/>",
            "<xfdf xmlns=\"wrong\"/>",
            "<!DOCTYPE xfdf><xfdf xmlns=\"http://ns.adobe.com/xfdf/\"/>",
            "<xfdf xmlns=\"http://ns.adobe.com/xfdf/\"><fields>",
            "<xfdf xmlns=\"http://ns.adobe.com/xfdf/\"><annots/></xfdf>",
        ] {
            assert!(read(xml).is_err(), "{xml}");
        }
    }
}
