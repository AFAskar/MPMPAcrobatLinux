//! Embedded TrueType assets, including Type0 faces in saved appearances.
use super::{appearance::RichFontMetrics, resolved, EmbeddedFont};
use anyhow::Result;
use lopdf::{Dictionary, Document, Object};
use std::collections::BTreeMap;

fn read(
    doc: &Document,
    font: &Dictionary,
    resource_name: Option<String>,
) -> Result<Option<EmbeddedFont>> {
    let font = if font.has(b"FontDescriptor") {
        font
    } else {
        let Some(descendant) = font
            .get(b"DescendantFonts")
            .ok()
            .and_then(|value| resolved(doc, value).ok())
            .and_then(|value| value.as_array().ok())
            .and_then(|values| values.first())
            .and_then(|value| resolved(doc, value).ok())
            .and_then(|value| value.as_dict().ok())
        else {
            return Ok(None);
        };
        descendant
    };
    let Some(descriptor) = font
        .get(b"FontDescriptor")
        .ok()
        .and_then(|value| resolved(doc, value).ok())
        .and_then(|value| value.as_dict().ok())
    else {
        return Ok(None);
    };
    let Some(stream) = descriptor
        .get(b"FontFile2")
        .ok()
        .and_then(|value| resolved(doc, value).ok())
        .and_then(|value| value.as_stream().ok())
    else {
        return Ok(None);
    };
    let bytes = if stream.dict.has(b"Filter") {
        stream.decompressed_content()?
    } else {
        stream.content.clone()
    };
    let Ok(face) = ttf_parser::Face::parse(&bytes, 0) else {
        return Ok(None);
    };
    let Some(font_name) = resource_name.or_else(|| {
        face.names()
            .into_iter()
            .filter(|entry| entry.name_id == ttf_parser::name_id::POST_SCRIPT_NAME)
            .find_map(|entry| entry.to_string())
    }) else {
        return Ok(None);
    };
    let bbox = face.global_bounding_box();
    let fallback = (f32::from(bbox.y_max) - f32::from(bbox.y_min)) / f32::from(face.units_per_em());
    let bbox_height = descriptor
        .get(b"FontBBox")
        .ok()
        .and_then(|value| resolved(doc, value).ok())
        .and_then(|value| value.as_array().ok())
        .and_then(|values| {
            Some((values.get(3)?.as_float().ok()? - values.get(1)?.as_float().ok()?) / 1000.)
        })
        .filter(|value| value.is_finite() && *value > 0.)
        .unwrap_or(fallback);
    let mut metrics = RichFontMetrics::from_face(&face, Some(bbox_height));
    let metric = |key: &[u8]| {
        descriptor
            .get(key)
            .ok()
            .and_then(|value| resolved(doc, value).ok())
            .and_then(|value| value.as_float().ok())
            .map(|value| value / 1000.)
    };
    if let (Some(ascent), Some(descent)) = (metric(b"Ascent"), metric(b"Descent")) {
        metrics = metrics.with_pdf_vertical_metrics(ascent, descent);
    }
    Ok(Some(EmbeddedFont {
        bytes,
        metrics,
        font_name,
    }))
}

pub(super) fn collect(doc: &Document) -> Result<BTreeMap<String, EmbeddedFont>> {
    let mut result = BTreeMap::new();
    let form = resolved(doc, doc.catalog()?.get(b"AcroForm")?)?.as_dict()?;
    if let Some(fonts) = form
        .get(b"DR")
        .ok()
        .and_then(|value| resolved(doc, value).ok())
        .and_then(|value| value.as_dict().ok())
        .and_then(|resources| resources.get(b"Font").ok())
        .and_then(|value| resolved(doc, value).ok())
        .and_then(|value| value.as_dict().ok())
    {
        for (key, value) in fonts {
            let name = String::from_utf8_lossy(key).into_owned();
            if let Some(asset) = read(doc, resolved(doc, value)?.as_dict()?, Some(name.clone()))? {
                result.insert(name, asset);
            }
        }
    }
    // Projection fonts are self-contained Type0 resources. Looking only in
    // AcroForm/DR loses their faces when a saved field is edited on a machine
    // without the system font. The font program supplies its real identity;
    // generated AP resource keys (Helv/Rich1/...) are not font family names.
    for object in doc.objects.values() {
        let Object::Dictionary(font) = object else {
            continue;
        };
        if font.get(b"Subtype").and_then(Object::as_name).ok() != Some(b"Type0".as_slice()) {
            continue;
        }
        if let Some(asset) = read(doc, font, None)? {
            result.entry(asset.font_name.clone()).or_insert(asset);
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use lopdf::dictionary;
    #[test]
    fn type0_appearance_faces_are_discovered_without_default_resources() {
        let bytes = std::fs::read(crate::pdf::installed_fonts::test_font_path(
            "DejaVuSans-Bold",
        ))
        .unwrap();
        let mut doc = Document::with_version("1.7");
        let form = doc.add_object(dictionary! {"DR"=>dictionary!{"Font"=>dictionary!{}}});
        let root = doc.add_object(dictionary! {"Type"=>"Catalog","AcroForm"=>form});
        doc.trailer.set("Root", root);
        super::super::unicode_font(&mut doc, bytes.clone(), "MPMBDejaVuSans-Bold").unwrap();
        let fonts = collect(&doc).unwrap();
        let recovered = &fonts["DejaVuSans-Bold"];
        assert_eq!(recovered.bytes, bytes);
        assert_eq!(recovered.font_name, "DejaVuSans-Bold");
        assert!(ttf_parser::Face::parse(&recovered.bytes, 0)
            .unwrap()
            .glyph_index('W')
            .is_some());
        assert!(!fonts.contains_key("MPMBDejaVuSans-Bold"));
    }
}
