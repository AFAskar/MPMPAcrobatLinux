//! Plain and rich text layout for generated widget appearances.
use super::*;
/// A changed default font must not replace the font on existing rich spans.
/// A homogeneous face can use its original embedded font. The projection also
/// calls this for individual spans when a field contains several faces.
pub(super) fn rich_font_candidates(state: &Value) -> Vec<String> {
    if state["richRenderActive"] != true {
        return vec![];
    }
    let Some(spans) = state["richValue"].as_array() else {
        return vec![];
    };
    let mut faces = spans
        .iter()
        .filter(|span| span["text"].as_str().is_some_and(|text| !text.is_empty()))
        .map(|span| {
            (
                span["fontFamily"][0].as_str(),
                span["fontWeight"].as_u64().unwrap_or(400),
                span["fontStyle"].as_str().unwrap_or("normal"),
            )
        });
    let Some(face) = faces.next() else {
        return vec![];
    };
    if faces.any(|next| next != face) {
        return vec![];
    }
    let defaults = &state["defaultStyle"];
    if face
        == (
            defaults["fontFamily"][0].as_str(),
            defaults["fontWeight"].as_u64().unwrap_or(400),
            defaults["fontStyle"].as_str().unwrap_or("normal"),
        )
    {
        // Preserve custom font resource names already represented by the field.
        return vec![];
    }
    let Some(family) = face.0 else { return vec![] };
    let base = match family {
        "Segoe UI" => "SegoeUI",
        _ => family,
    };
    let bold = match face.1 {
        400 => false,
        700 => true,
        _ => return vec![],
    };
    let italic = match face.2 {
        "normal" => false,
        "italic" | "oblique" => true,
        _ => return vec![],
    };
    let suffix = match (bold, italic) {
        (false, false) => return vec![base.into()],
        (true, false) => "Bold",
        (false, true) => "Italic",
        (true, true) => "BoldItalic",
    };
    vec![format!("{base},{suffix}"), format!("{base}-{suffix}")]
}

#[derive(Clone, Copy)]
pub(super) struct RichFontMetrics {
    bbox_height: f32,
    single_line_bounds: Option<(f32, f32)>,
    ascent: f32,
    line_gap: f32,
}
impl RichFontMetrics {
    pub(super) fn with_pdf_vertical_metrics(mut self, ascent: f32, descent: f32) -> Self {
        if ascent.is_finite() && descent.is_finite() && ascent > descent {
            self.single_line_bounds = Some((ascent, descent));
        }
        self
    }
    pub(super) fn with_default_bounds(mut self, defaults: Self) -> Self {
        self.bbox_height = defaults.bbox_height;
        self
    }
    pub(super) fn from_face(face: &ttf_parser::Face<'_>, bbox_height: Option<f32>) -> Self {
        let units = f32::from(face.units_per_em());
        // Reader truncates through 16-bit fixed point before PDF's 1000-unit
        // metrics. Decimal design metrics can lose one more unit (e.g. .868).
        let normalized = |n: f64| normalized_metric(n, f64::from(face.units_per_em()));
        let bbox = face.global_bounding_box();
        Self {
            single_line_bounds: None,
            bbox_height: bbox_height
                .unwrap_or((f32::from(bbox.y_max) - f32::from(bbox.y_min)) / units),
            ascent: normalized(f64::from(
                face.typographic_ascender()
                    .filter(|n| *n != 0)
                    .unwrap_or(face.ascender()),
            )),
            line_gap: normalized(
                f64::from(face.typographic_line_gap().unwrap_or(face.line_gap())).abs(),
            ),
        }
    }
}

fn normalized_metric(value: f64, units: f64) -> f32 {
    (((value / units * 65536.).floor() / 65536. * 1000.).floor() / 1000.) as f32
}

