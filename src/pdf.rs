mod appearance;
mod buttons;
mod structure;
use anyhow::{bail, Context, Result};
use lopdf::{dictionary, Dictionary, Document, Object, ObjectId, Stream, StringFormat};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};
use structure::Template;

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Widget {
    pub id: ObjectId,
    pub page: i32,
    pub rect: Vec<f64>,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Field {
    pub name: String,
    pub id: ObjectId,
    pub value: Value,
    pub default_value: Value,
    pub kind: String,
    pub user_name: String,
    pub submit_name: String,
    pub flags: i64,
    pub alignment: i64,
    pub display: i32,
    pub text_size: f64,
    pub text_font: String,
    pub widgets: Vec<Widget>,
    pub actions: BTreeMap<String, String>,
    pub items: Vec<Value>,
    pub export_values: Vec<String>,
    pub caption: String,
}
pub struct Pdf {
    pub doc: Document,
    pub fields: BTreeMap<String, Field>,
    pub scripts: Vec<(String, String)>,
    pub order: Vec<String>,
    pub info: Value,
    pub bookmarks: Value,
    pub path: PathBuf,
    pub templates: BTreeMap<String, Template>,
}
fn resolved<'a>(d: &'a Document, o: &'a Object) -> Result<&'a Object> {
    Ok(d.dereference(o)?.1)
}
fn text(d: &Document, o: &Object) -> String {
    let Ok(o) = resolved(d, o) else {
        return String::new();
    };
    match o {
        Object::String(b, _) => decode(b),
        Object::Name(b) => String::from_utf8_lossy(b).into(),
        Object::Integer(v) => v.to_string(),
        Object::Real(v) => v.to_string(),
        Object::Stream(s) => decode(
            &s.decompressed_content()
                .unwrap_or_else(|_| s.content.clone()),
        ),
        _ => String::new(),
    }
}
fn decode(b: &[u8]) -> String {
    if b.starts_with(&[254, 255]) {
        String::from_utf16_lossy(
            &b[2..]
                .chunks_exact(2)
                .map(|x| u16::from_be_bytes([x[0], x[1]]))
                .collect::<Vec<_>>(),
        )
    } else if b.starts_with(&[255, 254]) {
        String::from_utf16_lossy(
            &b[2..]
                .chunks_exact(2)
                .map(|x| u16::from_le_bytes([x[0], x[1]]))
                .collect::<Vec<_>>(),
        )
    } else {
        String::from_utf8(b.to_vec()).unwrap_or_else(|_| b.iter().map(|x| char::from(*x)).collect())
    }
}
fn pdf_string(s: &str) -> Object {
    let mut b = vec![254, 255];
    for v in s.encode_utf16() {
        b.extend(v.to_be_bytes());
    }
    Object::String(b, StringFormat::Hexadecimal)
}
fn action(d: &Document, o: &Object) -> String {
    let Ok(a) = resolved(d, o).and_then(|x| Ok(x.as_dict()?)) else {
        return String::new();
    };
    a.get(b"JS").map(|x| text(d, x)).unwrap_or_default()
}
fn names(d: &Document, o: &Object, out: &mut Vec<(String, String)>) -> Result<()> {
    let n = resolved(d, o)?.as_dict()?;
    if let Ok(a) = n.get(b"Names").and_then(Object::as_array) {
        for p in a.chunks_exact(2) {
            out.push((text(d, &p[0]), action(d, &p[1])));
        }
    }
    if let Ok(a) = n.get(b"Kids").and_then(Object::as_array) {
        for c in a {
            names(d, c, out)?;
        }
    }
    Ok(())
}
fn walk(
    d: &Document,
    r: &Object,
    prefix: &str,
    inherited: &Dictionary,
    page_map: &BTreeMap<ObjectId, i32>,
    out: &mut BTreeMap<String, Field>,
) -> Result<()> {
    let id = r.as_reference()?;
    let obj = resolved(d, r)?.as_dict()?;
    let mut attrs = inherited.clone();
    for (k, v) in obj {
        if k != b"Kids" {
            attrs.set(k.clone(), v.clone());
        }
    }
    let partial = obj.get(b"T").map(|v| text(d, v)).unwrap_or_default();
    let name = if prefix.is_empty() {
        partial.clone()
    } else if partial.is_empty() {
        prefix.into()
    } else {
        format!("{prefix}.{partial}")
    };
    let kids = obj
        .get(b"Kids")
        .and_then(Object::as_array)
        .cloned()
        .unwrap_or_default();
    let named: Vec<_> = kids
        .iter()
        .filter(|k| {
            resolved(d, k)
                .and_then(|v| Ok(v.as_dict()?.has(b"T")))
                .unwrap_or(false)
        })
        .collect();
    if !named.is_empty() {
        for k in named {
            walk(d, k, &name, &attrs, page_map, out)?;
        }
        return Ok(());
    }
    if name.is_empty() {
        return Ok(());
    }
    let val = |key: &[u8]| attrs.get(key).map(|x| text(d, x)).unwrap_or_default();
    let mut actions = BTreeMap::new();
    for node in [&attrs, obj] {
        if let Ok(aa) = node
            .get(b"AA")
            .and_then(|v| resolved(d, v).map_err(|_| lopdf::Error::ObjectNotFound(id)))
            .and_then(Object::as_dict)
        {
            for (k, v) in aa {
                actions.insert(String::from_utf8_lossy(k).into(), action(d, v));
            }
        }
    }
    let mut export_values = Vec::new();
    let mut widgets = Vec::new();
    let refs = if obj.get(b"Subtype").and_then(Object::as_name).ok() == Some(b"Widget") {
        vec![r.clone()]
    } else {
        kids
    };
    let mut display = 0;
    for w in refs {
        let wid = w.as_reference()?;
        let wd = resolved(d, &w)?.as_dict()?;
        if let Ok(normal) = wd
            .get(b"AP")
            .and_then(|v| d.dereference(v).map(|(_, v)| v))
            .and_then(Object::as_dict)
            .and_then(|ap| ap.get(b"N"))
            .and_then(|v| d.dereference(v).map(|(_, v)| v))
            .and_then(Object::as_dict)
        {
            export_values.push(
                normal
                    .iter()
                    .find(|(k, _)| k.as_slice() != b"Off")
                    .map(|(k, _)| String::from_utf8_lossy(k).into_owned())
                    .unwrap_or_else(|| "Yes".into()),
            );
        }

        if let Ok(aa) = wd
            .get(b"AA")
            .and_then(|v| d.dereference(v).map(|(_, v)| v))
            .and_then(Object::as_dict)
        {
            for (k, v) in aa {
                actions
                    .entry(String::from_utf8_lossy(k).into())
                    .or_insert_with(|| action(d, v));
            }
        }
        if let Ok(a) = wd.get(b"A") {
            let code = action(d, a);
            if !code.is_empty() {
                actions.entry("U".into()).or_insert(code);
            }
        }
        let flags = wd.get(b"F").and_then(Object::as_i64).unwrap_or(4);
        display = if flags & 2 != 0 {
            1
        } else if flags & 32 != 0 {
            3
        } else if flags & 4 == 0 {
            2
        } else {
            0
        };
        let rect = wd
            .get(b"Rect")
            .and_then(Object::as_array)
            .map(|a| {
                a.iter()
                    .map(|v| v.as_float().unwrap_or(0.) as f64)
                    .collect()
            })
            .unwrap_or_default();
        widgets.push(Widget {
            id: wid,
            page: *page_map.get(&wid).unwrap_or(&-1),
            rect,
        });
    }
    let items = attrs
        .get(b"Opt")
        .ok()
        .and_then(|v| resolved(d, v).ok())
        .and_then(|v| v.as_array().ok())
        .map(|a| {
            a.iter()
                .map(|o| match o {
                    Object::Array(a) => json!(a.iter().map(|x| text(d, x)).collect::<Vec<_>>()),
                    _ => json!(text(d, o)),
                })
                .collect()
        })
        .unwrap_or_default();
    let da = val(b"DA");
    let tokens: Vec<_> = da.split_whitespace().collect();
    let font_pos = tokens.iter().position(|t| *t == "Tf");
    let text_size = font_pos
        .and_then(|i| i.checked_sub(1))
        .and_then(|i| tokens[i].parse::<f64>().ok())
        .unwrap_or(0.);
    let text_font = font_pos
        .and_then(|i| i.checked_sub(2))
        .map(|i| tokens[i].trim_start_matches('/').to_owned())
        .unwrap_or_else(|| "Helvetica".into());
    out.insert(
        name.clone(),
        Field {
            name,
            id,
            value: json!(val(b"V")),
            default_value: json!(val(b"DV")),
            kind: val(b"FT"),
            user_name: val(b"TU"),
            submit_name: val(b"TM"),
            flags: attrs.get(b"Ff").and_then(Object::as_i64).unwrap_or(0),
            alignment: attrs.get(b"Q").and_then(Object::as_i64).unwrap_or(0),
            display,
            text_size,
            text_font,
            widgets,
            actions,
            items,
            export_values,
            caption: widgets_caption(d, obj),
        },
    );
    Ok(())
}
fn widgets_caption(d: &Document, field: &Dictionary) -> String {
    let nodes = field
        .get(b"Kids")
        .ok()
        .and_then(|v| v.as_array().ok())
        .cloned()
        .unwrap_or_default();
    std::iter::once(field)
        .chain(
            nodes
                .iter()
                .filter_map(|v| resolved(d, v).ok().and_then(|v| v.as_dict().ok())),
        )
        .find_map(|node| {
            node.get(b"MK")
                .ok()
                .and_then(|v| resolved(d, v).ok())
                .and_then(|v| v.as_dict().ok())
                .and_then(|mk| mk.get(b"CA").ok())
                .map(|v| text(d, v))
        })
        .unwrap_or_default()
}
fn bookmarks(d: &Document, first: Option<&Object>, depth: usize) -> Result<Vec<Value>> {
    if depth > 64 {
        bail!("bookmark depth limit")
    }
    let mut result = Vec::new();
    let mut node = first;
    let mut seen = std::collections::BTreeSet::new();
    while let Some(r) = node {
        if let Ok(id) = r.as_reference() {
            if !seen.insert(id) {
                bail!("cyclic bookmarks")
            }
        }
        let dict = resolved(d, r)?.as_dict()?;
        result.push(json!({"name":dict.get(b"Title").map(|v|text(d,v)).unwrap_or_default(),"code":dict.get(b"A").map(|v|action(d,v)).unwrap_or_default(),"children":bookmarks(d,dict.get(b"First").ok(),depth+1)?}));
        node = dict.get(b"Next").ok();
    }
    Ok(result)
}
fn unicode_font(doc: &mut Document) -> Result<(ObjectId, Vec<u8>)> {
    let path = std::env::var("MPMB_FONT")
        .unwrap_or_else(|_| "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf".into());
    let bytes = std::fs::read(&path).context("read Unicode appearance font (MPMB_FONT)")?;
    let face = ttf_parser::Face::parse(&bytes, 0)?;
    let units = face.units_per_em() as f32;
    let scale = |n: i16| n as f32 * 1000. / units;
    let bbox = face.global_bounding_box();
    let mut gids = vec![0u8; 65536 * 2];
    let mut widths = Vec::<Object>::new();
    for code in 0..65536u32 {
        if let Some(ch) = char::from_u32(code) {
            if let Some(gid) = face.glyph_index(ch) {
                gids[code as usize * 2..code as usize * 2 + 2]
                    .copy_from_slice(&gid.0.to_be_bytes());
                widths.push((code as i64).into());
                widths.push(Object::Array(vec![
                    ((face.glyph_hor_advance(gid).unwrap_or(0) as f32 * 1000. / units) as i64)
                        .into(),
                ]));
            }
        }
    }
    let file = doc.add_object(Stream::new(
        dictionary! {"Length1"=>bytes.len() as i64},
        bytes.clone(),
    ));
    let descriptor=doc.add_object(dictionary!{"Type"=>"FontDescriptor","FontName"=>"MPMBDejaVuSans","Flags"=>32,"FontBBox"=>vec![scale(bbox.x_min).into(),scale(bbox.y_min).into(),scale(bbox.x_max).into(),scale(bbox.y_max).into()],"ItalicAngle"=>0,"Ascent"=>scale(face.ascender()),"Descent"=>scale(face.descender()),"CapHeight"=>scale(face.capital_height().unwrap_or(face.ascender())),"StemV"=>80,"FontFile2"=>file});
    let gidmap = doc.add_object(Stream::new(dictionary! {}, gids));
    let cid=doc.add_object(dictionary!{"Type"=>"Font","Subtype"=>"CIDFontType2","BaseFont"=>"MPMBDejaVuSans","CIDSystemInfo"=>dictionary!{"Registry"=>Object::string_literal("Adobe"),"Ordering"=>Object::string_literal("Identity"),"Supplement"=>0},"FontDescriptor"=>descriptor,"DW"=>1000,"W"=>widths,"CIDToGIDMap"=>gidmap});
    let cmap=b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /MPMBIdentity def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange 1 beginbfrange <0000> <FFFF> <0000> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end";
    let unicode = doc.add_object(Stream::new(dictionary! {}, cmap.to_vec()));
    Ok((doc.add_object(dictionary!{"Type"=>"Font","Subtype"=>"Type0","BaseFont"=>"MPMBDejaVuSans","Encoding"=>"Identity-H","DescendantFonts"=>vec![cid.into()],"ToUnicode"=>unicode}),bytes))
}
impl Pdf {
    pub fn open(path: &Path) -> Result<Self> {
        eprintln!("PDF: loading {}", path.display());
        let doc = Document::load_with_options(
            path,
            lopdf::LoadOptions {
                strict: true,
                ..Default::default()
            },
        )
        .context("read PDF")?;
        eprintln!("PDF: parsed {} objects", doc.objects.len());
        let mut page_map = BTreeMap::new();
        for (n, id) in doc.get_pages() {
            if let Ok(a) = doc
                .get_dictionary(id)?
                .get(b"Annots")
                .and_then(|v| doc.dereference(v).map(|(_, o)| o))
                .and_then(Object::as_array)
            {
                for w in a {
                    if let Ok(id) = w.as_reference() {
                        page_map.insert(id, n as i32 - 1);
                    }
                }
            }
        }
        let cat = doc.catalog()?;
        let form = resolved(&doc, cat.get(b"AcroForm")?)?.as_dict()?;
        let mut fields = BTreeMap::new();
        for f in form.get(b"Fields")?.as_array()? {
            walk(&doc, f, "", &Dictionary::new(), &page_map, &mut fields)?;
        }
        let mut scripts = Vec::new();
        if let Ok(js) = cat
            .get(b"Names")
            .and_then(|v| resolved(&doc, v).map_err(|_| lopdf::Error::DictKey("Names".into())))
            .and_then(Object::as_dict)
            .and_then(|v| v.get(b"JavaScript"))
        {
            names(&doc, js, &mut scripts)?;
        }
        let id_names: BTreeMap<_, _> = fields
            .values()
            .flat_map(|f| {
                std::iter::once((f.id, f.name.clone()))
                    .chain(f.widgets.iter().map(|w| (w.id, f.name.clone())))
            })
            .collect();
        let order = form
            .get(b"CO")
            .and_then(Object::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|x| {
                        x.as_reference()
                            .ok()
                            .and_then(|id| id_names.get(&id).cloned())
                    })
                    .collect()
            })
            .unwrap_or_default();
        let mut info = serde_json::Map::new();
        if let Ok(i) = doc
            .trailer
            .get(b"Info")
            .and_then(|v| doc.get_dictionary(v.as_reference()?))
        {
            for (k, v) in i {
                info.insert(String::from_utf8_lossy(k).into(), json!(text(&doc, v)));
            }
        }
        let bkm = cat
            .get(b"Outlines")
            .ok()
            .and_then(|v| resolved(&doc, v).ok())
            .and_then(|v| v.as_dict().ok());
        let bookmarks = json!({"name":"Root","children":bookmarks(&doc,bkm.and_then(|v|v.get(b"First").ok()),0)?});
        eprintln!(
            "PDF: {} fields, {} original scripts",
            fields.len(),
            scripts.len()
        );
        if let Ok(trace) = std::env::var("MPMB_TRACE_FIELDS") {
            for name in trace.split(',') {
                if let Some(f) = fields.get(name) {
                    eprintln!("PDF initial {name}: {} at {:?}", f.value, f.id);
                }
            }
        }
        let templates = structure::templates(&doc, &fields)?;
        Ok(Self {
            templates,
            doc,
            fields,
            scripts,
            order,
            bookmarks,
            info: Value::Object(info),
            path: path.canonicalize()?,
        })
    }
    // Serialization is a projection of the JS state; this document is never edited independently.
    pub fn project(&self, state: &Value) -> Result<Vec<u8>> {
        let (mut doc, fields) = self.structure_projection(state)?;
        if let Some(order) = state["__order"].as_array() {
            let ids: Vec<_> = order
                .iter()
                .filter_map(|n| {
                    n.as_str()
                        .and_then(|n| fields.get(n))
                        .map(|f| Object::Reference(f.id))
                })
                .collect();
            let root = doc.trailer.get(b"Root")?.as_reference()?;
            let form = doc.get_dictionary(root)?.get(b"AcroForm")?.as_reference()?;
            doc.get_dictionary_mut(form)?.set("CO", ids);
        }
        let icon_source = doc.clone();
        let (font, font_bytes) = unicode_font(&mut doc)?;
        let face = ttf_parser::Face::parse(&font_bytes, 0)?;
        for (name, f) in &fields {
            let Some(s) = state.get(name) else {
                bail!("state lost field {name}")
            };
            let value = s["value"]
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| s["value"].to_string());
            let original = f.value.as_str().unwrap_or("");
            let changed = value != original;
            let dict = doc.get_dictionary_mut(f.id)?;
            if changed {
                if f.kind == "Btn" {
                    dict.set("V", Object::Name(value.as_bytes().to_vec()));
                } else {
                    dict.set("V", pdf_string(&value));
                }
            }
            if f.kind == "Ch" {
                if let Some(items) = s["items"].as_array() {
                    dict.set(
                        "Opt",
                        items
                            .iter()
                            .map(|v| {
                                if let Some(pair) = v.as_array() {
                                    Object::Array(
                                        pair.iter()
                                            .map(|x| pdf_string(x.as_str().unwrap_or("")))
                                            .collect(),
                                    )
                                } else {
                                    pdf_string(v.as_str().unwrap_or(""))
                                }
                            })
                            .collect::<Vec<_>>(),
                    );
                    dict.remove(b"I");
                }
            }
            if let Some(readonly) = s["readonly"].as_bool() {
                dict.set("Ff", if readonly { f.flags | 1 } else { f.flags & !1 });
            }
            if let Some(v) = s["submitName"].as_str() {
                if v != f.submit_name {
                    dict.set("TM", pdf_string(v));
                }
            }
            if let Some(v) = s["userName"].as_str() {
                if v != f.user_name {
                    dict.set("TU", pdf_string(v));
                }
            }
            for (widget_index, w) in f.widgets.iter().enumerate() {
                let display = s["display"].as_i64().unwrap_or(f.display as i64);
                let flags = match display {
                    1 => 2,
                    2 => 0,
                    3 => 36,
                    _ => 4,
                };
                let rect = s["widgets"][widget_index]["rect"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .map(|v| v.as_f64().unwrap_or(0.))
                            .collect::<Vec<_>>()
                    })
                    .unwrap_or_else(|| w.rect.clone());
                let wd = doc.get_dictionary_mut(w.id)?;
                if rect != w.rect {
                    wd.set(
                        "Rect",
                        rect.iter()
                            .map(|v| Object::Real(*v as f32))
                            .collect::<Vec<_>>(),
                    );
                }
                let old = wd.get(b"F").and_then(Object::as_i64).unwrap_or(4);
                wd.set("F", (old & !(2 | 4 | 32)) | flags);
                if f.kind == "Btn" && f.flags & 65536 != 0 {
                    buttons::project(&mut doc, &icon_source, &fields, w, &rect, s, &face, font)?;
                    continue;
                }
                if !changed {
                    continue;
                }
                if f.kind == "Btn" {
                    wd.set("AS", Object::Name(value.as_bytes().to_vec()));
                    continue;
                }
                if f.kind != "Tx" && f.kind != "Ch" {
                    continue;
                }
                if w.page < 0 || display == 1 || display == 3 {
                    continue;
                }
                if value.chars().any(|c| c as u32 > 65535) {
                    bail!("appearance encoding does not support non-BMP text in {name}")
                }
                if rect.len() != 4 {
                    continue;
                }
                let width = (rect[2] - rect[0]).abs() as f32;
                let height = (rect[3] - rect[1]).abs() as f32;
                let content = appearance::content(&face, width, height, f, s, &value)?;
                let ap=doc.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),width.into(),height.into()],"Resources"=>dictionary!{"Font"=>dictionary!{"Helv"=>font}}},content));
                doc.get_dictionary_mut(w.id)?
                    .set("AP", dictionary! {"N"=>ap});
            }
        }
        for object in doc.objects.values_mut() {
            if let Object::Stream(stream) = object {
                if stream.allows_compression {
                    stream.compress()?;
                }
            }
        }
        let mut bytes = Vec::new();
        doc.save_to(&mut bytes)?;
        Ok(bytes)
    }
    pub fn save_new(&self, state: &Value, path: &Path) -> Result<()> {
        // Refuse overwrites, including originals, aliases, and existing generated outputs.
        let bytes = self.project(state)?;
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .context("save requires a new disposable path")?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        Ok(())
    }
}
