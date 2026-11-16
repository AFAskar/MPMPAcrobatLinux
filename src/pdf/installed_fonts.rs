//! Exact installed TrueType faces for rich spans missing from the source PDF.
//! Fontconfig may return a substitute for any query, so inspect the actual face
//! identity before allowing its bytes into a requested-font resource.
use super::{appearance::RichFontMetrics, EmbeddedFont};
use anyhow::Context;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    process::Command,
};

/// Preserve explicit overrides, but find the same default face on other Linux
/// distributions. Fontconfig's successful exit alone does not identify a face.
pub(super) fn fallback_bytes() -> anyhow::Result<Vec<u8>> {
    if let Some(path) = std::env::var_os("MPMB_FONT") {
        return std::fs::read(path).context("read Unicode appearance font (MPMB_FONT)");
    }
    for path in [
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ] {
        if let Some(bytes) = default_font_at(Path::new(path)) {
            return Ok(bytes);
        }
    }
    if let Ok(output) = Command::new("fc-match")
        .args(["-f", "%{file}", "--", ":postscriptname=DejaVuSans"])
        .output()
    {
        if output.status.success() {
            if let Ok(path) = std::str::from_utf8(&output.stdout) {
                if let Some(bytes) = default_font_at(Path::new(path)) {
                    return Ok(bytes);
                }
            }
        }
    }
    anyhow::bail!("DejaVu Sans TrueType font unavailable; install it or set MPMB_FONT")
}

fn default_font_at(path: &Path) -> Option<Vec<u8>> {
    let bytes = std::fs::read(path).ok()?;
    let face = ttf_parser::Face::parse(&bytes, 0).ok()?;
    matching_name(&face, "DejaVuSans")?;
    Some(bytes)
}

#[derive(Default)]
pub(super) struct Resolver {
    attempted: BTreeSet<String>,
    attempted_families: BTreeSet<(String, u16, bool)>,
}
impl Resolver {
    pub fn resolve_family(
        &mut self,
        alias: &str,
        family: &str,
        weight: u16,
        italic: bool,
        fonts: &mut BTreeMap<String, EmbeddedFont>,
    ) {
        if fonts.contains_key(alias) {
            return;
        }
        // A saved document must remain usable without a system-font lookup.
        let embedded = fonts.values().find_map(|asset| {
            let face = ttf_parser::Face::parse(&asset.bytes, 0).ok()?;
            let font_name = matching_family(&face, family, weight, italic)?;
            Some(EmbeddedFont {
                bytes: asset.bytes.clone(),
                metrics: asset.metrics,
                font_name,
            })
        });
        if let Some(asset) = embedded {
            fonts.insert(alias.to_owned(), asset);
            return;
        }
        if !self
            .attempted_families
            .insert((family.to_owned(), weight, italic))
        {
            return;
        }
        let query = format!(
            "{family}:weight={}:slant={}",
            if weight == 700 { 200 } else { 80 },
            if italic { 100 } else { 0 }
        );
        let Ok(output) = Command::new("fc-match")
            .args(["-f", "%{file}", "--", &query])
            .output()
        else {
            return;
        };
        if !output.status.success() {
            return;
        }
        let Ok(path) = std::str::from_utf8(&output.stdout) else {
            return;
        };
        let Ok(bytes) = std::fs::read(path) else {
            return;
        };
        let Ok(face) = ttf_parser::Face::parse(&bytes, 0) else {
            return;
        };
        let Some(font_name) = matching_family(&face, family, weight, italic) else {
            return;
        };
        let metrics = RichFontMetrics::from_face(&face, None);
        fonts.insert(
            alias.to_owned(),
            EmbeddedFont {
                bytes,
                metrics,
                font_name,
            },
        );
    }

    pub fn resolve(&mut self, name: &str, fonts: &mut BTreeMap<String, EmbeddedFont>) {
        if fonts.contains_key(name) || !self.attempted.insert(name.to_owned()) {
            return;
        }
        let canonical = name.replace(',', "-");
        let Ok(output) = Command::new("fc-match")
            .args([
                "-f",
                "%{file}",
                "--",
                &format!(":postscriptname={canonical}"),
            ])
            .output()
        else {
            return;
        };
        if !output.status.success() {
            return;
        }
        let Ok(path) = std::str::from_utf8(&output.stdout) else {
            return;
        };
        let Ok(bytes) = std::fs::read(path) else {
            return;
        };
        let Ok(face) = ttf_parser::Face::parse(&bytes, 0) else {
            return;
        };
        let Some(font_name) = matching_name(&face, name) else {
            return;
        };
        let metrics = RichFontMetrics::from_face(&face, None);
        fonts.insert(
            name.to_owned(),
            EmbeddedFont {
                bytes,
                metrics,
                font_name,
            },
        );
    }
}

