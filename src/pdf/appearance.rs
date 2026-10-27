//! Plain and rich text layout for generated widget appearances.
use super::*;
#[derive(Clone)]
struct Glyph {
    c: char,
    size: f32,
    color: [f32; 3],
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
    face: &ttf_parser::Face<'_>,
    glyphs: Vec<Glyph>,
    max_width: f32,
    wrap: bool,
) -> Vec<Vec<Glyph>> {
    let mut result = Vec::new();
    let mut line: Vec<Glyph> = Vec::new();
    let mut current = 0.;
    for glyph in glyphs {
        if glyph.c == '\n' {
            // A blank rich line still carries the newline span's font size.
            line.push(glyph);
            result.push(std::mem::take(&mut line));
            current = 0.;
            continue;
        }
        let added = width(face, &glyph);
        if wrap && current + added > max_width && !line.is_empty() {
            if let Some(space) = line.iter().rposition(|g| g.c == ' ') {
                let tail = line.split_off(space + 1);
                line.pop();
                result.push(std::mem::replace(&mut line, tail));
                current = line.iter().map(|g| width(face, g)).sum();
            } else {
                result.push(std::mem::take(&mut line));
                current = 0.;
            }
        }
        if glyph.c == ' ' && line.is_empty() {
            continue;
        }
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
) -> Result<Vec<u8>> {
    let wrap = state["multiline"]
        .as_bool()
        .unwrap_or(field.flags & 4096 != 0);
    let spans = state["richValue"].as_array().filter(|v| !v.is_empty());
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
                .flat_map(|span| {
                    let size = span["textSize"].as_f64().map(|v| v as f32).unwrap_or(size);
                    let color = if span.get("textColor").is_some() {
                        rgb(&span["textColor"])
                    } else {
                        color
                    };
                    span["text"]
                        .as_str()
                        .unwrap_or("")
                        .replace('\r', "\n")
                        .chars()
                        .map(move |c| Glyph { c, size, color })
                        .collect::<Vec<_>>()
                })
                .collect()
        } else {
            formatted
                .replace('\r', "\n")
                .chars()
                .map(|c| Glyph { c, size, color })
                .collect()
        }
    };
    let mut laid = lines(face, make(size), available, wrap);
    if explicit == 0. && spans.is_none() {
        loop {
            let too_tall = wrap && laid.len() as f32 * size * 1.12 > height - 2.;
            let too_wide = !wrap
                && laid
                    .iter()
                    .any(|line| line.iter().map(|g| width(face, g)).sum::<f32>() > available);
            if !(too_tall || too_wide) || size <= 3. {
                break;
            }
            size = (size - 0.25).max(3.);
            laid = lines(face, make(size), available, wrap);
        }
    }
    let mut out = format!("/Tx BMC q 0 0 {width_box} {height} re W n BT ");
    let line_sizes: Vec<f32> = laid
        .iter()
        .map(|line| line.iter().map(|g| g.size).reduce(f32::max).unwrap_or(size))
        .collect();
    let units = face.units_per_em() as f32;
    let ascent = face.ascender() as f32 / units;
    let descent = face.descender() as f32 / units;
    let mut y = if spans.is_some() {
        height - line_sizes.first().copied().unwrap_or(size) * (ascent - descent)
    } else if wrap {
        height - 1. - line_sizes.first().copied().unwrap_or(size)
    } else {
        (height - ascent * size + descent * size) / 2. - descent * size
    };
    for (line_index, line) in laid.into_iter().enumerate() {
        let line_size = line_sizes[line_index];
        let line: Vec<_> = line.into_iter().filter(|g| g.c != '\n').collect();
        let total = line.iter().map(|g| width(face, g)).sum::<f32>();
        let mut x = match state["alignment"].as_str().unwrap_or("left") {
            "center" => (width_box - total) / 2.,
            "right" => width_box - 1. - total,
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
                if face.glyph_index(g.c).is_none() && !g.c.is_control() {
                    bail!(
                        "appearance font lacks glyph U+{:04X} in {}",
                        g.c as u32,
                        field.name
                    )
                }
                encoded.push_str(&format!("{:04X}", g.c as u32));
            }
            out.push_str(&format!(
                "/Helv {} Tf {} {} {} rg 1 0 0 1 {x} {y} Tm <{encoded}> Tj ",
                first.size, first.color[0], first.color[1], first.color[2]
            ));
            x += run.iter().map(|g| width(face, g)).sum::<f32>();
            start = end;
        }
        y -= if spans.is_some() {
            let next = line_sizes.get(line_index + 1).copied().unwrap_or(line_size);
            line_size * (1. - ascent) + next * ascent
        } else {
            line_size * 1.12
        };
    }
    out.push_str("ET Q EMC");
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
            widgets: vec![],
            actions: BTreeMap::new(),
            items: vec![],
            export_values: vec![],
            caption: String::new(),
        }
    }
    #[test]
    fn numeric_format_result_is_displayed_without_overwriting_formula() {
        let field = field();
        let state = json!({"formatted":12});
        assert_eq!(display_text(&field, &state, "10+Dex"), "12");
        assert_eq!(field.value, json!("10+Dex"));
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
            })
            .collect();
        let layout = lines(&face, glyphs, 100., true);
        assert_eq!(layout.len(), 3);
        assert_eq!(layout[1][0].c, '\n');
        assert_eq!(layout[1][0].size, 6.);
        assert_eq!(width(&face, &layout[1][0]), 0.);
    }
}
