mod attachments;
mod icon_import;
mod pdf;
mod platform;
mod printing;
mod render;
mod runtime;
mod serve;
mod storage;
mod ui;
fn main() -> anyhow::Result<()> {
    if std::env::args().nth(1).as_deref() == Some("serve") {
        return serve::main(std::env::args().skip(2).collect());
    }
    ui::main()
}
