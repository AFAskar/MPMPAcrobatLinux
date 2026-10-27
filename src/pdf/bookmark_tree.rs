use super::pdf_string;
use anyhow::{bail, Context, Result};
use lopdf::{dictionary, Dictionary, Document, Object, ObjectId};
use serde_json::Value;

pub(super) fn project(doc: &mut Document, root: &Value) -> Result<()> {
    let outline = doc.new_object_id();
    let mut dictionary = dictionary! {"Type"=>"Outlines"};
    let count = children(doc, outline, root, &mut dictionary, 0)?;
    dictionary.set("Count", count as i64);
    doc.objects.insert(outline, Object::Dictionary(dictionary));
    doc.catalog_mut()?.set("Outlines", outline);
    Ok(())
}

// Returns descendants visible when this parent is open. PDF Count is signed:
// a closed item's magnitude describes what opening that item would reveal.
fn children(
    doc: &mut Document,
    parent: ObjectId,
    node: &Value,
    dictionary: &mut Dictionary,
    depth: usize,
) -> Result<usize> {
    if depth > 64 {
        bail!("bookmark depth limit")
    }
    let nodes = node["children"]
        .as_array()
        .context("bookmark children must be an array")?;
    dictionary.remove(b"First");
    dictionary.remove(b"Last");
    dictionary.remove(b"Count");
    if nodes.is_empty() {
        return Ok(0);
    }
    let ids = nodes
        .iter()
        .map(|_| doc.new_object_id())
        .collect::<Vec<_>>();
    dictionary.set("First", ids[0]);
    dictionary.set("Last", ids[ids.len() - 1]);
    let mut visible = nodes.len();
    for (index, child) in nodes.iter().enumerate() {
        // Preserve existing destinations/actions and unrelated properties unless
        // setAction explicitly replaces the action. Never invent JS from a Dest.
        let original = child["id"]
            .as_array()
            .filter(|a| a.len() == 2)
            .and_then(|a| {
                Some((
                    u32::try_from(a[0].as_u64()?).ok()?,
                    u16::try_from(a[1].as_u64()?).ok()?,
                ))
            });
        let mut entry = original
            .and_then(|id| doc.get_dictionary(id).ok())
            .cloned()
            .unwrap_or_default();
        entry.remove(b"Prev");
        entry.remove(b"Next");
        entry.set(
            "Title",
            pdf_string(
                child["name"]
                    .as_str()
                    .context("bookmark name must be text")?,
            ),
        );
        entry.set("Parent", parent);
        if index > 0 {
            entry.set("Prev", ids[index - 1]);
        }
        if index + 1 < ids.len() {
            entry.set("Next", ids[index + 1]);
        }
        let style = child["style"].as_i64().unwrap_or(0);
        if !(0..=3).contains(&style) {
            bail!("invalid bookmark style")
        }
        entry.set("F", style);
        if let Some(color) = child["color"].as_array() {
            let rgb = match color.first().and_then(Value::as_str) {
                Some("RGB") if color.len() == 4 => color[1..].to_vec(),
                Some("G") if color.len() == 2 => vec![color[1].clone(); 3],
                _ => bail!("unsupported bookmark color"),
            };
            let rgb = rgb
                .iter()
                .map(|n| {
                    n.as_f64()
                        .filter(|v| v.is_finite() && (0.0..=1.0).contains(v))
                        .map(|v| Object::Real(v as f32))
                        .context("invalid bookmark color component")
                })
                .collect::<Result<Vec<_>>>()?;
            entry.set("C", rgb);
        }
        if child["actionChanged"] == true || original.is_none() {
            entry.remove(b"Dest");
            entry.remove(b"A");
            if let Some(code) = child["code"].as_str().filter(|s| !s.is_empty()) {
                entry.set("A", dictionary! {"S"=>"JavaScript","JS"=>pdf_string(code)});
            }
        }
        let descendants = children(doc, ids[index], child, &mut entry, depth + 1)?;
        if descendants > 0 {
            let open = child["open"].as_bool().unwrap_or(false);
            entry.set(
                "Count",
                if open {
                    descendants as i64
                } else {
                    -(descendants as i64)
                },
            );
            if open {
                visible += descendants;
            }
        }
        doc.objects.insert(ids[index], Object::Dictionary(entry));
    }
    Ok(visible)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn outlines_preserve_destinations_and_write_actions_links_and_open_counts() {
        let mut doc = Document::with_version("1.7");
        let catalog = doc.add_object(dictionary! {"Type"=>"Catalog"});
        doc.trailer.set("Root", catalog);
        let original=doc.add_object(dictionary!{"Title"=>"Old", "Dest"=>vec![Object::Integer(0),Object::Name(b"Fit".to_vec())],"Extra"=>true});
        let state = json!({"children":[{"id":original,"name":"Retained","open":true,"style":2,"color":["RGB",1,0,0],"children":[{"name":"Child","code":"pageNum=2","actionChanged":true,"children":[]}]},{"name":"Second","children":[]}]});
        project(&mut doc, &state).unwrap();
        let root = doc
            .catalog()
            .unwrap()
            .get(b"Outlines")
            .unwrap()
            .as_reference()
            .unwrap();
        let outline = doc.get_dictionary(root).unwrap();
        assert_eq!(outline.get(b"Count").unwrap().as_i64().unwrap(), 3);
        let first = outline.get(b"First").unwrap().as_reference().unwrap();
        let entry = doc.get_dictionary(first).unwrap();
        assert!(entry.has(b"Dest") && entry.has(b"Extra"));
        assert_eq!(entry.get(b"Count").unwrap().as_i64().unwrap(), 1);
        let child = entry.get(b"First").unwrap().as_reference().unwrap();
        let leaf = doc.get_dictionary(child).unwrap();
        assert!(leaf.has(b"A") && !leaf.has(b"Dest"));
        let second = entry.get(b"Next").unwrap().as_reference().unwrap();
        assert_eq!(
            doc.get_dictionary(second)
                .unwrap()
                .get(b"Prev")
                .unwrap()
                .as_reference()
                .unwrap(),
            first
        );
    }
}
