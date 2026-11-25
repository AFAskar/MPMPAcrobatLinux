mod attachments;
mod icon_import;
mod pdf;
mod platform;
mod printing;
mod render;
mod runtime;
mod ui;
fn main() -> anyhow::Result<()> {
    ui::main()
}
