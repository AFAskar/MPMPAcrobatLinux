use anyhow::Result;
use eframe::egui;
use serde_json::Value;
use std::collections::BTreeSet;

use crate::{pdf::Pdf, runtime::Runtime};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SidebarTab {
    Fields,
    Bookmarks,
    Diagnostics,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FieldFilter {
    All,
    CurrentPage,
    Writable,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FieldCatalogEntry {
    pub name: String,
    pub kind: String,
    pub readonly: bool,
}

impl FieldCatalogEntry {
    pub fn short_type(&self) -> &'static str {
        match self.kind.as_str() {
            "text" => "Tx",
            "combobox" => "Cb",
            "listbox" => "Lb",
            "checkbox" => "Ck",
            "radiobutton" => "Rd",
            "button" => "Bn",
            _ => "Fd",
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AbilityStat {
    pub label: &'static str,
    pub score: String,
    pub modifier: String,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CharacterSummary {
    pub name: String,
    pub class_and_levels: String,
    pub level: String,
    pub proficiency: String,
    pub ac: String,
    pub hp_current: String,
    pub hp_max: String,
    pub abilities: Vec<AbilityStat>,
}

impl CharacterSummary {
    pub fn fetch(rt: &Runtime) -> Self {
        let query = r#"(function(){
            function v(n){var f=getField(n);return f?String(f.valueAsString||''):'';}
            return {
                name:v('PC Name'),
                classAndLevels:v('Class and Levels'),
                level:v('Character Level'),
                prof:v('Proficiency Bonus'),
                ac:v('AC'),
                hpCur:v('HP Current'),
                hpMax:v('HP Max'),
                abilities:[
                    ['STR',v('Str'),v('Str Mod')],
                    ['DEX',v('Dex'),v('Dex Mod')],
                    ['CON',v('Con'),v('Con Mod')],
                    ['INT',v('Int'),v('Int Mod')],
                    ['WIS',v('Wis'),v('Wis Mod')],
                    ['CHA',v('Cha'),v('Cha Mod')]
                ]
            };
        })()"#;
        let Ok(val) = rt.eval(query) else {
            return Self::default();
        };
        let s = |k: &str| val[k].as_str().unwrap_or("").trim().to_owned();
        let labels = ["STR", "DEX", "CON", "INT", "WIS", "CHA"];
        let mut abilities = Vec::with_capacity(6);
        if let Some(arr) = val["abilities"].as_array() {
            for (idx, row) in arr.iter().enumerate() {
                if let Some(label) = labels.get(idx) {
                    abilities.push(AbilityStat {
                        label,
                        score: row[1].as_str().unwrap_or("").trim().to_owned(),
                        modifier: row[2].as_str().unwrap_or("").trim().to_owned(),
                    });
                }
            }
        }
        Self {
            name: s("name"),
            class_and_levels: s("classAndLevels"),
            level: s("level"),
            proficiency: s("prof"),
            ac: s("ac"),
            hp_current: s("hpCur"),
            hp_max: s("hpMax"),
            abilities,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ZoomMode {
    FitWidth,
    Manual(f32),
}

#[derive(Clone, Copy, Debug)]
pub struct ZoomState {
    pub mode: ZoomMode,
    pub last_effective: f32,
}

impl Default for ZoomState {
    fn default() -> Self {
        Self {
            mode: ZoomMode::FitWidth,
            last_effective: 1.0,
        }
    }
}

impl ZoomState {
    const MIN_ZOOM: f32 = 0.5;
    const MAX_ZOOM: f32 = 2.5;
    const BASE_PAGE_WIDTH: f32 = 820.0;

    pub fn effective_scale(&mut self, available_width: f32) -> f32 {
        let scale = match self.mode {
            ZoomMode::FitWidth => {
                let target = (available_width - 48.0).max(320.0);
                (target / Self::BASE_PAGE_WIDTH).clamp(Self::MIN_ZOOM, Self::MAX_ZOOM)
            }
            ZoomMode::Manual(z) => z.clamp(Self::MIN_ZOOM, Self::MAX_ZOOM),
        };
        self.last_effective = scale;
        scale
    }

    pub fn display_width(&mut self, available_width: f32) -> f32 {
        match self.mode {
            ZoomMode::FitWidth => {
                self.effective_scale(available_width);
                (available_width - 48.0).clamp(320.0, Self::BASE_PAGE_WIDTH * Self::MAX_ZOOM)
            }
            ZoomMode::Manual(z) => {
                let clamped = z.clamp(Self::MIN_ZOOM, Self::MAX_ZOOM);
                self.last_effective = clamped;
                Self::BASE_PAGE_WIDTH * clamped
            }
        }
    }

    pub fn render_pixel_width(&mut self, available_width: f32, pixels_per_point: f32) -> usize {
        let raw = self.display_width(available_width) * pixels_per_point.clamp(1.0, 2.5);
        // Quantize to 64px steps so smooth window dragging doesn't re-render every pixel.
        let quantized = ((raw / 64.0).round() * 64.0).clamp(640.0, 2304.0);
        quantized as usize
    }

    pub fn zoom_in(&mut self) {
        let next = ((self.last_effective * 10.0).round() / 10.0 + 0.15).min(Self::MAX_ZOOM);
        self.mode = ZoomMode::Manual(next);
        self.last_effective = next;
    }

    pub fn zoom_out(&mut self) {
        let next = ((self.last_effective * 10.0).round() / 10.0 - 0.15).max(Self::MIN_ZOOM);
        self.mode = ZoomMode::Manual(next);
        self.last_effective = next;
    }

    pub fn set_fit_width(&mut self) {
        self.mode = ZoomMode::FitWidth;
    }

    pub fn percent_label(&self) -> String {
        let pct = (self.last_effective * 100.0).round() as i32;
        match self.mode {
            ZoomMode::FitWidth => format!("Fit ({pct}%)"),
            ZoomMode::Manual(_) => format!("{pct}%"),
        }
    }
}

#[derive(Default)]
pub struct ProjectionCache {
    projected: Option<(u64, Vec<u8>)>,
    page_widgets: Option<(i32, u64, Vec<Value>)>,
    metadata_revision: Option<u64>,
    pub page_count: i32,
    pub field_catalog: Vec<FieldCatalogEntry>,
    pub summary: CharacterSummary,
    pub bookmarks: Value,
    pub diagnostics: Value,
    pub projection_builds: usize,
}

impl ProjectionCache {
    pub fn ensure_metadata(&mut self, rt: &Runtime, pdf: &Pdf, revision: u64) {
        if self.metadata_revision == Some(revision) {
            return;
        }
        self.metadata_revision = Some(revision);
        self.page_count = rt
            .eval("numPages")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(pdf.doc.get_pages().len() as u64)
            .max(1) as i32;
        self.field_catalog = rt
            .eval(
                "__host.names.map(function(n){var f=__host.fields[n];return [n,f?f.type:'text',!!(f&&f.readonly)];})",
            )
            .ok()
            .and_then(|v| v.as_array().cloned())
            .map(|items| {
                items
                    .into_iter()
                    .filter_map(|row| {
                        let arr = row.as_array()?;
                        Some(FieldCatalogEntry {
                            name: arr.first()?.as_str()?.to_owned(),
                            kind: arr.get(1)?.as_str().unwrap_or("text").to_owned(),
                            readonly: arr.get(2).and_then(Value::as_bool).unwrap_or(false),
                        })
                    })
                    .collect()
            })
            .unwrap_or_else(|| {
                pdf.fields
                    .values()
                    .map(|f| FieldCatalogEntry {
                        name: f.name.clone(),
                        kind: f.kind.clone(),
                        readonly: f.flags & 1 != 0,
                    })
                    .collect()
            });
        self.summary = CharacterSummary::fetch(rt);
        self.bookmarks = rt
            .eval("JSON.parse(JSON.stringify(bookmarkRoot))")
            .unwrap_or(Value::Null);
        self.diagnostics = rt.diagnostics().unwrap_or(Value::Null);
    }

    pub fn invalidate_all(&mut self) {
        self.projected = None;
        self.metadata_revision = None;
        self.page_widgets = None;
    }

    pub fn projected_bytes(&mut self, rt: &Runtime, pdf: &Pdf, revision: u64) -> Result<&[u8]> {
        let needs_build = self
            .projected
            .as_ref()
            .is_none_or(|(cached_rev, _)| *cached_rev != revision);
        if needs_build {
            let snap = rt.snapshot()?;
            let bytes = pdf.project(&snap)?;
            self.projected = Some((revision, bytes));
            self.projection_builds += 1;
        }
        Ok(&self.projected.as_ref().unwrap().1)
    }

    pub fn widgets_for_page(&mut self, rt: &Runtime, page: i32, revision: u64) -> &[Value] {
        let needs_fetch = self
            .page_widgets
            .as_ref()
            .is_none_or(|(p, r, _)| *p != page || *r != revision);
        if needs_fetch {
            let widgets = rt
                .eval(&format!("__host.pageWidgets({page})"))
                .ok()
                .and_then(|v| v.as_array().cloned())
                .unwrap_or_default();
            self.page_widgets = Some((page, revision, widgets));
        }
        &self.page_widgets.as_ref().unwrap().2
    }
}

pub fn filter_fields<'a>(
    catalog: &'a [FieldCatalogEntry],
    query: &str,
    mode: FieldFilter,
    page_widget_names: &BTreeSet<String>,
) -> Vec<&'a FieldCatalogEntry> {
    let needle = query.trim().to_ascii_lowercase();
    catalog
        .iter()
        .filter(|entry| {
            if !needle.is_empty() && !entry.name.to_ascii_lowercase().contains(&needle) {
                return false;
            }
            match mode {
                FieldFilter::All => true,
                FieldFilter::CurrentPage => page_widget_names.contains(&entry.name),
                FieldFilter::Writable => !entry.readonly && entry.kind != "button",
            }
        })
        .collect()
}

pub fn pdf_rect_to_screen(
    pdf_rect: &[Value],
    page_size: (f32, f32),
    image_rect: egui::Rect,
) -> Option<egui::Rect> {
    let (pw, ph) = page_size;
    if pdf_rect.len() != 4 || pw <= 0.0 || ph <= 0.0 {
        return None;
    }
    let x0 = pdf_rect[0].as_f64()? as f32;
    let y0 = pdf_rect[1].as_f64()? as f32;
    let x1 = pdf_rect[2].as_f64()? as f32;
    let y1 = pdf_rect[3].as_f64()? as f32;
    let left = image_rect.left() + (x0.min(x1) / pw) * image_rect.width();
    let right = image_rect.left() + (x0.max(x1) / pw) * image_rect.width();
    let top = image_rect.top() + ((ph - y0.max(y1)) / ph) * image_rect.height();
    let bottom = image_rect.top() + ((ph - y0.min(y1)) / ph) * image_rect.height();
    Some(egui::Rect::from_min_max(
        egui::pos2(left, top),
        egui::pos2(right, bottom),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::Arc;

    #[test]
    fn zoom_state_clamps_and_quantizes_render_widths() {
        let mut zoom = ZoomState::default();
        assert_eq!(zoom.mode, ZoomMode::FitWidth);
        let w = zoom.render_pixel_width(900.0, 1.0);
        assert_eq!(w % 64, 0);
        assert!((640..=2304).contains(&w));
        zoom.zoom_in();
        assert!(matches!(zoom.mode, ZoomMode::Manual(v) if v > 1.0));
        for _ in 0..20 {
            zoom.zoom_in();
        }
        assert!(matches!(zoom.mode, ZoomMode::Manual(v) if (v - 2.5).abs() < 1e-4));
        for _ in 0..30 {
            zoom.zoom_out();
        }
        assert!(matches!(zoom.mode, ZoomMode::Manual(v) if (v - 0.5).abs() < 1e-4));
        zoom.set_fit_width();
        assert_eq!(zoom.mode, ZoomMode::FitWidth);
    }

    #[test]
    fn field_filter_respects_query_page_and_writable_modes() {
        let catalog = vec![
            FieldCatalogEntry {
                name: "PC Name".into(),
                kind: "text".into(),
                readonly: false,
            },
            FieldCatalogEntry {
                name: "Str Mod".into(),
                kind: "text".into(),
                readonly: true,
            },
            FieldCatalogEntry {
                name: "ResetButton".into(),
                kind: "button".into(),
                readonly: false,
            },
            FieldCatalogEntry {
                name: "Notes.Left".into(),
                kind: "text".into(),
                readonly: false,
            },
        ];
        let on_page = BTreeSet::from(["PC Name".into(), "Str Mod".into()]);
        assert_eq!(
            filter_fields(&catalog, "", FieldFilter::All, &on_page).len(),
            4
        );
        assert_eq!(
            filter_fields(&catalog, "", FieldFilter::CurrentPage, &on_page)
                .iter()
                .map(|e| e.name.as_str())
                .collect::<Vec<_>>(),
            vec!["PC Name", "Str Mod"]
        );
        assert_eq!(
            filter_fields(&catalog, "", FieldFilter::Writable, &on_page)
                .iter()
                .map(|e| e.name.as_str())
                .collect::<Vec<_>>(),
            vec!["PC Name", "Notes.Left"]
        );
        assert_eq!(
            filter_fields(&catalog, "mod", FieldFilter::All, &on_page)
                .iter()
                .map(|e| e.name.as_str())
                .collect::<Vec<_>>(),
            vec!["Str Mod"]
        );
    }

    #[test]
    fn pdf_rect_maps_bottom_left_origin_to_screen_top_left() {
        let image = egui::Rect::from_min_size(egui::pos2(100.0, 50.0), egui::vec2(612.0, 792.0));
        let mapped = pdf_rect_to_screen(
            &[json!(10.0), json!(700.0), json!(110.0), json!(720.0)],
            (612.0, 792.0),
            image,
        )
        .unwrap();
        assert!((mapped.left() - 110.0).abs() < 1e-3);
        assert!((mapped.right() - 210.0).abs() < 1e-3);
        assert!((mapped.top() - (50.0 + 72.0)).abs() < 1e-3);
        assert!((mapped.bottom() - (50.0 + 92.0)).abs() < 1e-3);
    }

    #[test]
    fn projection_cache_reuses_bytes_until_revision_changes() {
        let mut doc = lopdf::Document::new();
        let page = doc.add_object(lopdf::dictionary! {"Type"=>"Page","MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()]});
        let pages = doc
            .add_object(lopdf::dictionary! {"Type"=>"Pages","Kids"=>vec![page.into()],"Count"=>1});
        doc.get_dictionary_mut(page).unwrap().set("Parent", pages);
        let field = doc.add_object(lopdf::dictionary! {
            "FT"=>"Tx","T"=>lopdf::Object::string_literal("PC Name"),"V"=>lopdf::Object::string_literal("Aria"),
            "Subtype"=>"Widget","Rect"=>vec![10.into(),700.into(),150.into(),720.into()],"P"=>page,"F"=>4
        });
        doc.get_dictionary_mut(page)
            .unwrap()
            .set("Annots", vec![field.into()]);
        let form = doc.add_object(lopdf::dictionary! {"Fields"=>vec![field.into()]});
        let root =
            doc.add_object(lopdf::dictionary! {"Type"=>"Catalog","Pages"=>pages,"AcroForm"=>form});
        doc.trailer.set("Root", root);

        let dir = std::env::temp_dir().join(format!("mpmb-proj-cache-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("sheet.pdf");
        doc.save(&path).unwrap();

        let pdf = Arc::new(Pdf::open(&path).unwrap());
        let rt = Runtime::new(&pdf, vec![], vec![], false, None, None).unwrap();
        let mut cache = ProjectionCache::default();
        let rev0 = rt.eval("__host.revision").unwrap().as_u64().unwrap();
        let first_len = cache.projected_bytes(&rt, &pdf, rev0).unwrap().len();
        let second_len = cache.projected_bytes(&rt, &pdf, rev0).unwrap().len();
        assert_eq!(first_len, second_len);
        assert_eq!(cache.projection_builds, 1);

        rt.edit("PC Name", &json!("Lyra")).unwrap();
        let rev1 = rt.eval("__host.revision").unwrap().as_u64().unwrap();
        assert_ne!(rev0, rev1);
        let _ = cache.projected_bytes(&rt, &pdf, rev1).unwrap();
        assert_eq!(cache.projection_builds, 2);

        cache.ensure_metadata(&rt, &pdf, rev1);
        assert_eq!(cache.summary.name, "Lyra");
        assert_eq!(cache.page_count, 1);

        // Explicit invalidation forces a fresh projection even at the same revision.
        cache.invalidate_all();
        let _ = cache.projected_bytes(&rt, &pdf, rev1).unwrap();
        assert_eq!(cache.projection_builds, 3);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
