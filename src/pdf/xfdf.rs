//! Read-only XFDF serialization of the authoritative runtime's field values.
use anyhow::{bail, Context, Result};
use quick_xml::events::{BytesDecl, BytesEnd, BytesStart, BytesText, Event};
use quick_xml::Writer;
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Default)]
struct Node {
    field: Option<Value>,
    children: BTreeMap<String, Node>,
}
fn valid_xml(text: &str) -> Result<()> {
    if text.chars().any(
        |c| !matches!(c as u32, 9 | 10 | 13 | 0x20..=0xd7ff | 0xe000..=0xfffd | 0x10000..=0x10ffff),
    ) {
        bail!("XFDF contains a character forbidden by XML 1.0")
    }
    Ok(())
}
fn write_nodes(writer: &mut Writer<Vec<u8>>, nodes: &BTreeMap<String, Node>) -> Result<()> {
    for (name, node) in nodes {
        valid_xml(name)?;
        let mut start = BytesStart::new("field");
        start.push_attribute(("name", name.as_str()));
        writer.write_event(Event::Start(start))?;
        if let Some(field) = &node.field {
            let values = match field.get("value").context("Missing XFDF field value")? {
                Value::String(s) => vec![s.as_str()],
                Value::Array(items) => items
                    .iter()
                    .map(|v| v.as_str().context("Invalid XFDF choice value"))
                    .collect::<Result<Vec<_>>>()?,
                _ => bail!("Invalid XFDF field value"),
            };
            let rich = field["rich"].as_array().filter(|v| !v.is_empty());
            // Rich fields export their markup instead of a competing value.
            // An unselected combo is represented by a field with no value.
            for text in values.into_iter().filter(|_| rich.is_none()) {
                if text.is_empty() && field["type"] == "combobox" {
                    continue;
                }
                valid_xml(text)?;
                writer.write_event(Event::Start(BytesStart::new("value")))?;
                // Reader emits plain field line endings as literal CRLF;
                // XML parsers then normalize them to LF. Rich markup below
                // instead protects its CR code units with character references.
                let escaped = quick_xml::escape::escape(text)
                    .replace("\r\n", "\n")
                    .replace('\r', "\n")
                    .replace('\n', "\r\n");
                writer.write_event(Event::Text(BytesText::from_escaped(escaped)))?;
                writer.write_event(Event::End(BytesEnd::new("value")))?;
            }
            if let Some(spans) = rich {
                let xml = super::rich_text::serialize(spans, &field["defaultStyle"])?;
                let body = xml
                    .split_once("?>")
                    .context("Missing rich XML declaration")?
                    .1;
                writer.write_event(Event::Start(BytesStart::new("value-richtext")))?;
                writer.get_mut().extend_from_slice(body.as_bytes());
                writer.write_event(Event::End(BytesEnd::new("value-richtext")))?;
            }
        }
        write_nodes(writer, &node.children)?;
        writer.write_event(Event::End(BytesEnd::new("field")))?;
    }
    Ok(())
}