fn matching_family(
    face: &ttf_parser::Face<'_>,
    family: &str,
    weight: u16,
    italic: bool,
) -> Option<String> {
    face.tables().glyf?;
    let named = |id, expected: &str| {
        face.names().into_iter().any(|entry| {
            entry.name_id == id
                && entry
                    .to_string()
                    .is_some_and(|name| name.trim().eq_ignore_ascii_case(expected.trim()))
        })
    };
    let preferred = named(ttf_parser::name_id::TYPOGRAPHIC_FAMILY, family)
        && face.weight().to_number() == weight
        && face.width().to_number() == 5
        && face.is_italic() == italic;
    // Legacy families can include a weight/width in the family itself, such
    // as Arial Narrow or Calibri Light. Match their actual subfamily as well.
    let subfamilies: &[&str] = match (weight, italic) {
        (400, false) => &["Regular", "Normal", "Roman", "Book"],
        (400, true) => &["Italic", "Oblique"],
        (700, false) => &["Bold"],
        (700, true) => &["Bold Italic", "Bold Oblique", "BoldItalic", "BoldOblique"],
        _ => return None,
    };
    let legacy = named(ttf_parser::name_id::FAMILY, family)
        && subfamilies
            .iter()
            .any(|style| named(ttf_parser::name_id::SUBFAMILY, style));
    if !preferred && !legacy {
        return None;
    }
    face.names()
        .into_iter()
        .filter(|entry| entry.name_id == ttf_parser::name_id::POST_SCRIPT_NAME)
        .find_map(|entry| entry.to_string().filter(|name| !name.is_empty()))
}

fn matching_name(face: &ttf_parser::Face<'_>, requested: &str) -> Option<String> {
    // The existing writer embeds CIDFontType2. CFF and nonzero collection
    // members need separate support rather than invalid TrueType resources.
    face.tables().glyf?;
    face.names()
        .into_iter()
        .filter(|entry| entry.name_id == ttf_parser::name_id::POST_SCRIPT_NAME)
        .filter_map(|entry| entry.to_string())
        .find(|actual| actual == requested || *actual == requested.replace(',', "-"))
}

/// Tests require these exact faces, but their package directories vary by distro.
#[cfg(test)]
pub(super) fn test_font_path(face: &str) -> &'static Path {
    let paths = match face {
        "DejaVuSans" => [
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ],
        "DejaVuSans-Bold" => [
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ],
        _ => panic!("Unknown required test face {face}"),
    };
    paths
        .into_iter()
        .map(Path::new)
        .find(|path| {
            std::fs::read(path).ok().is_some_and(|bytes| {
                ttf_parser::Face::parse(&bytes, 0)
                    .ok()
                    .is_some_and(|font| matching_name(&font, face).as_deref() == Some(face))
            })
        })
        .unwrap_or_else(|| panic!("Install the exact {face} TrueType face to run font tests"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn family_lookup_checks_face_style_and_reuses_embedded_bytes_first() {
        let bytes =
            std::fs::read(crate::pdf::installed_fonts::test_font_path("DejaVuSans")).unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        assert_eq!(
            matching_family(&face, "DejaVu Sans", 400, false).as_deref(),
            Some("DejaVuSans")
        );
        assert!(matching_family(&face, "Missing Family", 400, false).is_none());
        assert!(matching_family(&face, "DejaVu Sans", 700, false).is_none());
        assert!(matching_family(&face, "DejaVu Sans", 400, true).is_none());
        let metrics = RichFontMetrics::from_face(&face, None);
        let mut fonts = BTreeMap::from([(
            "OriginalResource".into(),
            EmbeddedFont {
                bytes: bytes.clone(),
                metrics,
                font_name: "DejaVuSans".into(),
            },
        )]);
        let mut resolver = Resolver::default();
        // A previous failed system lookup must not suppress a new embedded face.
        resolver
            .attempted_families
            .insert(("DejaVu Sans".into(), 400, false));
        resolver.resolve_family("DejaVu Sans", "DejaVu Sans", 400, false, &mut fonts);
        assert_eq!(fonts["DejaVu Sans"].font_name, "DejaVuSans");
        assert_eq!(fonts["DejaVu Sans"].bytes, bytes);
    }
    #[test]
    fn installed_substitutes_cannot_masquerade_as_requested_faces() {
        let bytes =
            std::fs::read(crate::pdf::installed_fonts::test_font_path("DejaVuSans")).unwrap();
        assert_eq!(
            default_font_at(Path::new(crate::pdf::installed_fonts::test_font_path(
                "DejaVuSans"
            ))),
            Some(bytes.clone())
        );
        assert!(
            default_font_at(Path::new(crate::pdf::installed_fonts::test_font_path(
                "DejaVuSans-Bold"
            )))
            .is_none()
        );
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        assert_eq!(
            matching_name(&face, "DejaVuSans").as_deref(),
            Some("DejaVuSans")
        );
        assert!(matching_name(&face, "SegoeUI-Italic").is_none());
        assert!(matching_name(&face, "DejaVuSans-Bold").is_none());
        let bold = std::fs::read(crate::pdf::installed_fonts::test_font_path(
            "DejaVuSans-Bold",
        ))
        .unwrap();
        let bold = ttf_parser::Face::parse(&bold, 0).unwrap();
        assert_eq!(
            matching_name(&bold, "DejaVuSans,Bold").as_deref(),
            Some("DejaVuSans-Bold")
        );
    }
}
