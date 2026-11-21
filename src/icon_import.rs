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
// Flatten existing normal appearances into the imported page, without copying
// interactive fields or document actions. Reader includes these in PDF icons.
fn page_appearances(
    source: &Document,
    page: ObjectId,
    target: &mut Document,
    ids: &mut HashMap<ObjectId, ObjectId>,
    resources: &mut Dictionary,
    content: &mut Vec<u8>,
) -> Result<()> {
    let page = source.get_dictionary(page)?;
    let Ok(annotations) = page.get(b"Annots") else {
        return Ok(());
    };
    let annotations = source.dereference(annotations)?.1.as_array()?;
    let mut xobjects = resources
        .get(b"XObject")
        .ok()
        .map(|o| {
            target
                .dereference(o)
                .and_then(|(_, v)| v.as_dict())
                .cloned()
        })
        .transpose()?
        .unwrap_or_default();
    for (index, annotation) in annotations.iter().enumerate() {
        let annotation = source.dereference(annotation)?.1.as_dict()?;
        let flags = annotation
            .get(b"F")
            .ok()
            .and_then(|v| v.as_i64().ok())
            .unwrap_or(0);
        if flags & (1 | 2 | 32) != 0 {
            continue;
        }
        let Ok(ap) = annotation.get(b"AP") else {
            continue;
        };
        let ap = source.dereference(ap)?.1.as_dict()?;
        let Ok(normal) = ap.get(b"N") else { continue };
        let normal = source.dereference(normal)?.1;
        let normal = if let Ok(states) = normal.as_dict() {
            let state = annotation.get(b"AS")?.as_name()?;
            source.dereference(states.get(state)?)?.1
        } else {
            normal
        };
        let stream = normal.as_stream()?;
        let numbers = |o: &Object, n: usize| -> Result<Vec<f32>> {
            let values = source
                .dereference(o)?
                .1
                .as_array()?
                .iter()
                .map(Object::as_float)
                .collect::<std::result::Result<Vec<_>, _>>()?;
            if values.len() != n || values.iter().any(|v| !v.is_finite()) {
                bail!("Invalid icon annotation geometry")
            }
            Ok(values)
        };
        let r = numbers(annotation.get(b"Rect")?, 4)?;
        let b = numbers(stream.dict.get(b"BBox")?, 4)?;
        let m = stream
            .dict
            .get(b"Matrix")
            .ok()
            .map(|o| numbers(o, 6))
            .transpose()?
            .unwrap_or_else(|| vec![1., 0., 0., 1., 0., 0.]);
        let points = [(b[0], b[1]), (b[0], b[3]), (b[2], b[1]), (b[2], b[3])]
            .map(|(x, y)| (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]));
        let minx = points.iter().map(|p| p.0).fold(f32::INFINITY, f32::min);
        let maxx = points.iter().map(|p| p.0).fold(f32::NEG_INFINITY, f32::max);
        let miny = points.iter().map(|p| p.1).fold(f32::INFINITY, f32::min);
        let maxy = points.iter().map(|p| p.1).fold(f32::NEG_INFINITY, f32::max);
        if maxx <= minx || maxy <= miny || r[2] <= r[0] || r[3] <= r[1] {
            bail!("Empty icon annotation bounds")
        }
        let sx = (r[2] - r[0]) / (maxx - minx);
        let sy = (r[3] - r[1]) / (maxy - miny);
        let tx = r[0] - sx * minx;
        let ty = r[1] - sy * miny;
        let mut name = format!("MPMBIconAnnotation{index}");
        while xobjects.has(name.as_bytes()) {
            name.push('_');
        }
        let copied = copy_object(source, target, normal, ids, 0)?;
        let copied = target.add_object(copied);
        xobjects.set(name.as_bytes(), copied);
        content.extend(format!("q {sx} 0 0 {sy} {tx} {ty} cm /{name} Do Q\n").as_bytes());
    }
    if !xobjects.is_empty() {
        resources.set("XObject", xobjects);
    }
    Ok(())
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
    let mut resources = copy_object(&source, &mut doc, &resources, &mut ids, 0)?
        .as_dict()?
        .clone();
    let mut content = source.get_page_content_with_limit(id, MAX_BYTES)?;
    page_appearances(
        &source,
        id,
        &mut doc,
        &mut ids,
        &mut resources,
        &mut content,
    )?;
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
    let form=doc.add_object(Stream::new(dictionary! {"Type"=>"XObject","Subtype"=>"Form","BBox"=>rect.clone(),"Matrix"=>matrix,"Resources"=>resources},content));
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