pub(crate) fn export(request: &Value) -> Result<String> {
    let options = &request["options"];
    if !options.is_object() {
        bail!("XFDF options must be an object")
    }
    if options["bAnnotations"] == true {
        bail!("XFDF annotation export is unsupported")
    }
    let selected = match options.get("aFields") {
        None | Some(Value::Null) => None,
        Some(Value::String(name)) => Some(vec![name.as_str()]),
        Some(Value::Array(names)) => Some(
            names
                .iter()
                .map(|n| n.as_str().context("Invalid XFDF field selection"))
                .collect::<Result<Vec<_>>>()?,
        ),
        _ => bail!("Invalid XFDF field selection"),
    };
    let mut root = Node::default();
    for field in request["fields"]
        .as_array()
        .context("Missing XFDF fields")?
    {
        let name = field["name"].as_str().context("Missing XFDF field name")?;
        let flags = field["flags"].as_u64().unwrap_or(0);
        if field["type"] == "button"
            || flags & 4 != 0
            || (options["bNoPassword"] != false && flags & 8192 != 0)
        {
            continue;
        }
        if selected.as_ref().is_some_and(|names| {
            !names.iter().any(|s| {
                name == *s
                    || name
                        .strip_prefix(s)
                        .is_some_and(|tail| tail.starts_with('.'))
            })
        }) {
            continue;
        }
        if options["bAllFields"] != true && field["value"] == "" && field["type"] != "combobox" {
            continue;
        }
        let mut node = &mut root;
        for part in name.split('.') {
            node = node.children.entry(part.to_owned()).or_default();
        }
        node.field = Some(field.clone());
    }
    let href = options
        .get("cHRef")
        .unwrap_or(&request["href"])
        .as_str()
        .context("Invalid XFDF href")?;
    valid_xml(href)?;
    let mut writer = Writer::new(Vec::new());
    writer.write_event(Event::Decl(BytesDecl::new("1.0", Some("UTF-8"), None)))?;
    let mut start = BytesStart::new("xfdf");
    start.push_attribute(("xmlns", "http://ns.adobe.com/xfdf/"));
    start.push_attribute(("xml:space", "preserve"));
    writer.write_event(Event::Start(start))?;
    let mut file = BytesStart::new("f");
    file.push_attribute(("href", href));
    writer.write_event(Event::Empty(file))?;
    if !root.children.is_empty() {
        writer.write_event(Event::Start(BytesStart::new("fields")))?;
        write_nodes(&mut writer, &root.children)?;
        writer.write_event(Event::End(BytesEnd::new("fields")))?;
    }
    writer.write_event(Event::End(BytesEnd::new("xfdf")))?;
    Ok(String::from_utf8(writer.into_inner())?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn fields() -> Value {
        json!([
            {"name":"Attack.1.Weapon", "type":"text", "value":""},
            {"name":"Attack.1.Weapon Selection", "type":"combobox", "value":""},
            {"name":"Attack.1.Proficiency", "type":"checkbox", "value":"Off"},
            {"name":"Other", "type":"text", "value":"not selected"},
            {"name":"Button", "type":"button", "value":"caption"},
            {"name":"Secret", "type":"text", "flags":8192, "value":"password"},
            {"name":"Excluded", "type":"text", "flags":4, "value":"not exportable"}
        ])
    }
    #[test]
    fn subtree_selection_keeps_unselected_combo_and_checkbox_but_omits_empty_text() {
        let request =
            json!({"options":{"aFields":"Attack.1"},"fields":fields(),"href":"sheet.pdf"});
        let xml = export(&request).unwrap();
        assert!(xml.contains("<field name=\"Attack\"><field name=\"1\">"));
        assert!(xml.contains("<field name=\"Weapon Selection\"></field>"));
        assert!(xml.contains("<value>Off</value>"));
        assert!(!xml.contains("name=\"Weapon\""));
        assert!(!xml.contains("not selected"));
        let mut all = request;
        all["options"]["bAllFields"] = json!(true);
        assert!(export(&all)
            .unwrap()
            .contains("<field name=\"Weapon\"><value></value>"));
        all["options"]["aFields"] = json!([]);
        assert!(!export(&all).unwrap().contains("<fields>"));
    }
    #[test]
    fn field_values_and_href_escape_xml_and_preserve_unicode_without_exporting_secrets() {
        let mut items = fields();
        items
            .as_array_mut()
            .unwrap()
            .push(json!({"name":"A & \"quoted\"", "type":"text", "value":"0012 <&> é Ω😀"}));
        let mut request = json!({"options":{"cHRef":"a&\"b"},"href":"unused", "fields":items});
        let xml = export(&request).unwrap();
        assert!(xml.contains("href=\"a&amp;&quot;b\""));
        assert!(xml.contains("name=\"A &amp; &quot;quoted&quot;\""));
        assert!(xml.contains("0012 &lt;&amp;&gt; é Ω😀"));
        assert!(
            !xml.contains("password")
                && !xml.contains("caption")
                && !xml.contains("not exportable")
        );
        request["options"]["bNoPassword"] = json!(false);
        assert!(export(&request).unwrap().contains("password"));
    }
    #[test]
    fn rich_export_emits_one_value_richtext_with_protected_line_breaks() {
        let request = json!({"options":{},"href":"sheet.pdf", "fields":[{"name":"Notes.Left", "type":"text", "value":"first\rsecond", "rich":[{"text":"first\r", "fontWeight":700},{"text":"second"}], "defaultStyle":{"fontFamily":["Helvetica"],"textSize":7,"fontWeight":400}}]});
        let xml = export(&request).unwrap();
        assert!(!xml.contains("<value>"));
        assert_eq!(xml.matches("<value-richtext>").count(), 1);
        assert_eq!(xml.matches("<?xml").count(), 1);
        assert!(xml.contains("first&#13;") && xml.contains("font-weight:bold"));
    }
    #[test]
    fn invalid_xml_and_unsupported_annotations_fail_instead_of_losing_data() {
        let mut request = json!({"options":{},"href":"sheet.pdf", "fields":[{"name":"A", "type":"text", "value":"before\u{0}after"}]});
        assert!(export(&request)
            .unwrap_err()
            .to_string()
            .contains("XML 1.0"));
        request["fields"] = json!([]);
        request["options"]["bAnnotations"] = json!(true);
        assert!(export(&request)
            .unwrap_err()
            .to_string()
            .contains("annotation"));
        request["options"] = json!({"aFields":3});
        assert!(export(&request).is_err());
    }
    #[test]
    fn plain_multiline_values_use_reader_crlf_without_changing_tabs_or_empty_lines() {
        let request = json!({"options":{},"href":"sheet.pdf", "fields":[{"name":"A", "type":"text", "value":"\rfirst\r\nsecond\t<&>\r"}]});
        let xml = export(&request).unwrap();
        assert!(xml.contains("<value>\r\nfirst\r\nsecond\t&lt;&amp;&gt;\r\n</value>"));
    }
}