fn first_rich_offset(
    first: f32,
    largest: f32,
    spacing: Option<f32>,
    metrics: RichFontMetrics,
) -> f32 {
    // Mixed first lines start from the first span's default bounds, adding
    // typographic ascent/gap for larger runs. Reader omits the largest run's
    // external gap when explicit leading is shorter than that run's em size.
    first * metrics.bbox_height + (largest - first) * (metrics.ascent + metrics.line_gap)
        - if spacing.is_some_and(|spacing| spacing < largest) {
            largest * metrics.line_gap
        } else {
            0.
        }
}

pub(super) struct RenderFont<'a> {
    pub face: ttf_parser::Face<'a>,
    pub resource: String,
}
pub(super) struct FontLayout<'a> {
    pub fonts: Vec<RenderFont<'a>>,
    pub span_fonts: Vec<usize>,
    pub metrics: RichFontMetrics,
}
impl FontLayout<'_> {
    fn width(&self, glyph: &Glyph) -> f32 {
        width(&self.fonts[glyph.font].face, glyph)
    }
}

#[derive(Clone)]
struct Glyph {
    c: char,
    size: f32,
    color: [f32; 3],
    spacing: Option<f32>,
    alignment: Option<u8>,
    font: usize,
    decoration: u8,
}
fn width(face: &ttf_parser::Face<'_>, g: &Glyph) -> f32 {
    if g.c == '\n' {
        return 0.;
    }
    face.glyph_index(g.c)
        .and_then(|id| face.glyph_hor_advance(id))
        .unwrap_or(face.units_per_em() / 2) as f32
        * g.size
        / face.units_per_em() as f32
}
fn lines(
    measure: &impl Fn(&Glyph) -> f32,
    glyphs: Vec<Glyph>,
    max_width: f32,
    wrap: bool,
) -> Vec<Vec<Glyph>> {
    let mut result = Vec::new();
    let mut line: Vec<Glyph> = Vec::new();
    let mut current = 0.;
    let mut soft_start = false;
    for glyph in glyphs {
        if glyph.c == '\n' {
            // A blank rich line still carries the newline span's font size.
            line.push(glyph);
            result.push(std::mem::take(&mut line));
            current = 0.;
            soft_start = false;
            continue;
        }
        let added = measure(&glyph);
        if wrap && current + added > max_width && !line.is_empty() {
            if let Some(space) = line.iter().rposition(|g| g.c == ' ') {
                let tail = line.split_off(space + 1);
                line.pop();
                result.push(std::mem::replace(&mut line, tail));
                current = line.iter().map(measure).sum();
            } else {
                result.push(std::mem::take(&mut line));
                current = 0.;
            }
            soft_start = line.is_empty();
        }
        if glyph.c == ' ' && line.is_empty() && soft_start {
            continue;
        }
        soft_start = false;
        current += added;
        line.push(glyph);
    }
    result.push(line);
    result
}
fn rgb(v: &Value) -> [f32; 3] {
    let Some(c) = v.as_array() else {
        return [0.; 3];
    };
    match c.first().and_then(Value::as_str) {
        Some("RGB") if c.len() == 4 => [
            c[1].as_f64().unwrap_or(0.) as f32,
            c[2].as_f64().unwrap_or(0.) as f32,
            c[3].as_f64().unwrap_or(0.) as f32,
        ],
        Some("G") if c.len() == 2 => [c[1].as_f64().unwrap_or(0.) as f32; 3],
        _ => [0.; 3],
    }
}
pub(super) fn display_text(field: &Field, state: &Value, value: &str) -> String {
    let formatted = match state.get("formatted") {
        Some(Value::String(s)) => s.clone(),
        Some(v @ (Value::Number(_) | Value::Bool(_))) => v.to_string(),
        _ => value.to_owned(),
    };
    if field.kind == "Ch" && !field.actions.contains_key("F") {
        state["items"]
            .as_array()
            .and_then(|items| {
                items.iter().find_map(|item| {
                    let pair = item.as_array()?;
                    if pair.first()?.as_str()? == value {
                        pair.get(1)?.as_str().map(str::to_owned)
                    } else {
                        None
                    }
                })
            })
            .unwrap_or(formatted)
    } else {
        formatted
    }
}
pub(super) fn content(
    face: &ttf_parser::Face<'_>,
    width_box: f32,
    height: f32,
    field: &Field,
    state: &Value,
    value: &str,
    font_metrics: Option<RichFontMetrics>,
) -> Result<Vec<u8>> {
    let layout = FontLayout {
        fonts: vec![RenderFont {
            face: face.clone(),
            resource: "Helv".into(),
        }],
        span_fonts: vec![],
        metrics: font_metrics.unwrap_or_else(|| RichFontMetrics::from_face(face, None)),
    };
    content_with_fonts(&layout, width_box, height, field, state, value)
}
pub(super) fn content_with_fonts(
    layout: &FontLayout<'_>,
    width_box: f32,
    height: f32,
    field: &Field,
    state: &Value,
    value: &str,
) -> Result<Vec<u8>> {
    let face = &layout.fonts[0].face;
    let measure = |glyph: &Glyph| layout.width(glyph);
    let wrap = state["multiline"]
        .as_bool()
        .unwrap_or(field.flags & 4096 != 0);
    let spans = state["richValue"]
        .as_array()
        .filter(|v| !v.is_empty() || state["richRenderActive"] == true);
    if let Some(spans) = spans {
        for span in spans {
            if let Some(alignment) = span["alignment"].as_str() {
                if !["left", "center", "right"].contains(&alignment) {
                    bail!(
                        "Unsupported rich paragraph alignment in {}: {alignment}",
                        field.name
                    )
                }
            }
        }
    }
    let explicit = state["textSize"].as_f64().unwrap_or(field.text_size) as f32;
    let mut size = if explicit > 0. {
        explicit
    } else if wrap {
        9.
    } else {
        (height - 3.).clamp(4., 18.)
    };
    let formatted = display_text(field, state, value);
    let color = rgb(&state["textColor"]);
    let available = (width_box - if spans.is_some() { 0. } else { 2. }).max(1.);
    let make = |size: f32| -> Vec<Glyph> {
        if let Some(spans) = spans {
            spans
                .iter()
                .enumerate()
                .flat_map(|(span_index, span)| {
                    let font = layout.span_fonts.get(span_index).copied().unwrap_or(0);
                    let size = span["textSize"].as_f64().map(|v| v as f32).unwrap_or(size);
                    let color = if span.get("textColor").is_some() {
                        rgb(&span["textColor"])
                    } else {
                        color
                    };
                    let mut text = span["text"].as_str().unwrap_or("").replace('\r', "\n");
                    if span["endParagraph"] == true && !text.ends_with('\n') {
                        text.push('\n');
                    }
                    let spacing = span["linespacing"]
                        .as_f64()
                        .map(|n| n as f32)
                        .filter(|n| *n > 0.);
                    text.chars()
                        .map(move |c| Glyph {
                            c,
                            size,
                            color,
                            spacing,
                            font,
                            decoration: u8::from(span["underline"] == true)
                                | (u8::from(span["strikethrough"] == true) << 1),
                            alignment: match span["alignment"].as_str() {
                                Some("left") => Some(0),
                                Some("center") => Some(1),
                                Some("right") => Some(2),
                                _ => None,
                            },
                        })
                        .collect::<Vec<_>>()
                })
                .collect()
        } else {
            formatted
                .replace('\r', "\n")
                .chars()
                .map(|c| Glyph {
                    c,
                    size,
                    color,
                    spacing: None,
                    alignment: None,
                    font: 0,
                    decoration: 0,
                })
                .collect()
        }
    };
    let mut laid = lines(&measure, make(size), available, wrap);
    if explicit == 0. && spans.is_none() {
        loop {
            let too_tall = wrap && laid.len() as f32 * size * 1.12 > height - 2.;
            let too_wide = !wrap
                && laid
                    .iter()
                    .any(|line| line.iter().map(&measure).sum::<f32>() > available);
            if !(too_tall || too_wide) || size <= 3. {
                break;
            }
            size = (size - 0.25).max(3.);
            laid = lines(&measure, make(size), available, wrap);
        }
    }
    let mut out = format!("/Tx BMC q 0 0 {width_box} {height} re W n BT ");
    let mut decorations = String::new();
    let line_sizes: Vec<f32> = laid
        .iter()
        .map(|line| line.iter().map(|g| g.size).reduce(f32::max).unwrap_or(size))
        .collect();
    let line_spacings: Vec<Option<f32>> = laid
        .iter()
        .map(|line| line.iter().filter_map(|g| g.spacing).reduce(f32::max))
        .collect();
    let units = face.units_per_em() as f32;
    // Single-line centering uses the PDF descriptor, which need not equal the
    // embedded TrueType hhea metrics. Rich baseline/leading metrics are separate.
    let (ascent, descent) = layout.metrics.single_line_bounds.unwrap_or((
        face.ascender() as f32 / units,
        face.descender() as f32 / units,
    ));
    let rich_metrics = layout.metrics;
    let mut y = if spans.is_some() {
        let first = laid
            .first()
            .and_then(|line| line.first())
            .map(|g| g.size)
            .unwrap_or(size);
        height
            - first_rich_offset(
                first,
                line_sizes.first().copied().unwrap_or(size),
                line_spacings.first().copied().flatten(),
                rich_metrics,
            )
    } else if wrap {
        height - 1. - line_sizes.first().copied().unwrap_or(size)
    } else {
        (height - ascent * size + descent * size) / 2. - descent * size
    };
    for (line_index, line) in laid.into_iter().enumerate() {
        let line_size = line_sizes[line_index];
        let alignment = line.iter().find_map(|g| g.alignment).unwrap_or_else(|| {
            match state["alignment"].as_str() {
                Some("center") => 1,
                Some("right") => 2,
                _ => 0,
            }
        });
        let line: Vec<_> = line.into_iter().filter(|g| g.c != '\n').collect();
        let total = line.iter().map(&measure).sum::<f32>();
        let mut x = match alignment {
            1 => (width_box - total) / 2.,
            2 => width_box - 1. - total,
            _ => {
                if spans.is_some() {
                    0.
                } else {
                    1.
                }
            }
        };
        let mut start = 0;
        while start < line.len() {
            let mut end = start + 1;
            while end < line.len()
                && line[end].size == line[start].size
                && line[end].color == line[start].color
                && line[end].font == line[start].font
                && line[end].decoration == line[start].decoration
            {
                end += 1
            }
            let run = &line[start..end];
            let first = &run[0];
            let mut encoded = String::new();
            for g in run {
                if g.c as u32 > 65535 {
                    bail!(
                        "appearance font encoding does not support non-BMP text in {}",
                        field.name
                    )
                }
                if layout.fonts[g.font].face.glyph_index(g.c).is_none() && !g.c.is_control() {
                    bail!(
                        "appearance font lacks glyph U+{:04X} in {}",
                        g.c as u32,
                        field.name
                    )
                }
                encoded.push_str(&format!("{:04X}", g.c as u32));
            }
            out.push_str(&format!(
                "/{} {} Tf {} {} {} rg 1 0 0 1 {x} {y} Tm <{encoded}> Tj ",
                layout.fonts[first.font].resource,
                first.size,
                first.color[0],
                first.color[1],
                first.color[2]
            ));
            let advance = run.iter().map(&measure).sum::<f32>();
            let face = &layout.fonts[first.font].face;
            for (flag, metrics) in [(1, face.underline_metrics()), (2, face.strikeout_metrics())] {
                if first.decoration & flag == 0 {
                    continue;
                }
                let metrics = metrics
                    .filter(|metrics| metrics.thickness > 0)
                    .with_context(|| {
                        format!("Appearance font lacks decoration metrics in {}", field.name)
                    })?;
                let scale = first.size / f32::from(face.units_per_em());
                // OpenType positions specify the top edge; PDF strokes use
                // their center line. Reader's own decoration geometry remains
                // a separate qualification from these native font metrics.
                let line_y =
                    y + (f32::from(metrics.position) - f32::from(metrics.thickness) / 2.) * scale;
                let thickness = f32::from(metrics.thickness) * scale;
                let end_x = x + advance;
                decorations.push_str(&format!(
                    "{} {} {} RG {thickness} w {x} {line_y} m {end_x} {line_y} l S ",
                    first.color[0], first.color[1], first.color[2]
                ));
            }
            x += advance;
            start = end;
        }
        y -= if spans.is_some() {
            let next = line_sizes.get(line_index + 1).copied().unwrap_or(line_size);
            let leading = line_spacings[line_index].unwrap_or(next * (1. + rich_metrics.line_gap));
            leading + (line_size - next) * (1. - rich_metrics.ascent)
        } else {
            line_size * 1.12
        };
    }
    out.push_str("ET ");
    out.push_str(&decorations);
    out.push_str("Q EMC");
    Ok(out.into_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn field() -> Field {
        Field {
            name: "format regression".into(),
            id: (1, 0),
            value: json!("10+Dex"),
            default_value: json!(""),
            kind: "Tx".into(),
            user_name: String::new(),
            submit_name: String::new(),
            flags: 0,
            alignment: 0,
            display: 0,
            text_size: 7.,
            text_font: String::new(),
            text_color: json!(["G", 0]),
            rich_metadata: json!({}),
            widgets: vec![],
            actions: BTreeMap::new(),
            items: vec![],
            export_values: vec![],
            caption: String::new(),
        }
    }
    #[test]
    fn single_line_center_uses_pdf_descriptor_without_replacing_rich_metrics() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        // Reader's original generated spell description: height 10.48, size
        // 6.25, PDF ascent/descent 1159/-411, saved baseline 2.903 points.
        // A different physical face deliberately proves descriptor precedence.
        let metrics =
            RichFontMetrics::from_face(&face, None).with_pdf_vertical_metrics(1.159, -0.411);
        let defaults =
            RichFontMetrics::from_face(&face, Some(1.57)).with_pdf_vertical_metrics(2., -0.5);
        let metrics = metrics.with_default_bounds(defaults);
        assert_eq!(metrics.single_line_bounds, Some((1.159, -0.411)));
        assert_eq!(metrics.bbox_height, 1.57);
        let baseline = |metrics| {
            let bytes = content(
                &face,
                285.817,
                10.48,
                &field(),
                &json!({"textSize":6.25}),
                "2 beams",
                metrics,
            )
            .unwrap();
            let decoded = lopdf::content::Content::decode(&bytes).unwrap();
            decoded
                .operations
                .iter()
                .find(|op| op.operator == "Tm")
                .unwrap()
                .operands[5]
                .as_float()
                .unwrap()
        };
        assert!((baseline(Some(metrics)) - 2.903).abs() < 0.001);
        assert!((baseline(None) - baseline(Some(metrics))).abs() > 0.05);
        assert!(RichFontMetrics::from_face(&face, None)
            .with_pdf_vertical_metrics(f32::NAN, -0.411)
            .single_line_bounds
            .is_none());
        assert!(RichFontMetrics::from_face(&face, None)
            .with_pdf_vertical_metrics(-1., 1.)
            .single_line_bounds
            .is_none());
    }

    #[test]
    fn decorations_keep_run_colors_and_paint_outside_text_objects() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let state = json!({"textSize":7,"richRenderActive":true,"richValue":[
            {"text":"plain "},
            {"text":"under ","underline":true,"textColor":["RGB",1,0,0]},
            {"text":"strike ","strikethrough":true,"textColor":["RGB",0,1,0]},
            {"text":"both","underline":true,"strikethrough":true,"textColor":["RGB",0,0,1]},
            {"text":" end"}]});
        let output = content(
            &face,
            400.,
            50.,
            &field(),
            &state,
            "plain under strike both end",
            None,
        )
        .unwrap();
        let parsed = lopdf::content::Content::decode(&output).unwrap();
        let mut in_text = false;
        let mut baseline = None;
        let mut starts = Vec::new();
        let mut colors = Vec::new();
        let mut strokes = 0;
        for operation in parsed.operations {
            match operation.operator.as_str() {
                "BT" => in_text = true,
                "ET" => in_text = false,
                "Tm" => {
                    baseline.get_or_insert(operation.operands[5].as_float().unwrap());
                }
                "RG" => colors.push(
                    operation
                        .operands
                        .iter()
                        .map(|value| value.as_float().unwrap())
                        .collect::<Vec<_>>(),
                ),
                "w" | "m" | "l" | "S" => {
                    assert!(!in_text, "Path painting inside a text object");
                    match operation.operator.as_str() {
                        "w" => assert!(operation.operands[0].as_float().unwrap() > 0.),
                        "m" => starts.push((
                            operation.operands[0].as_float().unwrap(),
                            operation.operands[1].as_float().unwrap(),
                        )),
                        "S" => strokes += 1,
                        _ => {}
                    }
                }
                _ => {}
            }
        }
        assert_eq!(strokes, 4);
        assert_eq!(
            colors,
            vec![
                vec![1., 0., 0.],
                vec![0., 1., 0.],
                vec![0., 0., 1.],
                vec![0., 0., 1.]
            ]
        );
        let baseline = baseline.unwrap();
        assert!(starts[0].0 > 0. && starts[0].1 < baseline);
        assert!(starts[1].0 > starts[0].0 && starts[1].1 > baseline);
        assert_eq!(starts[2].0, starts[3].0);
        assert!(starts[2].1 < baseline && starts[3].1 > baseline);
    }
    #[test]
    fn first_rich_line_accounts_for_mixed_sizes_and_short_leading() {
        let metrics = RichFontMetrics {
            bbox_height: 1.57,
            single_line_bounds: None,
            ascent: 0.728,
            line_gap: 0.131,
        };
        // Independent Reader baseline offsets: uniform fractional and inline
        // size7/8 or9/7 runs, with short, explicit normal and default leading.
        for (first, largest, spacing, expected) in [
            (7.9, 7.9, Some(7.2), 11.3681),
            (8.1, 8.1, Some(7.2), 11.6559),
            (7.2, 7.2, Some(7.2), 11.304),
            (7., 8., Some(7.2), 10.801),
            (7., 8., Some(11.), 11.849),
            (7., 8., None, 11.849),
            (9., 9., Some(7.2), 12.951),
            (9., 9., None, 14.13),
        ] {
            assert!((first_rich_offset(first, largest, spacing, metrics) - expected).abs() < 0.002);
        }
    }
    #[test]
    fn mixed_faces_use_distinct_resources_and_face_specific_advances() {
        let regular = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let bold = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf").unwrap();
        let normal = ttf_parser::Face::parse(&regular, 0).unwrap();
        let heavy = ttf_parser::Face::parse(&bold, 0).unwrap();
        let layout = FontLayout {
            metrics: RichFontMetrics::from_face(&normal, None),
            fonts: vec![
                RenderFont {
                    face: normal,
                    resource: "Normal".into(),
                },
                RenderFont {
                    face: heavy,
                    resource: "Bold".into(),
                },
            ],
            span_fonts: vec![0, 1],
        };
        let normal_glyph = Glyph {
            c: 'W',
            size: 7.,
            color: [0.; 3],
            spacing: None,
            alignment: Some(0),
            font: 0,
            decoration: 0,
        };
        let bold_glyph = Glyph {
            font: 1,
            ..normal_glyph.clone()
        };
        assert!(layout.width(&bold_glyph) > layout.width(&normal_glyph));
        let state = json!({"richRenderActive":true,"richValue":[{"text":"normal ","textSize":7},{"text":"bold","textSize":7}]});
        let output = String::from_utf8(
            content_with_fonts(&layout, 400., 50., &field(), &state, "normal bold").unwrap(),
        )
        .unwrap();
        assert!(output.contains("/Normal 7 Tf"));
        assert!(output.contains("/Bold 7 Tf"));
    }
    #[test]
    fn reader_font_metrics_truncate_fixed_point_before_design_units() {
        assert_eq!(normalized_metric(1491., 2048.), 0.728);
        assert_eq!(normalized_metric(868., 1000.), 0.867);
        assert_eq!(normalized_metric(720., 1000.), 0.719);
        assert_eq!(normalized_metric(73., 1000.), 0.072);
        assert_eq!(normalized_metric(201., 2048.), 0.098);
    }
    #[test]
    fn mixed_size_rich_lines_use_typographic_ascent_with_explicit_or_normal_leading() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let metrics = RichFontMetrics {
            bbox_height: 1.57,
            single_line_bounds: None,
            ascent: 0.728,
            line_gap: 0.131,
        };
        for (spacing, expected_advance) in [(Some(11), 10.456), (None, 9.635)] {
            let mut first = json!({"text":"A\r","textSize":7});
            let mut next = json!({"text":"B","textSize":9});
            if let Some(spacing) = spacing {
                first["linespacing"] = json!(spacing);
                next["linespacing"] = json!(spacing);
            }
            let state = json!({"richRenderActive":true,"richValue":[first,next]});
            let output = String::from_utf8(
                content(&face, 100., 50., &field(), &state, "A\rB", Some(metrics)).unwrap(),
            )
            .unwrap();
            let tokens = output.split_whitespace().collect::<Vec<_>>();
            let positions = tokens
                .iter()
                .enumerate()
                .filter(|(_, v)| **v == "Tm")
                .map(|(i, _)| tokens[i - 1].parse::<f32>().unwrap())
                .collect::<Vec<_>>();
            assert_eq!(positions.len(), 2);
            assert!(
                (positions[0] - positions[1] - expected_advance).abs() < 0.002,
                "{output}"
            );
        }
    }
    #[test]
    fn rich_first_baseline_uses_source_pdf_font_bounds_independently_of_line_spacing() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        for spacing in [11, 14] {
            let state = json!({"textSize":7,"richRenderActive":true,"richValue":[{"text":"A","textSize":7,"linespacing":spacing}]});
            let output = String::from_utf8(
                content(
                    &face,
                    100.,
                    50.,
                    &field(),
                    &state,
                    "A",
                    Some(RichFontMetrics::from_face(&face, Some(1.57))),
                )
                .unwrap(),
            )
            .unwrap();
            assert!(output.contains("1 0 0 1 0 39.01 Tm"), "{output}");
        }
    }
    #[test]
    fn existing_rich_paragraph_alignment_survives_changed_field_default() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let state = json!({"textSize":9,"alignment":"right","richRenderActive":true,"richValue":[{"text":"style probe","textSize":7,"alignment":"left"}]});
        let output = String::from_utf8(
            content(&face, 100., 50., &field(), &state, "style probe", None).unwrap(),
        )
        .unwrap();
        assert!(
            output.contains(" rg 1 0 0 1 0 "),
            "Existing rich text must stay at its left paragraph position: {output}"
        );
    }
    #[test]
    fn matching_default_face_keeps_custom_font_resource_selection() {
        let state = json!({"textFont":"Custom-BoldLF", "defaultStyle":{"fontFamily":["Custom"],"fontWeight":400,"fontStyle":"normal"}, "richRenderActive":true,"richValue":[{"text":"title","fontFamily":["Custom"],"fontWeight":400,"fontStyle":"normal"}]});
        assert!(rich_font_candidates(&state).is_empty());
    }
    #[test]
    fn existing_uniform_rich_face_survives_changed_default_font() {
        let state = json!({"textFont":"Helvetica", "richRenderActive":true,"richValue":[{"text":"style probe","fontFamily":["Segoe UI","sans-serif"],"fontWeight":400,"fontStyle":"normal"}]});
        assert_eq!(rich_font_candidates(&state), vec!["SegoeUI"]);
    }
    #[test]
    fn mixed_rich_faces_do_not_claim_a_single_face_mapping() {
        let state = json!({"richRenderActive":true,"richValue":[{"text":"one","fontFamily":["Segoe UI"],"fontWeight":400},{"text":"two","fontFamily":["Segoe UI"],"fontWeight":700}]});
        assert!(rich_font_candidates(&state).is_empty());
    }
    #[test]
    fn numeric_format_result_is_displayed_without_overwriting_formula() {
        let field = field();
        let state = json!({"formatted":12});
        assert_eq!(display_text(&field, &state, "10+Dex"), "12");
        assert_eq!(field.value, json!("10+Dex"));
    }
    #[test]
    fn explicit_rich_indent_survives_start_and_paragraph_break() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let glyphs = "  A\n  B"
            .chars()
            .map(|c| Glyph {
                c,
                size: 7.,
                color: [0.; 3],
                spacing: Some(11.),
                alignment: Some(0),
                font: 0,
                decoration: 0,
            })
            .collect();
        let layout = lines(&|glyph| width(&face, glyph), glyphs, 100., true);
        assert_eq!(layout.len(), 2);
        assert_eq!(layout[0].iter().map(|g| g.c).collect::<String>(), "  A\n");
        assert_eq!(layout[1].iter().map(|g| g.c).collect::<String>(), "  B");
    }
    #[test]
    fn explicit_empty_rich_display_does_not_fall_back_to_canonical_text() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let output = content(
            &face,
            100.,
            50.,
            &field(),
            &json!({"richRenderActive":true,"richValue":[],"textSize":7}),
            "canonical text",
            None,
        )
        .unwrap();
        assert!(!String::from_utf8(output).unwrap().contains("Tj"));
    }
    #[test]
    fn rich_paragraph_flags_and_explicit_spacing_control_baselines() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let output = content(&face,100.,50.,&field(),&json!({"richRenderActive":true,"richValue":[{"text":"A","textSize":7,"linespacing":11,"endParagraph":true},{"text":"B","textSize":7,"linespacing":11}],"textSize":7}),"AB",None).unwrap();
        let decoded = lopdf::content::Content::decode(&output).unwrap();
        let baselines: Vec<f32> = decoded
            .operations
            .iter()
            .filter(|op| op.operator == "Tm")
            .map(|op| op.operands[5].as_float().unwrap())
            .collect();
        assert_eq!(baselines.len(), 2);
        assert!((baselines[0] - baselines[1] - 11.).abs() < 0.001);
    }
    #[test]
    fn blank_rich_lines_preserve_the_newline_font_size() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        let glyphs = [('A', 7.), ('\n', 7.), ('\n', 6.), ('B', 7.)]
            .into_iter()
            .map(|(c, size)| Glyph {
                c,
                size,
                color: [0.; 3],
                spacing: None,
                alignment: None,
                font: 0,
                decoration: 0,
            })
            .collect();
        let layout = lines(&|glyph| width(&face, glyph), glyphs, 100., true);
        assert_eq!(layout.len(), 3);
        assert_eq!(layout[1][0].c, '\n');
        assert_eq!(layout[1][0].size, 6.);
        assert_eq!(width(&face, &layout[1][0]), 0.);
    }
}