pub fn icon_stream_pdf(pdf: &crate::pdf::Pdf, icon: &Value) -> Result<(usize, Vec<u8>)> {
    let owned_source;
    let (source_doc, form_object): (&Document, Object) =
        if let Some(hex_str) = icon["asset"]["pdf_hex"].as_str() {
            let bytes = unhex(hex_str)?;
            if icon["asset"]["id"].as_str() != Some(hex(&Sha256::digest(&bytes)).as_str()) {
                bail!("Icon payload fingerprint differs")
            }
            owned_source = Document::load_mem(&bytes)?;
            let form = owned_source.catalog()?.get(b"MPMBIcon")?.clone();
            (&owned_source, form)
        } else {
            let field_name = icon["field"]
                .as_str()
                .context("util.iconStreamFromIcon requires a button icon")?;
            let field = pdf
                .fields
                .get(field_name)
                .with_context(|| format!("Icon source field not found: {field_name}"))?;
            let widget = field
                .widgets
                .first()
                .context("Icon source field has no widget")?;
            let wd = pdf.doc.get_dictionary(widget.id)?;
            let found = wd
                .get(b"MK")
                .ok()
                .and_then(|v| pdf.doc.dereference(v).ok().map(|(_, o)| o))
                .and_then(|v| v.as_dict().ok())
                .and_then(|v| v.get(b"I").ok())
                .or_else(|| {
                    wd.get(b"AP")
                        .ok()
                        .and_then(|v| pdf.doc.dereference(v).ok().map(|(_, o)| o))
                        .and_then(|v| v.as_dict().ok())
                        .and_then(|v| v.get(b"N").ok())
                })
                .cloned()
                .context("Button field has no normal icon")?;
            (&pdf.doc, found)
        };
    let stream = source_doc.dereference(&form_object)?.1.as_stream()?;
    let b: Vec<f32> = stream
        .dict
        .get(b"BBox")?
        .as_array()?
        .iter()
        .map(|v| v.as_float().unwrap_or(0.))
        .collect();
    if b.len() != 4 || b[2] <= b[0] || b[3] <= b[1] {
        bail!("Invalid icon form BBox")
    }
    let m = stream
        .dict
        .get(b"Matrix")
        .ok()
        .and_then(|v| v.as_array().ok())
        .map(|a| {
            a.iter()
                .map(|v| v.as_float().unwrap_or(0.))
                .collect::<Vec<_>>()
        })
        .unwrap_or_else(|| vec![1., 0., 0., 1., 0., 0.]);
    if m.len() != 6 {
        bail!("Invalid icon form Matrix")
    }
    let corners = [(b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])]
        .map(|(x, y)| (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]));
    let minx = corners.iter().map(|p| p.0).fold(f32::INFINITY, f32::min);
    let maxx = corners
        .iter()
        .map(|p| p.0)
        .fold(f32::NEG_INFINITY, f32::max);
    let miny = corners.iter().map(|p| p.1).fold(f32::INFINITY, f32::min);
    let maxy = corners
        .iter()
        .map(|p| p.1)
        .fold(f32::NEG_INFINITY, f32::max);
    let src_w = maxx - minx;
    let src_h = maxy - miny;
    if !src_w.is_finite() || !src_h.is_finite() || src_w <= 0. || src_h <= 0. {
        bail!("Degenerate icon bounds")
    }
    let max_dim = 256.0f32;
    let fit = (max_dim / src_w).min(max_dim / src_h).min(1.0);
    let page_w = (src_w * fit).ceil().max(1.);
    let page_h = (src_h * fit).ceil().max(1.);
    let tx = -minx * fit;
    let ty = -miny * fit;
    let mut doc = Document::with_version("1.7");
    let copied = copy_object(source_doc, &mut doc, &form_object, &mut HashMap::new(), 0)?;
    let form_ref = match copied {
        Object::Reference(id) => id,
        other => doc.add_object(other),
    };
    let content = doc.add_object(Stream::new(
        dictionary! {},
        format!("q {fit} 0 0 {fit} {tx} {ty} cm /Icon Do Q\n").into_bytes(),
    ));
    let pages = doc.new_object_id();
    let page = doc.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages,
        "MediaBox" => vec![0.into(), 0.into(), Object::Real(page_w), Object::Real(page_h)],
        "Resources" => dictionary! {"XObject" => dictionary! {"Icon" => form_ref}},
        "Contents" => content,
    });
    doc.objects.insert(
        pages,
        Object::Dictionary(dictionary! {"Type"=>"Pages","Kids"=>vec![page.into()],"Count"=>1}),
    );
    let root = doc.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages});
    doc.trailer.set("Root", root);
    let mut bytes = Vec::new();
    doc.save_to(&mut bytes)?;
    Ok((page_w as usize, bytes))
}

