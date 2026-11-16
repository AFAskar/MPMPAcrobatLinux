//! Imported button media is immutable, self-contained PDF resource data.
//! The JavaScript field owns the selected icon; no second form state is created.
use anyhow::{bail, Context, Result};
use image::ImageReader;
use lopdf::{dictionary, Dictionary, Document, Object, ObjectId, Stream};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::HashMap, io::Cursor, path::Path};

const MAX_BYTES: usize = 64 * 1024 * 1024;
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn unhex(text: &str) -> Result<Vec<u8>> {
    if text.len() > MAX_BYTES * 2 || !text.len().is_multiple_of(2) {
        bail!("Invalid icon payload size")
    }
    text.as_bytes()
        .chunks_exact(2)
        .map(|b| {
            let s = std::str::from_utf8(b)?;
            Ok(u8::from_str_radix(s, 16)?)
        })
        .collect()
}
fn inherited(doc: &Document, mut page: ObjectId, key: &[u8]) -> Result<Object> {
    for _ in 0..64 {
        let d = doc.get_dictionary(page)?;
        if let Ok(value) = d.get(key) {
            return Ok(doc.dereference(value)?.1.clone());
        }
        page = d.get(b"Parent")?.as_reference()?;
    }
    bail!("Icon page inheritance exceeds64 levels")
}
fn copy_object(
    source: &Document,
    target: &mut Document,
    object: &Object,
    ids: &mut HashMap<ObjectId, ObjectId>,
    depth: usize,
) -> Result<Object> {
    if depth > 64 || ids.len() > 100_000 {
        bail!("Icon resource graph exceeds supported bounds")
    }
    Ok(match object {
        Object::Reference(id) => {
            if let Some(mapped) = ids.get(id) {
                return Ok(Object::Reference(*mapped));
            }
            let new = target.add_object(Object::Null);
            ids.insert(*id, new);
            let copied = copy_object(source, target, source.get_object(*id)?, ids, depth + 1)?;
            target.objects.insert(new, copied);
            Object::Reference(new)
        }
        Object::Array(a) => Object::Array(
            a.iter()
                .map(|v| copy_object(source, target, v, ids, depth + 1))
                .collect::<Result<_>>()?,
        ),
        Object::Dictionary(d) => {
            let mut out = Dictionary::new();
            for (key, value) in d.iter() {
                out.set(
                    key.clone(),
                    copy_object(source, target, value, ids, depth + 1)?,
                );
            }
            Object::Dictionary(out)
        }
        Object::Stream(s) => {
            let d = copy_object(
                source,
                target,
                &Object::Dictionary(s.dict.clone()),
                ids,
                depth + 1,
            )?;
            Object::Stream(Stream::new(d.as_dict()?.clone(), s.content.clone()))
        }
        value => value.clone(),
    })
}
fn finish(mut doc: Document, form: ObjectId) -> Result<Value> {
    let root = doc.add_object(dictionary! {"Type"=>"Catalog","MPMBIcon"=>form});
    doc.trailer.set("Root", root);
    doc.compress();
    let mut bytes = Vec::new();
    doc.save_to(&mut bytes)?;
    if bytes.len() > MAX_BYTES {
        bail!("Prepared icon exceeds64MiB")
    }
    Ok(json!({"id":hex(&Sha256::digest(&bytes)),"pdf_hex":hex(&bytes)}))
}
fn bitmap(bytes: &[u8]) -> Result<Value> {
    let read = || ImageReader::new(Cursor::new(bytes)).with_guessed_format();
    let (w, h) = read()?.into_dimensions()?;
    if w == 0 || h == 0 || u64::from(w) * u64::from(h) > 16 * 1024 * 1024 {
        bail!("Icon exceeds16 megapixels")
    }
    let mut reader = read()?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(16384);
    limits.max_image_height = Some(16384);
    limits.max_alloc = Some(128 * 1024 * 1024);
    reader.limits(limits);
    let image = reader.decode()?.to_rgba8();
    let mut rgb = Vec::with_capacity((w * h * 3) as usize);
    let mut alpha = Vec::with_capacity((w * h) as usize);
    for p in image.pixels() {
        rgb.extend_from_slice(&p.0[..3]);
        alpha.push(p.0[3]);
    }
    let mut doc = Document::with_version("1.7");
    let mut image_dict = dictionary! {"Type"=>"XObject","Subtype"=>"Image","Width"=>w as i64,"Height"=>h as i64,"ColorSpace"=>"DeviceRGB","BitsPerComponent"=>8};
    if alpha.iter().any(|v| *v != 255) {
        let mask=doc.add_object(Stream::new(dictionary! {"Type"=>"XObject","Subtype"=>"Image","Width"=>w as i64,"Height"=>h as i64,"ColorSpace"=>"DeviceGray","BitsPerComponent"=>8},alpha));
        image_dict.set("SMask", mask);
    }
    let image = doc.add_object(Stream::new(image_dict, rgb));
    let content = format!("q {w} 0 0 {h} 0 0 cm /Image Do Q\n").into_bytes();
    let form=doc.add_object(Stream::new(dictionary! {"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),(w as i64).into(),(h as i64).into()],"Resources"=>dictionary! {"XObject"=>dictionary! {"Image"=>image}}},content));
    finish(doc, form)
}
fn pdf_page(bytes: &[u8], page: usize) -> Result<Value> {
    let source = Document::load_mem(bytes)?;
    let pages = source.get_pages();
    let id = *pages.values().nth(page).context("Invalid icon page")?;
    let bounds =
        inherited(&source, id, b"CropBox").or_else(|_| inherited(&source, id, b"MediaBox"))?;
    let rect = bounds.as_array()?;
    if rect.len() != 4 {
        bail!("Invalid icon page rectangle")
    }
    let r = rect
        .iter()
        .map(Object::as_float)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if r[2] <= r[0] || r[3] <= r[1] {
        bail!("Empty icon page")
    }
    // Keep the selected page's vector content and only its reachable resources.
    // Catalogs, scripts and other pages are not copied into the character PDF.
    let mut doc = Document::with_version("1.7");
    let mut ids = HashMap::new();
    let resources = inherited(&source, id, b"Resources")
        .unwrap_or_else(|_| Object::Dictionary(Dictionary::new()));
    let resources = copy_object(&source, &mut doc, &resources, &mut ids, 0)?;
    let angle = inherited(&source, id, b"Rotate")
        .ok()
        .and_then(|o| o.as_i64().ok())
        .unwrap_or(0)
        .rem_euclid(360);
    let matrix: Vec<Object> = match angle {
        0 => vec![1, 0, 0, 1, 0, 0],
        90 => vec![0, -1, 1, 0, 0, 0],
        180 => vec![-1, 0, 0, -1, 0, 0],
        270 => vec![0, 1, -1, 0, 0, 0],
        _ => bail!("Invalid icon page rotation"),
    }
    .into_iter()
    .map(Object::Integer)
    .collect();
    let form=doc.add_object(Stream::new(dictionary! {"Type"=>"XObject","Subtype"=>"Form","BBox"=>rect.clone(),"Matrix"=>matrix,"Resources"=>resources},source.get_page_content_with_limit(id, MAX_BYTES)?));
    finish(doc, form)
}
fn is_pdf(bytes: &[u8]) -> bool {
    bytes[..bytes.len().min(1024)]
        .windows(5)
        .any(|w| w == b"%PDF-")
}
pub fn request(request: &Value, interactive: bool, base: &Path) -> Result<Value> {
    let explicit = request["path"].as_str();
    let path = if let Some(path) = explicit {
        path.to_owned()
    } else {
        if !interactive {
            bail!("Icon file selection requires interactive mode or an explicit local path")
        }
        let selected = std::process::Command::new("zenity")
            .args([
                "--file-selection",
                "--title=Import image or PDF icon",
                "--file-filter=Images and PDF | *.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff",
                "--file-filter=All files | *",
            ])
            .output()?;
        if !selected.status.success() {
            if selected.status.code() == Some(1) {
                return Ok(json!({"code":1}));
            }
            bail!("Native icon file picker failed")
        }
        String::from_utf8(selected.stdout)?
            .trim_end_matches(['\r', '\n'])
            .to_owned()
    };
    let path = Path::new(&path);
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        base.join(path)
    };
    let read = (|| -> Result<Vec<u8>> {
        if path.metadata()?.len() > MAX_BYTES as u64 {
            bail!("Icon input exceeds64MiB")
        }
        Ok(std::fs::read(&path)?)
    })();
    let bytes = match read {
        Ok(b) => b,
        Err(e) => return Ok(json!({"code":-1,"reason":format!("{e:#}")})),
    };
    let mut page = request["page"].as_i64().unwrap_or(-1);
    if explicit.is_none() {
        page = 0;
        if is_pdf(&bytes) {
            let count = Document::load_mem(&bytes)
                .map(|d| d.get_pages().len())
                .unwrap_or(0);
            if count > 1 {
                let answer = crate::ui::modal(
                    &json!({"description":{"name":"Choose PDF icon page","elements":[{"type":"static_text","name":format!("Choose a page from 1 through {count}")},{"type":"edit_text","item_id":"page","char_width":8},{"type":"ok_cancel"}]},"values":{"page":"1"}}),
                )?;
                if answer["result"] != "ok" {
                    return Ok(json!({"code":1}));
                }
                page = answer["values"]["page"]
                    .as_str()
                    .and_then(|s| s.parse::<i64>().ok())
                    .unwrap_or(0)
                    - 1;
            }
        }
    }
    if page < 0 {
        return Ok(json!({"code":-2}));
    }
    if is_pdf(&bytes) {
        if let Ok(d) = Document::load_mem(&bytes) {
            if page as usize >= d.get_pages().len() {
                return Ok(json!({"code":-2}));
            }
        }
    } else if page != 0 {
        return Ok(json!({"code":-2}));
    }
    let prepared = if is_pdf(&bytes) {
        pdf_page(&bytes, page as usize)
    } else {
        bitmap(&bytes)
    };
    Ok(match prepared {
        Ok(asset) => json!({"code":0,"asset":asset}),
        Err(e) => json!({"code":-1,"reason":format!("{e:#}")}),
    })
}
pub fn embed(target: &mut Document, asset: &Value) -> Result<ObjectId> {
    let bytes = unhex(asset["pdf_hex"].as_str().context("Missing icon payload")?)?;
    if asset["id"].as_str() != Some(hex(&Sha256::digest(&bytes)).as_str()) {
        bail!("Icon payload fingerprint differs")
    }
    let source = Document::load_mem(&bytes)?;
    let form = source.catalog()?.get(b"MPMBIcon")?;
    copy_object(&source, target, form, &mut HashMap::new(), 0)?
        .as_reference()
        .map_err(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn folder() -> std::path::PathBuf {
        let p = std::env::temp_dir().join(format!(
            "mpmb-icon-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&p).unwrap();
        p
    }
    fn test_pdf(path: &Path) {
        let mut d = Document::with_version("1.7");
        let pages = d.new_object_id();
        let mut ids = Vec::new();
        for (rotate, content) in [
            (0, b"1 0 0 rg 0 0 40 20 re f".as_slice()),
            (90, b"0 1 0 rg 0 0 40 20 re f".as_slice()),
        ] {
            let c = d.add_object(Stream::new(dictionary! {}, content.to_vec()));
            ids.push(Object::Reference(d.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),40.into(),20.into()],"Rotate"=>rotate,"Contents"=>c,"Resources"=>dictionary!{}})));
        }
        d.objects.insert(
            pages,
            Object::Dictionary(dictionary! {"Type"=>"Pages","Kids"=>ids,"Count"=>2}),
        );
        let root = d.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages});
        d.trailer.set("Root", root);
        d.save(path).unwrap();
    }
    #[test]
    fn imported_png_is_self_contained_and_preserves_alpha() {
        let p = folder();
        let source = p.join("alpha.png");
        let rgba = image::RgbaImage::from_raw(2, 1, vec![255, 0, 0, 0, 0, 255, 0, 128]).unwrap();
        rgba.save(&source).unwrap();
        let result = request(&json!({"path":source,"page":0}), false, &p).unwrap();
        assert_eq!(result["code"], 0);
        std::fs::remove_file(&source).unwrap();
        let mut target = Document::new();
        let form = embed(&mut target, &result["asset"]).unwrap();
        let resources = target
            .get_object(form)
            .unwrap()
            .as_stream()
            .unwrap()
            .dict
            .get(b"Resources")
            .unwrap()
            .as_dict()
            .unwrap();
        let image = resources
            .get(b"XObject")
            .unwrap()
            .as_dict()
            .unwrap()
            .get(b"Image")
            .unwrap()
            .as_reference()
            .unwrap();
        let stream = target.get_object(image).unwrap().as_stream().unwrap();
        assert_eq!(
            stream.get_plain_content().unwrap(),
            vec![255, 0, 0, 0, 255, 0]
        );
        let mask = stream.dict.get(b"SMask").unwrap().as_reference().unwrap();
        assert_eq!(
            target
                .get_object(mask)
                .unwrap()
                .as_stream()
                .unwrap()
                .get_plain_content()
                .unwrap(),
            vec![0, 128]
        );
        std::fs::remove_dir_all(p).unwrap();
    }
    #[test]
    fn selected_pdf_page_keeps_vector_content_and_rotation() {
        let p = folder();
        let source = p.join("pages.pdf");
        test_pdf(&source);
        let result = request(&json!({"path":source,"page":1}), false, &p).unwrap();
        assert_eq!(result["code"], 0);
        let mut target = Document::new();
        let id = embed(&mut target, &result["asset"]).unwrap();
        let stream = target.get_object(id).unwrap().as_stream().unwrap();
        assert_eq!(
            stream.get_plain_content().unwrap(),
            b"0 1 0 rg 0 0 40 20 re f\n"
        );
        assert_eq!(
            stream.dict.get(b"Matrix").unwrap().as_array().unwrap(),
            &vec![
                0.into(),
                (-1).into(),
                1.into(),
                0.into(),
                0.into(),
                0.into()
            ]
        );
        assert!(!target.objects.values().any(|v| v.as_dict().is_ok_and(|d| d
            .get(b"Type")
            .and_then(Object::as_name)
            .ok()
            == Some(b"Page".as_slice()))));
        std::fs::remove_dir_all(p).unwrap();
    }
    #[test]
    fn bad_file_and_invalid_page_are_distinct_and_payloads_are_checked() {
        let p = folder();
        let source = p.join("pages.pdf");
        test_pdf(&source);
        assert_eq!(
            request(&json!({"path":source,"page":2}), false, &p).unwrap()["code"],
            -2
        );
        assert_eq!(
            request(&json!({"path":p.join("missing.png"),"page":0}), false, &p).unwrap()["code"],
            -1
        );
        let mut value =
            request(&json!({"path":source,"page":0}), false, &p).unwrap()["asset"].clone();
        value["id"] = json!("changed");
        assert!(embed(&mut Document::new(), &value).is_err());
        std::fs::remove_dir_all(p).unwrap();
    }
}
