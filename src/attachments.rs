//! Existing embedded files are immutable document resources. Exports copy bytes.
use anyhow::{bail, Context, Result};
use lopdf::{Document, Object};
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    io::Write,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Serialize, Clone)]
pub struct DataObject {
    pub name: String,
    pub path: String,
    pub size: usize,
    #[serde(rename = "MIMEType")]
    pub mime_type: String,
    #[serde(skip)]
    pub bytes: Vec<u8>,
}
fn text(doc: &Document, object: &Object) -> String {
    let Ok((_, object)) = doc.dereference(object) else {
        return String::new();
    };
    let Ok(bytes) = object.as_str() else {
        return String::new();
    };
    if bytes.starts_with(&[254, 255]) {
        String::from_utf16_lossy(
            &bytes[2..]
                .chunks_exact(2)
                .map(|b| u16::from_be_bytes([b[0], b[1]]))
                .collect::<Vec<_>>(),
        )
    } else {
        String::from_utf8_lossy(bytes).into_owned()
    }
}
pub fn read(doc: &Document) -> Result<BTreeMap<String, DataObject>> {
    fn walk(
        doc: &Document,
        node: &Object,
        depth: usize,
        result: &mut BTreeMap<String, DataObject>,
    ) -> Result<()> {
        if depth > 64 {
            bail!("embedded file name tree exceeds 64 levels")
        }
        let node = doc.dereference(node)?.1.as_dict()?;
        if let Ok(names) = node.get(b"Names").and_then(Object::as_array) {
            if names.len() % 2 != 0 {
                bail!("invalid embedded file name pairs")
            }
            for pair in names.chunks_exact(2) {
                let name = text(doc, &pair[0]);
                let spec = doc.dereference(&pair[1])?.1.as_dict()?;
                let ef = doc.dereference(spec.get(b"EF")?)?.1.as_dict()?;
                let stream = doc
                    .dereference(ef.get(b"UF").or_else(|_| ef.get(b"F"))?)?
                    .1
                    .as_stream()?;
                let bytes = if stream.dict.has(b"Filter") {
                    stream.decompressed_content()?
                } else {
                    stream.content.clone()
                };
                let path = spec
                    .get(b"UF")
                    .or_else(|_| spec.get(b"F"))
                    .map(|o| text(doc, o))
                    .unwrap_or_else(|_| name.clone());
                let mime_type = stream
                    .dict
                    .get(b"Subtype")
                    .and_then(Object::as_name)
                    .map(|b| String::from_utf8_lossy(b).into_owned())
                    .unwrap_or_default();
                let data = DataObject {
                    name: name.clone(),
                    path,
                    size: bytes.len(),
                    mime_type,
                    bytes,
                };
                if result.insert(name.clone(), data).is_some() {
                    bail!("duplicate embedded file name: {name}")
                }
            }
        }
        if let Ok(kids) = node.get(b"Kids").and_then(Object::as_array) {
            for kid in kids {
                walk(doc, kid, depth + 1, result)?;
            }
        }
        Ok(())
    }
    let mut result = BTreeMap::new();
    if let Ok(names) = doc.catalog()?.get(b"Names") {
        let names = doc.dereference(names)?.1.as_dict()?;
        if let Ok(tree) = names.get(b"EmbeddedFiles") {
            walk(doc, tree, 0, &mut result)?;
        }
    }
    Ok(result)
}
#[derive(Default)]
pub struct Exporter {
    temporary: Vec<PathBuf>,
}
impl Drop for Exporter {
    fn drop(&mut self) {
        for path in &self.temporary {
            let _ = std::fs::remove_file(path);
        }
    }
}
impl Exporter {
    pub fn export(
        &mut self,
        objects: &BTreeMap<String, DataObject>,
        request: &str,
        interactive: bool,
        output_dir: Option<&Path>,
    ) -> Result<Value> {
        let request: Value = serde_json::from_str(request)?;
        let params = request
            .as_object()
            .context("exportDataObject requires options")?;
        if params
            .keys()
            .any(|k| !["cName", "nLaunch", "bAllowAuth"].contains(&k.as_str()))
        {
            bail!("unsupported exportDataObject option")
        }
        let name = request["cName"]
            .as_str()
            .context("exportDataObject requires cName")?;
        let object = objects
            .get(name)
            .context("embedded data object does not exist")?;
        let launch = request
            .get("nLaunch")
            .map(|v| v.as_i64().context("nLaunch must be an integer"))
            .transpose()?
            .unwrap_or(0);
        if !(0..=2).contains(&launch) {
            bail!("invalid nLaunch")
        }
        if launch > 0
            && (!object.path.to_lowercase().ends_with(".pdf")
                || !object.bytes.starts_with(b"%PDF-"))
        {
            bail!("launching non-PDF attachments is unsupported")
        }
        let filename = Path::new(&object.path)
            .file_name()
            .filter(|n| !n.is_empty())
            .context("attachment filename missing")?;
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
        let temporary = output_dir.is_none() && launch == 2;
        let destination = if let Some(dir) = output_dir {
            std::fs::create_dir_all(dir)?;
            dir.join(format!("{stamp}-{}", filename.to_string_lossy()))
        } else if !interactive {
            bail!("attachment export requires a native dialog or explicit probe attachment_output_dir")
        } else if temporary {
            std::env::temp_dir().join(format!("mpmb-{stamp}-{}", filename.to_string_lossy()))
        } else {
            let suggested = filename.to_string_lossy();
            let output = Command::new("zenity")
                .args([
                    "--file-selection",
                    "--save",
                    "--title=Export MPMB attachment",
                    &format!("--filename={suggested}"),
                ])
                .output()?;
            if output.status.code() == Some(1) {
                return Ok(json!({"status":"cancelled","name":name}));
            }
            if !output.status.success() {
                bail!("attachment destination dialog failed")
            }
            PathBuf::from(String::from_utf8(output.stdout)?.trim_end_matches('\n'))
        };
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&destination)
            .context("attachment export requires a new destination")?;
        file.write_all(&object.bytes)?;
        file.sync_all()?;
        if temporary {
            self.temporary.push(destination.clone());
        }
        let launched = launch > 0 && output_dir.is_none();
        if launched
            && !Command::new("xdg-open")
                .arg(&destination)
                .status()?
                .success()
        {
            bail!("could not open exported PDF attachment")
        }
        Ok(
            json!({"status":"saved","name":name,"path":destination,"size":object.size,"launched":launched,"launch_suppressed":launch>0&&!launched}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lopdf::{dictionary, Stream};
    #[test]
    fn nested_name_tree_decodes_payload_and_unicode_filename() {
        let mut doc = Document::with_version("1.7");
        let bytes = b"Binary attachment\0\xff".to_vec();
        let mut stream = Stream::new(
            dictionary! {"Type"=>"EmbeddedFile","Subtype"=>"application/pdf"},
            bytes.clone(),
        );
        stream.compress().unwrap();
        let payload = doc.add_object(stream);
        let mut utf16 = vec![254, 255];
        for c in "FAQ العربية.pdf".encode_utf16() {
            utf16.extend(c.to_be_bytes());
        }
        let spec = doc.add_object(dictionary! {"Type"=>"Filespec","F"=>Object::string_literal("fallback.pdf"),"UF"=>Object::String(utf16,lopdf::StringFormat::Hexadecimal),"EF"=>dictionary! {"F"=>payload},"Desc"=>Object::string_literal("description")});
        let leaf = doc
            .add_object(dictionary! {"Names"=>vec![Object::string_literal("FAQ.pdf"),spec.into()]});
        let root = doc.add_object(dictionary! {"Type"=>"Catalog","Names"=>dictionary! {"EmbeddedFiles"=>dictionary! {"Kids"=>vec![leaf.into()]}}});
        doc.trailer.set("Root", root);
        let objects = read(&doc).unwrap();
        let object = &objects["FAQ.pdf"];
        assert_eq!(object.path, "FAQ العربية.pdf");
        assert_eq!(object.bytes, bytes);
        assert_eq!(object.size, bytes.len());
        assert_eq!(object.mime_type, "application/pdf");
        assert!(!serde_json::to_value(object)
            .unwrap()
            .as_object()
            .unwrap()
            .contains_key("bytes"));
        // A malformed/cyclic tree must fail rather than hang or silently hide files.
        doc.get_dictionary_mut(leaf)
            .unwrap()
            .set("Kids", vec![leaf.into()]);
        assert!(read(&doc).is_err());
    }
    #[test]
    fn export_copies_bytes_and_rejects_launching_non_pdf_or_missing_destinations() {
        let name = "helper.js.txt";
        let bytes = b"var installationHelper = true;";
        let objects = BTreeMap::from([(
            name.into(),
            DataObject {
                name: name.into(),
                path: "../../helper.js.txt".into(),
                size: bytes.len(),
                mime_type: "text/plain".into(),
                bytes: bytes.to_vec(),
            },
        )]);
        let mut exporter = Exporter::default();
        assert!(exporter
            .export(&objects, &json!({"cName":name}).to_string(), false, None)
            .is_err());
        let folder = std::env::temp_dir().join(format!(
            "mpmb-attachment-test-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let result = exporter
            .export(
                &objects,
                &json!({"cName":name}).to_string(),
                false,
                Some(&folder),
            )
            .unwrap();
        let path = Path::new(result["path"].as_str().unwrap());
        assert_eq!(path.parent(), Some(folder.as_path()));
        assert_eq!(std::fs::read(path).unwrap(), bytes);
        assert!(exporter
            .export(
                &objects,
                &json!({"cName":name,"nLaunch":2}).to_string(),
                false,
                Some(&folder)
            )
            .is_err());
        assert!(exporter
            .export(
                &objects,
                &json!({"cName":"missing"}).to_string(),
                false,
                Some(&folder)
            )
            .is_err());
        std::fs::remove_dir_all(folder).unwrap();
    }
}
