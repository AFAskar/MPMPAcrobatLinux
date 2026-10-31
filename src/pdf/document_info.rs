//! Read the XMP properties exposed alongside the PDF information dictionary.
use anyhow::{bail, Context, Result};
use lopdf::{Dictionary, Document};
use quick_xml::{events::Event, name::ResolveResult, NsReader, XmlVersion};
use serde_json::{json, Map, Value};

const DC: &[u8] = b"http://purl.org/dc/elements/1.1/";
const RDF: &[u8] = b"http://www.w3.org/1999/02/22-rdf-syntax-ns#";
const AC: &[u8] = b"http://ns.adobe.com/AcrobatCollab/6.0/";

#[derive(Default, Debug, PartialEq)]
struct Overlay {
    authors: Option<Vec<String>>,
    contact_email: Option<String>,
}
enum Kind {
    Author,
    Email,
}
struct Capture {
    kind: Kind,
    depth: usize,
    value: String,
}

fn parse(xml: &[u8]) -> Result<Overlay> {
    let mut reader = NsReader::from_reader(xml);
    reader.config_mut().expand_empty_elements = true;
    let mut result = Overlay::default();
    let mut tags: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
    let mut capture: Option<Capture> = None;
    loop {
        let (namespace, event) = reader.read_resolved_event()?;
        let namespace = match namespace {
            ResolveResult::Bound(ns) => ns.as_ref().to_vec(),
            _ => Vec::new(),
        };
        match event {
            Event::Start(node) => {
                if capture.is_some() {
                    bail!("Nested XMP author/contact content is unsupported")
                }
                for attribute in node.attributes() {
                    let attribute = attribute?;
                    let (ns, name) = reader.resolver().resolve_attribute(attribute.key);
                    if matches!(ns, ResolveResult::Bound(ns) if ns.as_ref() == AC)
                        && name.as_ref() == b"ContactEmail"
                    {
                        result.contact_email = Some(
                            attribute
                                .decoded_and_normalized_value(
                                    XmlVersion::Implicit1_0,
                                    reader.decoder(),
                                )?
                                .into_owned(),
                        );
                    }
                }
                let name = node.local_name().as_ref().to_vec();
                if namespace == DC && name == b"creator" {
                    result.authors = Some(Vec::new());
                }
                let author = namespace == RDF
                    && name == b"li"
                    && tags.iter().any(|(ns, tag)| ns == DC && tag == b"creator");
                let email = namespace == AC && name == b"ContactEmail";
                tags.push((namespace, name));
                if author || email {
                    capture = Some(Capture {
                        kind: if author { Kind::Author } else { Kind::Email },
                        depth: tags.len(),
                        value: String::new(),
                    });
                }
            }
            Event::End(_) => {
                if capture.as_ref().is_some_and(|c| c.depth == tags.len()) {
                    let captured = capture.take().unwrap();
                    match captured.kind {
                        Kind::Author => result.authors.as_mut().unwrap().push(captured.value),
                        Kind::Email => result.contact_email = Some(captured.value),
                    }
                }
                tags.pop().context("Unbalanced XMP metadata")?;
            }
            Event::Text(node) => {
                if let Some(capture) = &mut capture {
                    capture.value.push_str(&node.xml10_content()?);
                }
            }
            Event::CData(node) => {
                if let Some(capture) = &mut capture {
                    capture.value.push_str(&node.decode()?);
                }
            }
            Event::GeneralRef(node) => {
                if let Some(capture) = &mut capture {
                    if let Some(character) = node.resolve_char_ref()? {
                        capture.value.push(character);
                    } else {
                        capture.value.push_str(match node.decode()?.as_ref() {
                            "amp" => "&",
                            "lt" => "<",
                            "gt" => ">",
                            "quot" => "\"",
                            "apos" => "'",
                            _ => bail!("Unsupported XMP metadata entity"),
                        });
                    }
                }
            }
            Event::DocType(_) => bail!("XMP document types are unsupported"),
            Event::Eof => break,
            _ => {}
        }
    }
    if !tags.is_empty() || capture.is_some() {
        bail!("Incomplete XMP metadata")
    }
    Ok(result)
}

pub(super) fn overlay(
    doc: &Document,
    catalog: &Dictionary,
    info: &mut Map<String, Value>,
) -> Result<()> {
    let Ok(metadata) = catalog.get(b"Metadata") else {
        return Ok(());
    };
    let stream = super::resolved(doc, metadata)?.as_stream()?;
    let xml = if stream.dict.has(b"Filter") {
        stream.decompressed_content()?
    } else {
        stream.content.clone()
    };
    let overlay = parse(&xml).context("Read document-info XMP overlay")?;
    if let Some(authors) = overlay.authors {
        info.insert("Authors".into(), json!(authors));
    }
    if let Some(email) = overlay.contact_email {
        info.insert("ContactEmail".into(), json!(email));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn namespaces_containers_and_entities_select_only_document_authors() {
        let xml = br#"<r:RDF xmlns:r="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:d="http://purl.org/dc/elements/1.1/" xmlns:c="http://ns.adobe.com/AcrobatCollab/6.0/">
          <r:Description><d:subject><r:Bag><r:li>Unrelated</r:li></r:Bag></d:subject>
          <d:creator><r:Seq><r:li>Alex &amp; Beta &#x3a9;</r:li><r:li><![CDATA[Second <author>]]></r:li></r:Seq></d:creator>
          <c:ContactEmail>contact@example.test</c:ContactEmail></r:Description></r:RDF>"#;
        assert_eq!(
            parse(xml).unwrap(),
            Overlay {
                authors: Some(vec!["Alex & Beta Ω".into(), "Second <author>".into()]),
                contact_email: Some("contact@example.test".into()),
            }
        );
    }
    #[test]
    fn compact_contact_attribute_and_empty_creator_are_retained() {
        let xml = br#"<r:Description xmlns:r="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:d="http://purl.org/dc/elements/1.1/" xmlns:c="http://ns.adobe.com/AcrobatCollab/6.0/" c:ContactEmail="a&amp;b@example.test"><d:creator><r:Bag/></d:creator></r:Description>"#;
        assert_eq!(
            parse(xml).unwrap(),
            Overlay {
                authors: Some(vec![]),
                contact_email: Some("a&b@example.test".into()),
            }
        );
        assert!(parse(b"<!DOCTYPE x SYSTEM 'file:///unread'><x/>").is_err());
        assert!(parse(b"<x>").is_err());
    }
}
