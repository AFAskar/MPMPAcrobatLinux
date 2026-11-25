mod attachments;
mod icon_import;
mod pdf;
mod platform;
mod printing;
mod render;
mod runtime;
#[allow(dead_code)]
mod storage;
mod ui;
fn main() -> anyhow::Result<()> {
    ui::main()
}
