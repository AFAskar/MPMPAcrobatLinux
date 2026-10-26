use super::*;
// A button icon is a reference to an original document resource, never a raster
// copy or a second mutable form value. The live JS model resolves icon swaps.
pub(super) fn project(
    doc: &mut Document,
    source_doc: &Document,
    fields: &BTreeMap<String, Field>,
    widget: &Widget,
    rect: &[f64],
    state: &Value,
    face: &ttf_parser::Face<'_>,
    font: ObjectId,
) -> Result<()> {
    let icon = state["icon"]["field"].as_str();
    let caption = state["caption"].as_str();
    if icon.is_none() && caption.is_none() {
        return Ok(());
    }
    if rect.len() != 4 {
        bail!("Button has invalid rectangle")
    }
    let width = (rect[2] - rect[0]).abs() as f32;
    let height = (rect[3] - rect[1]).abs() as f32;
    let mut mk = doc
        .get_dictionary(widget.id)?
        .get(b"MK")
        .ok()
        .and_then(|v| resolved(source_doc, v).ok())
        .and_then(|v| v.as_dict().ok())
        .cloned()
        .unwrap_or_default();
    let mut resources = dictionary! {"Font"=>dictionary!{"Helv"=>font}};
    let mut content = Vec::new();
    if let Some(name) = icon {
        let field = fields.get(name).context("Icon source field not found")?;
        let source = field.widgets.first().context("Icon source has no widget")?;
        let wd = source_doc.get_dictionary(source.id)?;
        let source_icon = wd
            .get(b"MK")
            .ok()
            .and_then(|v| resolved(source_doc, v).ok())
            .and_then(|v| v.as_dict().ok())
            .and_then(|v| v.get(b"I").ok())
            .or_else(|| {
                wd.get(b"AP")
                    .ok()
                    .and_then(|v| resolved(source_doc, v).ok())
                    .and_then(|v| v.as_dict().ok())
                    .and_then(|v| v.get(b"N").ok())
            })
            .cloned();
        if let Some(source_icon) = source_icon {
            let stream = resolved(source_doc, &source_icon)?.as_stream()?;
            let bounds = stream.dict.get(b"BBox")?.as_array()?;
            let b: Vec<f32> = bounds.iter().map(|x| x.as_float().unwrap_or(0.)).collect();
            if b.len() != 4 || b[2] <= b[0] || b[3] <= b[1] {
                bail!("Invalid button icon bounds")
            }
            // The original icon's Matrix is applied by Do. Its transformed bounds
            // must also be used for fit/alignment (including quarter-turn rotations).
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
                bail!("Invalid icon matrix")
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
            let scale = (width / (maxx - minx)).min(height / (maxy - miny));
            if !scale.is_finite() {
                bail!("Degenerate button icon")
            }
            let x = (width - (maxx - minx) * scale) / 2. - minx * scale;
            let y = (height - (maxy - miny) * scale) / 2. - miny * scale;
            content.extend(format!("q {scale} 0 0 {scale} {x} {y} cm /Icon Do Q\n").as_bytes());
            resources.set("XObject", dictionary! {"Icon"=>source_icon.clone()});
            mk.set("I", source_icon);
        } else {
            mk.remove(b"I");
        }
    }
    if let Some(caption) = caption {
        mk.set("CA", pdf_string(caption));
        if !caption.is_empty() {
            let mut s = state.clone();
            s["formatted"] = json!(caption);
            let target = fields
                .values()
                .find(|f| f.widgets.iter().any(|w| w.id == widget.id))
                .context("Button field missing")?;
            content.extend(appearance::content(
                face, width, height, target, &s, caption,
            )?);
        }
    }
    let ap=doc.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),width.into(),height.into()],"Resources"=>resources},content));
    let mut ap_dict = dictionary! {"N"=>ap};
    for (face, key, ap_key) in [(1, "RC", "R"), (2, "AC", "D")] {
        if let Some(caption) = state["captions"][face.to_string()].as_str() {
            if caption != state["caption"].as_str().unwrap_or("") {
                bail!("Distinct rollover/down button captions are unsupported")
            }
            mk.set(key, pdf_string(caption));
            ap_dict.set(ap_key, ap);
        }
    }
    let wd = doc.get_dictionary_mut(widget.id)?;
    wd.set("MK", mk);
    wd.set("AP", ap_dict);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_source_icon_clears_previous_resource_and_keeps_button_faces() {
        let mut doc = Document::new();
        let source=doc.add_object(dictionary!{"Subtype"=>"Widget","FT"=>"Btn","Ff"=>65536,"T"=>Object::string_literal("Empty"),"Rect"=>vec![0.into(),0.into(),20.into(),20.into()]});
        let previous=doc.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),20.into(),20.into()]},b"q Q".to_vec()));
        let target=doc.add_object(dictionary!{"Subtype"=>"Widget","FT"=>"Btn","Ff"=>65536,"T"=>Object::string_literal("Target"),"Rect"=>vec![0.into(),0.into(),20.into(),20.into()],"MK"=>dictionary!{"I"=>previous},"AP"=>dictionary!{"N"=>previous}});
        let mut fields = BTreeMap::new();
        for id in [source, target] {
            walk(
                &doc,
                &id.into(),
                "",
                &Dictionary::new(),
                &BTreeMap::new(),
                &mut fields,
            )
            .unwrap();
        }
        let bytes = std::fs::read(
            std::env::var("MPMB_FONT")
                .unwrap_or_else(|_| "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf".into()),
        )
        .unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let pristine = doc.clone();
        project(
            &mut doc,
            &pristine,
            &fields,
            &fields["Target"].widgets[0],
            &[0., 0., 20., 20.],
            &json!({"icon":{"field":"Empty"},"caption":"","captions":{"0":"","1":"","2":""}}),
            &face,
            (999, 0),
        )
        .unwrap();
        let wd = doc.get_dictionary(target).unwrap();
        let mk = wd.get(b"MK").unwrap().as_dict().unwrap();
        assert!(!mk.has(b"I"));
        assert!(mk.has(b"RC") && mk.has(b"AC"));
        let ap = wd.get(b"AP").unwrap().as_dict().unwrap();
        assert_eq!(ap.get(b"N").unwrap(), ap.get(b"R").unwrap());
        assert_eq!(ap.get(b"N").unwrap(), ap.get(b"D").unwrap());
        assert!(resolved(&doc, ap.get(b"N").unwrap())
            .unwrap()
            .as_stream()
            .unwrap()
            .content
            .is_empty());
    }
}
