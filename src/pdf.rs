mod appearance;
mod bookmark_tree;
mod buttons;
mod document_info;
mod embedded_fonts;
mod field_style;
mod installed_fonts;
mod rich_text;
mod structure;
pub(crate) mod xfdf;
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
    pub flags: i64,
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
    pub text_color: Value,
    pub rich_metadata: Value,
    pub widgets: Vec<Widget>,
    pub actions: BTreeMap<String, String>,
    pub items: Vec<Value>,
    pub export_values: Vec<String>,
    pub caption: String,
}
// Non-leaf field entries can occupy real /CO slots without an executable
// action. Preserve their references and positions; calcOrderIndex counts them.
#[derive(Clone, Serialize, Deserialize, Debug, PartialEq)]
#[serde(untagged)]
pub enum CalculationEntry {
    Field(String),
    Preserved { reference: ObjectId },
}

pub struct Pdf {
    pub doc: Document,
    pub fields: BTreeMap<String, Field>,
    pub scripts: Vec<(String, String)>,
    pub order: Vec<CalculationEntry>,
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
            flags,
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
    // Reader base-field getters use widget zero even when it belongs to an
    // inactive template. Do not prefer a visible widget over PDF Kids order.
    let style_widget = widgets.first().and_then(|w| d.get_dictionary(w.id).ok());
    let da = style_widget
        .and_then(|widget| widget.get(b"DA").ok())
        .map(|appearance| text(d, appearance))
        .unwrap_or_else(|| val(b"DA"));
    let alignment = style_widget
        .and_then(|widget| widget.get(b"Q").ok())
        .and_then(|q| q.as_i64().ok())
        .unwrap_or_else(|| attrs.get(b"Q").and_then(Object::as_i64).unwrap_or(0));
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
    // DA names address font resources. Reader's getter exposes the standard
    // font name, rather than aliases such as ZaDb, Helv or HeBo.
    let text_font = match text_font.as_str() {
        "Helv" => "Helvetica".into(),
        "HeBo" => "Helvetica-Bold".into(),
        "Cour" => "Courier".into(),
        "Symb" => "Symbol".into(),
        "ZaDb" => "ZapfDingbats".into(),
        _ => text_font,
    };
    let text_color =
        field_style::color(&da).with_context(|| format!("Default appearance color in {name}"))?;
    let kind = val(b"FT");
    let flags = attrs.get(b"Ff").and_then(Object::as_i64).unwrap_or(0);
    let mut value = val(b"V");
    // Reader exposes an unset checkbox/radio value as Off. Keep the source
    // dictionary untouched so an unchanged logical Off does not invent /V.
    if kind == "Btn" && flags & 65536 == 0 && value.is_empty() {
        value = "Off".into();
    }
    out.insert(
        name.clone(),
        Field {
            name: name.clone(),
            id,
            value: json!(value),
            default_value: json!(val(b"DV")),
            kind,
            user_name: val(b"TU"),
            submit_name: val(b"TM"),
            flags,
            alignment,
            display,
            text_size,
            rich_metadata: rich_text::metadata(
                &val(b"DS"),
                &val(b"RV"),
                &text_font,
                text_size,
                alignment,
            )
            .with_context(|| format!("Rich-text metadata in {name}"))?,
            text_font,
            text_color,
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
        let destination = dict.get(b"Dest").ok().or_else(|| {
            dict.get(b"A")
                .ok()
                .and_then(|a| resolved(d, a).ok())
                .and_then(|a| a.as_dict().ok())
                .and_then(|a| a.get(b"D").ok())
        });
        let destination_page = destination
            .and_then(|a| resolved(d, a).ok())
            .and_then(|a| a.as_array().ok())
            .and_then(|a| a.first())
            .and_then(|p| p.as_reference().ok())
            .and_then(|id| d.get_pages().values().position(|p| *p == id));
        let mut bookmark = json!({"id":r.as_reference().ok(),"name":dict.get(b"Title").map(|v|text(d,v)).unwrap_or_default(),"code":dict.get(b"A").map(|v|action(d,v)).unwrap_or_default(),"style":dict.get(b"F").and_then(Object::as_i64).unwrap_or(0)&3,"open":dict.get(b"Count").and_then(Object::as_i64).unwrap_or(0)>0,"children":bookmarks(d,dict.get(b"First").ok(),depth+1)?});
        if let Some(page) = destination_page {
            bookmark["destinationPage"] = json!(page);
            bookmark["destinationApproximate"] = json!(true);
        } else if destination.is_some() {
            bookmark["unsupportedAction"] = json!("named/unresolved destination");
        } else if let Some(kind) = dict
            .get(b"A")
            .ok()
            .and_then(|a| resolved(d, a).ok())
            .and_then(|a| a.as_dict().ok())
            .and_then(|a| a.get(b"S").ok())
            .map(|a| text(d, a))
        {
            if kind != "JavaScript" {
                bookmark["unsupportedAction"] = json!(kind);
            }
        }
        if let Ok(color) = dict.get(b"C").and_then(Object::as_array) {
            bookmark["color"] = json!([
                "RGB",
                color.first().and_then(|v| v.as_float().ok()).unwrap_or(0.),
                color.get(1).and_then(|v| v.as_float().ok()).unwrap_or(0.),
                color.get(2).and_then(|v| v.as_float().ok()).unwrap_or(0.)
            ]);
        }
        result.push(bookmark);
        node = dict.get(b"Next").ok();
    }
    Ok(result)
}
fn unicode_font(doc: &mut Document, bytes: Vec<u8>, name: &str) -> Result<(ObjectId, Vec<u8>)> {
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
    let descriptor=doc.add_object(dictionary!{"Type"=>"FontDescriptor","FontName"=>name,"Flags"=>32,"FontBBox"=>vec![scale(bbox.x_min).into(),scale(bbox.y_min).into(),scale(bbox.x_max).into(),scale(bbox.y_max).into()],"ItalicAngle"=>0,"Ascent"=>scale(face.ascender()),"Descent"=>scale(face.descender()),"CapHeight"=>scale(face.capital_height().unwrap_or(face.ascender())),"StemV"=>80,"FontFile2"=>file});
    let gidmap = doc.add_object(Stream::new(dictionary! {}, gids));
    let cid=doc.add_object(dictionary!{"Type"=>"Font","Subtype"=>"CIDFontType2","BaseFont"=>name,"CIDSystemInfo"=>dictionary!{"Registry"=>Object::string_literal("Adobe"),"Ordering"=>Object::string_literal("Identity"),"Supplement"=>0},"FontDescriptor"=>descriptor,"DW"=>1000,"W"=>widths,"CIDToGIDMap"=>gidmap});
    let cmap=b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /MPMBIdentity def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange 1 beginbfrange <0000> <FFFF> <0000> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end";
    let unicode = doc.add_object(Stream::new(dictionary! {}, cmap.to_vec()));
    Ok((doc.add_object(dictionary!{"Type"=>"Font","Subtype"=>"Type0","BaseFont"=>name,"Encoding"=>"Identity-H","DescendantFonts"=>vec![cid.into()],"ToUnicode"=>unicode}),bytes))
}
// Reuse embedded TrueType faces and their actual metrics when the field's
// requested font covers its text. Paid font bytes stay inside disposable PDFs.
struct EmbeddedFont {
    bytes: Vec<u8>,
    metrics: appearance::RichFontMetrics,
    font_name: String,
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
        let mut order = Vec::new();
        if let Ok(entries) = form.get(b"CO").and_then(Object::as_array) {
            for entry in entries {
                let id = entry
                    .as_reference()
                    .context("Non-reference calculation order entry")?;
                if let Some(name) = id_names.get(&id) {
                    order.push(CalculationEntry::Field(name.clone()));
                } else {
                    let node = doc.get_dictionary(id)?;
                    if let Ok(code) = node
                        .get(b"AA")
                        .and_then(|value| {
                            resolved(&doc, value).map_err(|_| lopdf::Error::DictKey("AA".into()))
                        })
                        .and_then(Object::as_dict)
                        .and_then(|actions| actions.get(b"C"))
                    {
                        if !action(&doc, code).is_empty() {
                            bail!("Unsupported Calculate action on a non-leaf field")
                        }
                    }
                    order.push(CalculationEntry::Preserved { reference: id });
                }
            }
        }
        let mut info = serde_json::Map::new();
        if let Ok(i) = doc
            .trailer
            .get(b"Info")
            .and_then(|v| doc.get_dictionary(v.as_reference()?))
        {
            for (k, v) in i {
                // Preserve PDF scalar types instead of forcing every Info
                // entry to text. XMP supplements these values; custom scalar
                // coercion is applied by the JavaScript info getters.
                let value = match resolved(&doc, v)? {
                    Object::Integer(value) => json!(value),
                    Object::Real(value) => json!(value),
                    Object::Boolean(value) => json!(value),
                    _ => json!(text(&doc, v)),
                };
                info.insert(String::from_utf8_lossy(k).into(), value);
            }
        }
        document_info::overlay(&doc, cat, &mut info)?;
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
            let mut ids = Vec::with_capacity(order.len());
            for entry in order {
                let entry: CalculationEntry = serde_json::from_value(entry.clone())
                    .context("Invalid calculation order entry")?;
                let id = match &entry {
                    CalculationEntry::Field(name) => {
                        fields
                            .get(name)
                            .with_context(|| format!("Missing calculation field {name}"))?
                            .id
                    }
                    CalculationEntry::Preserved { reference } => {
                        if !self.order.contains(&entry) {
                            bail!("Unrecognized preserved calculation reference")
                        }
                        doc.get_dictionary(*reference)
                            .context("Missing preserved calculation object")?;
                        *reference
                    }
                };
                ids.push(Object::Reference(id));
            }
            let root = doc.trailer.get(b"Root")?.as_reference()?;
            let form = doc.get_dictionary(root)?.get(b"AcroForm")?.as_reference()?;
            doc.get_dictionary_mut(form)?.set("CO", ids);
        }
        let icon_source = doc.clone();
        let mut embedded = embedded_fonts::collect(&doc)?;
        let mut installed_fonts = installed_fonts::Resolver::default();
        let mut font_cache = BTreeMap::new();
        let fallback_bytes = installed_fonts::fallback_bytes()?;
        let (font, font_bytes) = unicode_font(&mut doc, fallback_bytes, "MPMBDejaVuSans")?;
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
            let rich_changed = f.kind == "Tx" && s["richValueChanged"] == true;
            let rich_enabled = s["richText"].as_bool().unwrap_or(f.flags & 33554432 != 0);
            let rich_mode_changed = rich_enabled != (f.flags & 33554432 != 0);
            let style_field = f.kind == "Tx" || f.kind == "Ch";
            let font_size = s["textSize"].as_f64().unwrap_or(f.text_size);
            let font_name = s["textFont"].as_str().unwrap_or(&f.text_font);
            let text_color = s.get("textColor").unwrap_or(&f.text_color);
            let alignment = match s["alignment"].as_str() {
                Some("center") => 1,
                Some("right") => 2,
                Some("left") => 0,
                _ => f.alignment,
            };
            let da_changed = style_field
                && (font_size != f.text_size
                    || font_name != f.text_font
                    || !field_style::same(text_color, &f.text_color));
            let alignment_changed = style_field && alignment != f.alignment;
            let style_changed = da_changed || alignment_changed;
            let da = if da_changed {
                Some(
                    field_style::appearance(&doc, font_name, font_size, text_color)
                        .with_context(|| format!("Persist appearance defaults in {name}"))?,
                )
            } else {
                None
            };
            let dict = doc.get_dictionary_mut(f.id)?;
            if f.kind == "Tx"
                && rich_enabled
                && !field_style::same(&s["defaultStyle"], &f.rich_metadata["defaultStyle"])
            {
                let css = rich_text::style_css(&s["defaultStyle"])
                    .with_context(|| format!("Persist default style in {name}"))?;
                dict.set("DS", pdf_string(&css));
            }
            if changed {
                if f.kind == "Btn" {
                    if f.flags & (65536 | 32768) == 0 && value == "Off" {
                        // Reader clears a checkbox's canonical value while its
                        // widgets retain /AS /Off. Runtime still reads Off.
                        dict.remove(b"V");
                    } else {
                        dict.set("V", Object::Name(value.as_bytes().to_vec()));
                    }
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
            if f.kind == "Tx" {
                let mut flags = dict.get(b"Ff").and_then(Object::as_i64).unwrap_or(f.flags);
                for (property, mask) in [("richText", 33554432), ("multiline", 4096)] {
                    if let Some(enabled) = s[property].as_bool() {
                        flags = if enabled { flags | mask } else { flags & !mask };
                    }
                }
                dict.set("Ff", flags);
                if !rich_enabled && rich_mode_changed {
                    dict.remove(b"RV");
                } else if rich_enabled && (rich_changed || changed || rich_mode_changed) {
                    let spans = s["rawRichValue"]
                        .as_array()
                        .context("Missing raw rich spans")?;
                    let xml = rich_text::serialize(spans, &s["defaultStyle"])
                        .with_context(|| format!("Serialize rich field {name}"))?;
                    dict.set("RV", pdf_string(&xml));
                }
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
            if let Some(actions) = s["actions"].as_object() {
                for (key, code) in actions {
                    let code = code
                        .as_str()
                        .context("Field action must be JavaScript text")?;
                    if ["C", "V", "K", "F"].contains(&key.as_str()) {
                        update_action(&mut doc, f.id, key, code)?;
                    } else if ["U", "D", "Fo", "Bl"].contains(&key.as_str()) {
                        for w in &f.widgets {
                            update_action(&mut doc, w.id, key, code)?;
                        }
                    } else {
                        bail!("Unsupported persisted field action {key}")
                    }
                }
            }
            for (widget_index, w) in f.widgets.iter().enumerate() {
                let display = s["display"].as_i64().unwrap_or(f.display as i64);
                let flags = s["widgets"][widget_index]["flags"]
                    .as_i64()
                    .unwrap_or_else(|| {
                        let visibility = match display {
                            1 => 6,
                            2 => 0,
                            3 => 36,
                            _ => 4,
                        };
                        (w.flags & !(2 | 4 | 32)) | visibility
                    });
                if flags < 0 {
                    bail!("invalid widget flags for {name}")
                }
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
                // Base style assignments target widget zero in Reader, including
                // inactive template widgets. Other widgets retain their defaults.
                if widget_index == 0 {
                    if let Some(da) = &da {
                        // DA is PDF content, not a Unicode PDF text string.
                        wd.set("DA", Object::string_literal(da.as_bytes().to_vec()));
                    }
                    if alignment_changed {
                        wd.set("Q", alignment);
                    }
                }
                wd.set("F", flags);
                if f.kind == "Btn" && f.flags & 65536 != 0 {
                    buttons::project(&mut doc, &icon_source, &fields, w, &rect, s, (&face, font))?;
                    continue;
                }
                if !changed
                    && !rich_changed
                    && !rich_mode_changed
                    && !style_changed
                    && s["appearanceDirty"] != true
                {
                    continue;
                }
                if f.kind == "Btn" {
                    wd.set("AS", Object::Name(value.as_bytes().to_vec()));
                    continue;
                }
                if f.kind != "Tx" && f.kind != "Ch" {
                    continue;
                }
                // noView fields still need fresh appearances for printing.
                if w.page < 0 || flags & 2 != 0 {
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
                let rich_fonts = appearance::rich_font_candidates(s);
                if s["richRenderActive"] == true {
                    let mut requested_faces = vec![rich_fonts.clone()];
                    if let Some(name) = s["textFont"].as_str() {
                        requested_faces.push(vec![name.to_owned()]);
                    }
                    if let Some(spans) = s["richValue"].as_array() {
                        for span in spans {
                            let span_state = json!({"richRenderActive":true,"richValue":[span],"defaultStyle":s["defaultStyle"]});
                            requested_faces.push(appearance::rich_font_candidates(&span_state));
                        }
                    }
                    for candidates in requested_faces {
                        if candidates.iter().any(|name| embedded.contains_key(name)) {
                            continue;
                        }
                        for candidate in candidates {
                            installed_fonts.resolve(&candidate, &mut embedded);
                            if embedded.contains_key(&candidate) {
                                break;
                            }
                        }
                    }
                    // CSS families are not necessarily PostScript names (Arial
                    // versus ArialMT). Validate family/style identity separately.
                    let resolve_family =
                        |alias: &str,
                         style: &Value,
                         resolver: &mut installed_fonts::Resolver,
                         fonts: &mut BTreeMap<String, EmbeddedFont>| {
                            if let Some(family) = style["fontFamily"]
                                .as_array()
                                .and_then(|names| names.first())
                                .and_then(Value::as_str)
                            {
                                resolver.resolve_family(
                                    alias,
                                    family,
                                    u16::try_from(style["fontWeight"].as_u64().unwrap_or(400))
                                        .unwrap_or(400),
                                    matches!(
                                        style["fontStyle"].as_str(),
                                        Some("italic" | "oblique")
                                    ),
                                    fonts,
                                );
                            }
                        };
                    if let Some(alias) = s["textFont"].as_str() {
                        resolve_family(
                            alias,
                            &s["defaultStyle"],
                            &mut installed_fonts,
                            &mut embedded,
                        );
                    }
                    if let Some(spans) = s["richValue"].as_array() {
                        for span in spans {
                            let span_state = json!({"richRenderActive":true,"richValue":[span],"defaultStyle":s["defaultStyle"]});
                            let candidates = appearance::rich_font_candidates(&span_state);
                            if !candidates.iter().any(|name| embedded.contains_key(name)) {
                                if let Some(alias) = candidates.first() {
                                    resolve_family(
                                        alias,
                                        span,
                                        &mut installed_fonts,
                                        &mut embedded,
                                    );
                                }
                            }
                        }
                    }
                }
                let requested = rich_fonts
                    .iter()
                    .find(|name| embedded.contains_key(*name))
                    .map(String::as_str)
                    .unwrap_or_else(|| s["textFont"].as_str().unwrap_or(&f.text_font));
                let render_text = if let Some(spans) = s["richValue"]
                    .as_array()
                    .filter(|v| !v.is_empty() || s["richRenderActive"] == true)
                {
                    spans
                        .iter()
                        .filter_map(|v| v["text"].as_str())
                        .collect::<String>()
                } else {
                    appearance::display_text(f, s, &value)
                };
                let covers = |name: &str, text: &str| {
                    embedded.get(name).is_some_and(|font| {
                        ttf_parser::Face::parse(&font.bytes, 0).is_ok_and(|face| {
                            text.chars()
                                .all(|c| c.is_control() || face.glyph_index(c).is_some())
                        })
                    })
                };
                let base = covers(requested, &render_text).then(|| requested.to_owned());
                let mut selected = vec![base.clone()];
                let mut span_fonts = Vec::new();
                if let Some(spans) = s["richValue"]
                    .as_array()
                    .filter(|spans| !spans.is_empty() || s["richRenderActive"] == true)
                {
                    for span in spans {
                        let text = span["text"].as_str().unwrap_or("");
                        let span_state = json!({"richRenderActive":true,"richValue":[span],"defaultStyle":s["defaultStyle"]});
                        let candidates = appearance::rich_font_candidates(&span_state);
                        let chosen = candidates
                            .into_iter()
                            .find(|name| covers(name, text))
                            .or_else(|| base.as_ref().filter(|name| covers(name, text)).cloned());
                        let index = selected
                            .iter()
                            .position(|name| *name == chosen)
                            .unwrap_or_else(|| {
                                selected.push(chosen);
                                selected.len() - 1
                            });
                        span_fonts.push(index);
                    }
                }
                for key in selected.iter().flatten() {
                    if !font_cache.contains_key(key) {
                        let asset = &embedded[key];
                        let mapped = unicode_font(
                            &mut doc,
                            asset.bytes.clone(),
                            &format!("MPMB{}", asset.font_name),
                        )?;
                        font_cache.insert(key.clone(), mapped);
                    }
                }
                let default_metrics = field_style::widget_font(&doc, w.id)?
                    .and_then(|name| embedded.get(&name).map(|font| font.metrics));
                let metrics = base
                    .as_ref()
                    .map(|key| embedded[key].metrics)
                    .unwrap_or_else(|| appearance::RichFontMetrics::from_face(&face, None));
                let metrics = default_metrics
                    .map(|defaults| metrics.with_default_bounds(defaults))
                    .unwrap_or(metrics);
                let mut font_resources = Dictionary::new();
                let mut render_fonts = Vec::new();
                for (index, key) in selected.iter().enumerate() {
                    let resource = if index == 0 {
                        "Helv".to_owned()
                    } else {
                        format!("Rich{index}")
                    };
                    let id = key.as_ref().map(|key| font_cache[key].0).unwrap_or(font);
                    // Each parsed face borrows its existing cache bytes; no field
                    // state is created by the appearance renderer.
                    let parsed = if let Some(key) = key {
                        ttf_parser::Face::parse(&font_cache[key].1, 0)?
                    } else {
                        ttf_parser::Face::parse(&font_bytes, 0)?
                    };
                    font_resources.set(resource.as_bytes().to_vec(), id);
                    render_fonts.push(appearance::RenderFont {
                        face: parsed,
                        resource,
                    });
                }
                let layout = appearance::FontLayout {
                    fonts: render_fonts,
                    span_fonts,
                    metrics,
                };
                let inset = field_style::plain_text_inset(&doc, w.id)?;
                let content =
                    appearance::content_with_fonts(&layout, width, height, f, s, &value, inset)?;
                let ap=doc.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),width.into(),height.into()],"Resources"=>dictionary!{"Font"=>font_resources}},content));
                doc.get_dictionary_mut(w.id)?
                    .set("AP", dictionary! {"N"=>ap});
            }
        }
        if let Some(bookmarks) = state.get("__bookmarks") {
            bookmark_tree::project(&mut doc, bookmarks)?;
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

fn update_action(doc: &mut Document, id: ObjectId, key: &str, code: &str) -> Result<()> {
    let mut aa = doc
        .get_dictionary(id)?
        .get(b"AA")
        .ok()
        .and_then(|v| resolved(doc, v).ok())
        .and_then(|v| v.as_dict().ok())
        .cloned()
        .unwrap_or_default();
    if code.is_empty() {
        aa.remove(key.as_bytes());
    } else {
        aa.set(key, dictionary! {"S"=>"JavaScript","JS"=>pdf_string(code)});
    }
    doc.get_dictionary_mut(id)?.set("AA", aa);
    Ok(())
}
#[cfg(test)]
mod action_tests {
    use super::*;
    #[test]
    fn unset_checkbox_value_is_logical_off_without_changing_the_pdf() {
        let mut doc = Document::new();
        for (flags, stored, expected) in [
            (0, None, "Off"),
            (0, Some(""), "Off"),
            (0, Some("True"), "True"),
            (32768, None, "Off"),
            (65536, None, ""),
        ] {
            let mut field =
                dictionary! {"FT"=>"Btn","Ff"=>flags,"T"=>Object::string_literal("Check")};
            if let Some(value) = stored {
                field.set("V", Object::string_literal(value));
            }
            let id = doc.add_object(field.clone());
            let mut fields = BTreeMap::new();
            walk(
                &doc,
                &id.into(),
                "",
                &Dictionary::new(),
                &BTreeMap::new(),
                &mut fields,
            )
            .unwrap();
            assert_eq!(fields["Check"].value, json!(expected));
            assert_eq!(doc.get_dictionary(id).unwrap(), &field);
        }
    }
    #[test]
    fn changed_action_retains_unrelated_actions_and_does_not_modify_shared_source() {
        let mut doc = Document::new();
        let shared=doc.add_object(dictionary!{"C"=>dictionary!{"S"=>"JavaScript","JS"=>Object::string_literal("event.value=1")},"F"=>dictionary!{"S"=>"JavaScript","JS"=>Object::string_literal("event.value='formatted'")}});
        let field = doc.add_object(dictionary! {"AA"=>shared});
        update_action(&mut doc, field, "C", "event.value=2").unwrap();
        let aa = doc
            .get_dictionary(field)
            .unwrap()
            .get(b"AA")
            .unwrap()
            .as_dict()
            .unwrap();
        assert_eq!(action(&doc, aa.get(b"C").unwrap()), "event.value=2");
        assert!(aa.has(b"F"));
        assert_eq!(
            action(&doc, doc.get_dictionary(shared).unwrap().get(b"C").unwrap()),
            "event.value=1"
        );
        update_action(&mut doc, field, "C", "").unwrap();
        let aa = doc
            .get_dictionary(field)
            .unwrap()
            .get(b"AA")
            .unwrap()
            .as_dict()
            .unwrap();
        assert!(!aa.has(b"C"));
        assert!(aa.has(b"F"));
    }
}
