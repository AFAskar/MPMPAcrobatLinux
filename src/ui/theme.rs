use eframe::egui::{self, Color32, CornerRadius, Margin, Shadow, Stroke, TextStyle};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ThemeMode {
    Dark,
    Light,
}

impl ThemeMode {
    pub fn from_env() -> Self {
        match std::env::var("MPMB_THEME")
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase()
            .as_str()
        {
            "light" => Self::Light,
            _ => Self::Dark,
        }
    }

    pub fn as_env(self) -> &'static str {
        match self {
            Self::Dark => "dark",
            Self::Light => "light",
        }
    }

    pub fn toggled(self) -> Self {
        match self {
            Self::Dark => Self::Light,
            Self::Light => Self::Dark,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Palette {
    pub canvas_bg: Color32,
    pub panel_bg: Color32,
    pub toolbar_bg: Color32,
    pub card_bg: Color32,
    pub card_stroke: Color32,
    pub accent: Color32,
    pub accent_text: Color32,
    pub accent_soft: Color32,
    pub text_primary: Color32,
    pub text_secondary: Color32,
    pub text_muted: Color32,
    pub ok: Color32,
    pub ok_bg: Color32,
    pub warn: Color32,
    pub warn_bg: Color32,
    pub err: Color32,
    pub err_bg: Color32,
    pub ro_badge_bg: Color32,
    pub widget_hover_fill: Color32,
    pub widget_hover_stroke: Color32,
    pub widget_selected_fill: Color32,
    pub widget_selected_stroke: Color32,
    pub page_shadow: Shadow,
}

impl Palette {
    pub fn for_mode(mode: ThemeMode) -> Self {
        match mode {
            ThemeMode::Dark => Self {
                canvas_bg: Color32::from_rgb(20, 23, 29),
                panel_bg: Color32::from_rgb(27, 31, 39),
                toolbar_bg: Color32::from_rgb(31, 36, 46),
                card_bg: Color32::from_rgb(36, 42, 54),
                card_stroke: Color32::from_rgb(56, 65, 82),
                accent: Color32::from_rgb(218, 160, 62),
                accent_text: Color32::from_rgb(20, 22, 26),
                accent_soft: Color32::from_rgba_unmultiplied(218, 160, 62, 34),
                text_primary: Color32::from_rgb(236, 240, 246),
                text_secondary: Color32::from_rgb(176, 185, 200),
                text_muted: Color32::from_rgb(122, 132, 148),
                ok: Color32::from_rgb(74, 210, 142),
                ok_bg: Color32::from_rgba_unmultiplied(74, 210, 142, 28),
                warn: Color32::from_rgb(240, 178, 72),
                warn_bg: Color32::from_rgba_unmultiplied(240, 178, 72, 30),
                err: Color32::from_rgb(238, 102, 102),
                err_bg: Color32::from_rgba_unmultiplied(238, 102, 102, 32),
                ro_badge_bg: Color32::from_rgb(52, 58, 72),
                widget_hover_fill: Color32::from_rgba_unmultiplied(218, 160, 62, 32),
                widget_hover_stroke: Color32::from_rgba_unmultiplied(218, 160, 62, 200),
                widget_selected_fill: Color32::from_rgba_unmultiplied(92, 168, 255, 28),
                widget_selected_stroke: Color32::from_rgba_unmultiplied(92, 168, 255, 210),
                page_shadow: Shadow {
                    offset: [0, 6],
                    blur: 22,
                    spread: 0,
                    color: Color32::from_black_alpha(120),
                },
            },
            ThemeMode::Light => Self {
                canvas_bg: Color32::from_rgb(225, 229, 236),
                panel_bg: Color32::from_rgb(247, 248, 250),
                toolbar_bg: Color32::from_rgb(252, 252, 254),
                card_bg: Color32::from_rgb(255, 255, 255),
                card_stroke: Color32::from_rgb(212, 218, 228),
                accent: Color32::from_rgb(176, 104, 18),
                accent_text: Color32::from_rgb(255, 255, 255),
                accent_soft: Color32::from_rgba_unmultiplied(176, 104, 18, 24),
                text_primary: Color32::from_rgb(24, 30, 42),
                text_secondary: Color32::from_rgb(76, 86, 104),
                text_muted: Color32::from_rgb(122, 132, 150),
                ok: Color32::from_rgb(22, 134, 78),
                ok_bg: Color32::from_rgba_unmultiplied(22, 134, 78, 24),
                warn: Color32::from_rgb(176, 104, 18),
                warn_bg: Color32::from_rgba_unmultiplied(176, 104, 18, 24),
                err: Color32::from_rgb(192, 42, 42),
                err_bg: Color32::from_rgba_unmultiplied(192, 42, 42, 24),
                ro_badge_bg: Color32::from_rgb(232, 236, 242),
                widget_hover_fill: Color32::from_rgba_unmultiplied(176, 104, 18, 28),
                widget_hover_stroke: Color32::from_rgba_unmultiplied(176, 104, 18, 210),
                widget_selected_fill: Color32::from_rgba_unmultiplied(38, 114, 216, 22),
                widget_selected_stroke: Color32::from_rgba_unmultiplied(38, 114, 216, 220),
                page_shadow: Shadow {
                    offset: [0, 4],
                    blur: 16,
                    spread: 0,
                    color: Color32::from_black_alpha(45),
                },
            },
        }
    }
}

pub fn apply(ctx: &egui::Context, mode: ThemeMode) -> Palette {
    let p = Palette::for_mode(mode);
    let mut visuals = match mode {
        ThemeMode::Dark => egui::Visuals::dark(),
        ThemeMode::Light => egui::Visuals::light(),
    };
    visuals.panel_fill = p.panel_bg;
    visuals.window_fill = p.panel_bg;
    visuals.extreme_bg_color = match mode {
        ThemeMode::Dark => Color32::from_rgb(20, 24, 31),
        ThemeMode::Light => Color32::from_rgb(255, 255, 255),
    };
    visuals.faint_bg_color = p.card_bg;
    visuals.window_corner_radius = CornerRadius::same(10);
    visuals.menu_corner_radius = CornerRadius::same(8);
    visuals.window_stroke = Stroke::new(1.0, p.card_stroke);
    visuals.selection.bg_fill = p.accent_soft;
    visuals.selection.stroke = Stroke::new(1.2, p.accent);
    visuals.hyperlink_color = p.accent;
    visuals.override_text_color = Some(p.text_primary);

    visuals.widgets.noninteractive.bg_fill = p.panel_bg;
    visuals.widgets.noninteractive.weak_bg_fill = p.card_bg;
    visuals.widgets.noninteractive.bg_stroke = Stroke::new(1.0, p.card_stroke);
    visuals.widgets.noninteractive.corner_radius = CornerRadius::same(6);
    visuals.widgets.noninteractive.fg_stroke = Stroke::new(1.0, p.text_primary);

    visuals.widgets.inactive.bg_fill = p.card_bg;
    visuals.widgets.inactive.weak_bg_fill = p.card_bg;
    visuals.widgets.inactive.bg_stroke = Stroke::new(1.0, p.card_stroke);
    visuals.widgets.inactive.corner_radius = CornerRadius::same(6);
    visuals.widgets.inactive.fg_stroke = Stroke::new(1.0, p.text_primary);

    visuals.widgets.hovered.bg_fill = match mode {
        ThemeMode::Dark => Color32::from_rgb(48, 56, 72),
        ThemeMode::Light => Color32::from_rgb(236, 240, 246),
    };
    visuals.widgets.hovered.weak_bg_fill = visuals.widgets.hovered.bg_fill;
    visuals.widgets.hovered.bg_stroke = Stroke::new(1.0, p.accent);
    visuals.widgets.hovered.corner_radius = CornerRadius::same(6);
    visuals.widgets.hovered.fg_stroke = Stroke::new(1.0, p.text_primary);

    visuals.widgets.active.bg_fill = p.accent_soft;
    visuals.widgets.active.weak_bg_fill = p.accent_soft;
    visuals.widgets.active.bg_stroke = Stroke::new(1.2, p.accent);
    visuals.widgets.active.corner_radius = CornerRadius::same(6);
    visuals.widgets.active.fg_stroke = Stroke::new(1.0, p.text_primary);

    let mut style = (*ctx.style()).clone();
    style.visuals = visuals;
    style.spacing.item_spacing = egui::vec2(8.0, 6.0);
    style.spacing.button_padding = egui::vec2(10.0, 5.0);
    style.spacing.window_margin = Margin::same(14);
    style.spacing.indent = 16.0;
    style.text_styles.insert(
        TextStyle::Heading,
        egui::FontId::new(16.5, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        TextStyle::Body,
        egui::FontId::new(13.5, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        TextStyle::Button,
        egui::FontId::new(13.0, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        TextStyle::Small,
        egui::FontId::new(11.5, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        TextStyle::Monospace,
        egui::FontId::new(12.5, egui::FontFamily::Monospace),
    );
    ctx.set_style(style);
    p
}

pub fn card_frame(p: &Palette) -> egui::Frame {
    egui::Frame::new()
        .fill(p.card_bg)
        .stroke(Stroke::new(1.0, p.card_stroke))
        .corner_radius(CornerRadius::same(8))
        .inner_margin(Margin::same(10))
}

pub fn badge(ui: &mut egui::Ui, text: &str, fg: Color32, bg: Color32) {
    egui::Frame::new()
        .fill(bg)
        .corner_radius(CornerRadius::same(5))
        .inner_margin(Margin::symmetric(7, 2))
        .show(ui, |ui| {
            ui.label(egui::RichText::new(text).small().strong().color(fg));
        });
}

pub fn status_dot(ui: &mut egui::Ui, color: Color32) {
    let (rect, _) = ui.allocate_exact_size(egui::vec2(8.0, 8.0), egui::Sense::hover());
    ui.painter().circle_filled(rect.center(), 3.5, color);
}

pub fn status_pill(ui: &mut egui::Ui, text: &str, fg: Color32, bg: Color32) {
    egui::Frame::new()
        .fill(bg)
        .corner_radius(CornerRadius::same(5))
        .inner_margin(Margin::symmetric(7, 2))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing.x = 5.0;
                status_dot(ui, fg);
                ui.label(egui::RichText::new(text).small().strong().color(fg));
            });
        });
}

pub fn accent_button(ui: &mut egui::Ui, p: &Palette, label: &str) -> egui::Response {
    ui.add(
        egui::Button::new(egui::RichText::new(label).strong().color(p.accent_text))
            .fill(p.accent)
            .stroke(Stroke::new(1.0, p.accent))
            .corner_radius(CornerRadius::same(6)),
    )
}
