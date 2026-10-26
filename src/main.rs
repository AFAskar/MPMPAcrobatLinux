mod pdf;
mod render;
fn main() -> anyhow::Result<()> {
    let path=std::env::args().nth(1).ok_or_else(||anyhow::anyhow!("usage: mpmb-reader <sheet.pdf>"))?;
    let pdf=pdf::Pdf::open(std::path::Path::new(&path))?;
    println!("{} pages, {} fields, {} embedded scripts, {} named templates",pdf.doc.get_pages().len(),pdf.fields.len(),pdf.scripts.len(),pdf.templates.len());
    Ok(())
}
