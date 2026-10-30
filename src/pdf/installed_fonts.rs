//! Exact installed TrueType faces for rich spans missing from the source PDF.
//! Fontconfig may return a substitute for any query, so inspect the actual face
//! identity before allowing its bytes into a requested-font resource.
use super::{appearance::RichFontMetrics, EmbeddedFont};
use std::{
    collections::{BTreeMap, BTreeSet},
    process::Command,
};

#[derive(Default)]
pub(super) struct Resolver {
    attempted: BTreeSet<String>,
}
impl Resolver {
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn installed_substitutes_cannot_masquerade_as_requested_faces() {
        let bytes = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf").unwrap();
        let face = ttf_parser::Face::parse(&bytes, 0).unwrap();
        assert_eq!(
            matching_name(&face, "DejaVuSans").as_deref(),
            Some("DejaVuSans")
        );
        assert!(matching_name(&face, "SegoeUI-Italic").is_none());
        assert!(matching_name(&face, "DejaVuSans-Bold").is_none());
        let bold = std::fs::read("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf").unwrap();
        let bold = ttf_parser::Face::parse(&bold, 0).unwrap();
        assert_eq!(
            matching_name(&bold, "DejaVuSans,Bold").as_deref(),
            Some("DejaVuSans-Bold")
        );
    }
}