pub fn icon_stream(pdf: &crate::pdf::Pdf, icon: &Value) -> Result<Value> {
    let (width, pdf_bytes) = icon_stream_pdf(pdf, icon)?;
    let (w, h, rgba) = crate::render::Renderer::new()?.render(&pdf_bytes, 0, width)?;
    let mut argb = String::with_capacity(w * h * 8);
    for px in rgba.chunks_exact(4) {
        use std::fmt::Write;
        let _ = write!(
            &mut argb,
            "{:02x}{:02x}{:02x}{:02x}",
            px[3], px[0], px[1], px[2]
        );
    }
    Ok(json!({"width": w, "height": h, "argb": argb}))
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
    fn pdf_widget_appearance_is_flattened_without_interactive_state() {
        let p = folder();
        let path = p.join("annotated.pdf");
        test_pdf(&path);
        let mut source = Document::load(&path).unwrap();
        let page = source.get_pages()[&2];
        let ap = source.add_object(Stream::new(
            dictionary! {
                "Type"=>"XObject", "Subtype"=>"Form",
                "BBox"=>vec![10.into(),20.into(),30.into(),60.into()],
                "Matrix"=>vec![0.into(),(-1).into(),1.into(),0.into(),0.into(),0.into()],
                "Resources"=>dictionary!{}
            },
            b"1 1 1 rg 10 20 20 40 re f".to_vec(),
        ));
        let widget = source.add_object(dictionary! {
            "Type"=>"Annot", "Subtype"=>"Widget", "FT"=>"Tx", "T"=>"Private",
            "Rect"=>vec![2.into(),4.into(),22.into(),14.into()], "F"=>4,
            "AP"=>dictionary!{"N"=>ap}, "AA"=>dictionary!{"U"=>dictionary!{"JS"=>"must not copy"}}
        });
        source
            .get_object_mut(page)
            .unwrap()
            .as_dict_mut()
            .unwrap()
            .set("Annots", vec![widget.into()]);
        source.save(&path).unwrap();
        let result = request(&json!({"path":path,"page":1}), false, &p).unwrap();
        assert_eq!(result["code"], 0);
        std::fs::remove_file(&path).unwrap();
        let mut target = Document::new();
        let form = embed(&mut target, &result["asset"]).unwrap();
        let stream = target.get_object(form).unwrap().as_stream().unwrap();
        let content = String::from_utf8(stream.get_plain_content().unwrap()).unwrap();
        assert!(content.contains("q 0.5 0 0 0.5 -8 19 cm /MPMBIconAnnotation0 Do Q"));
        let copied = stream
            .dict
            .get(b"Resources")
            .unwrap()
            .as_dict()
            .unwrap()
            .get(b"XObject")
            .unwrap()
            .as_dict()
            .unwrap()
            .get(b"MPMBIconAnnotation0")
            .unwrap()
            .as_reference()
            .unwrap();
        assert_eq!(
            target
                .get_object(copied)
                .unwrap()
                .as_stream()
                .unwrap()
                .get_plain_content()
                .unwrap(),
            b"1 1 1 rg 10 20 20 40 re f"
        );
        assert!(!target
            .objects
            .values()
            .any(|o| o.as_dict().is_ok_and(|d| d.has(b"AA") || d.has(b"FT"))));
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
    #[test]
    fn icon_stream_pdf_wraps_button_and_imported_assets_with_transformed_bounds() {
        let p = folder();
        let source = p.join("icon.png");
        let rgba = image::RgbaImage::from_raw(4, 2, vec![255; 32]).unwrap();
        rgba.save(&source).unwrap();
        let imported = request(&json!({"path":source,"page":0}), false, &p).unwrap();
        let mut doc = Document::with_version("1.7");
        let form = doc.add_object(Stream::new(
            dictionary! {
                "Type" => "XObject",
                "Subtype" => "Form",
                "BBox" => vec![3.into(), 4.into(), 60.into(), 59.into()],
                "Matrix" => vec![1.into(), 0.into(), 0.into(), 1.into(), (-31).into(), (-31).into()],
                "Resources" => dictionary! {}
            },
            b"1 0 0 rg 3 4 57 55 re f".to_vec(),
        ));
        let widget = doc.add_object(dictionary! {
            "Type" => "Annot", "Subtype" => "Widget", "FT" => "Btn", "Ff" => 65536,
            "T" => Object::string_literal("SaveIMG.Patreon"),
            "Rect" => vec![0.into(), 0.into(), 20.into(), 20.into()],
            "MK" => dictionary! {"I" => form}
        });
        let fields = std::collections::BTreeMap::from([(
            "SaveIMG.Patreon".into(),
            crate::pdf::Field {
                name: "SaveIMG.Patreon".into(),
                id: widget,
                value: json!(""),
                default_value: json!(""),
                kind: "Btn".into(),
                user_name: String::new(),
                submit_name: String::new(),
                flags: 65536,
                alignment: 0,
                display: 0,
                text_size: 0.,
                text_font: "Helvetica".into(),
                text_color: json!(["G", 0]),
                rich_metadata: json!({}),
                widgets: vec![crate::pdf::Widget {
                    id: widget,
                    page: 0,
                    rect: vec![0., 0., 20., 20.],
                    flags: 4,
                }],
                actions: std::collections::BTreeMap::new(),
                items: Vec::new(),
                export_values: Vec::new(),
                caption: String::new(),
            },
        )]);
        let pdf = crate::pdf::Pdf {
            doc,
            fields,
            scripts: Vec::new(),
            order: Vec::new(),
            info: json!({}),
            bookmarks: json!({"name":"Root","children":[]}),
            path: p.join("sheet.pdf"),
            templates: std::collections::BTreeMap::new(),
        };
        let (w1, bytes1) =
            icon_stream_pdf(&pdf, &json!({"field":"SaveIMG.Patreon","face":0})).unwrap();
        assert_eq!(w1, 57);
        assert_eq!(Document::load_mem(&bytes1).unwrap().get_pages().len(), 1);
        let (w2, bytes2) = icon_stream_pdf(&pdf, &json!({"asset":imported["asset"]})).unwrap();
        assert_eq!(w2, 4);
        assert_eq!(Document::load_mem(&bytes2).unwrap().get_pages().len(), 1);
        std::fs::remove_dir_all(p).unwrap();
    }
}
