//! Printing snapshots live state synchronously. Interactive saves stay in pdf.rs.
use crate::{pdf::Pdf, render::Renderer};
use anyhow::{bail, Context, Result};
use lopdf::{dictionary, Document, Object};
use serde_json::{json, Value};
use std::{io::Write, path::Path, process::Command, time::SystemTime};

pub fn pages(params: &Value, count: usize) -> Result<Vec<i32>> {
    let mut pages = Vec::new();
    if let Some(ranges) = params.get("printRange") {
        for range in ranges
            .as_array()
            .context("printRange must contain page pairs")?
        {
            let pair = range
                .as_array()
                .filter(|a| a.len() == 2)
                .context("invalid printRange pair")?;
            let first = pair[0].as_u64().context("invalid first print page")? as usize;
            let last = pair[1].as_u64().context("invalid last print page")? as usize;
            if first > last || last >= count {
                bail!("printRange outside document")
            }
            pages.extend((first..=last).map(|n| n as i32));
        }
    } else {
        let first = params["firstPage"]
            .as_u64()
            .filter(|n| (*n as usize) < count)
            .unwrap_or(0) as usize;
        let last = params["lastPage"]
            .as_u64()
            .filter(|n| (*n as usize) < count && (*n as usize) >= first)
            .unwrap_or(count.saturating_sub(1) as u64) as usize;
        pages.extend((first..=last).map(|n| n as i32));
    }
    if pages.is_empty() || pages.len() > 10000 {
        bail!("print requires 1..10000 pages")
    }
    Ok(pages)
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .context("print requires a new destination; existing files are never overwritten")?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn choose(args: &[&str]) -> Result<Option<String>> {
    let result = Command::new("zenity")
        .args(args)
        .output()
        .context("open native print dialog")?;
    if result.status.code() == Some(1) {
        return Ok(None);
    }
    if !result.status.success() {
        bail!(
            "print dialog failed: {}",
            String::from_utf8_lossy(&result.stderr)
        )
    }
    Ok(Some(
        String::from_utf8(result.stdout)?
            .trim_end_matches('\n')
            .to_owned(),
    ))
}

pub fn execute(
    pdf: &Pdf,
    request: &str,
    interactive: bool,
    output_dir: Option<&Path>,
) -> Result<Value> {
    let request: Value = serde_json::from_str(request)?;
    let params = &request["params"];
    // Do not silently accept settings outside those used by the supplied PDFs.
    for key in params
        .as_object()
        .context("print parameters must be an object")?
        .keys()
    {
        if ![
            "constants",
            "interactive",
            "DuplexType",
            "firstPage",
            "lastPage",
            "printRange",
        ]
        .contains(&key.as_str())
        {
            bail!("unsupported print parameter {key}")
        }
    }
    let interaction = params
        .get("interactive")
        .map(|v| {
            v.as_i64()
                .context("print interaction level must be an integer")
        })
        .transpose()?
        .unwrap_or(0);
    if !(0..=2).contains(&interaction) {
        bail!("invalid print interaction level")
    }
    if interactive && output_dir.is_none() && interaction != 0 {
        bail!("noninteractive desktop printing is unsupported")
    }
    let duplex = match params
        .get("DuplexType")
        .map(|v| v.as_i64().context("print duplex type must be an integer"))
        .transpose()?
        .unwrap_or(1)
    {
        1 => "one-sided",
        2 => "two-sided-long-edge",
        3 => "two-sided-short-edge",
        value => bail!("unsupported duplex type {value}"),
    };
    let projected = pdf.project(&request["state"])?;
    let count = Document::load_mem(&projected)?.get_pages().len();
    let selected = pages(params, count)?;
    let token = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)?
        .as_nanos();
    let mut printer = None;
    let destination = if let Some(dir) = output_dir {
        std::fs::create_dir_all(dir)?;
        dir.join(format!("print-{token}.pdf"))
    } else {
        if !interactive {
            bail!("printing requires an explicit probe print_output_dir or native print dialog")
        }
        let mut destinations = vec![
            "--list".to_string(),
            "--title=Print MPMB sheet".into(),
            format!(
                "--text={} selected page(s), {duplex}. Choose a destination.",
                selected.len()
            ),
            "--column=Destination".into(),
            "Save print PDF".into(),
        ];
        let printers = Command::new("lpstat")
            .arg("-a")
            .output()
            .context("list CUPS printers")?;
        if printers.status.success() {
            for line in String::from_utf8(printers.stdout)?.lines() {
                if let Some(name) = line.split_whitespace().next() {
                    destinations.push(name.to_owned())
                }
            }
        }
        let refs = destinations.iter().map(String::as_str).collect::<Vec<_>>();
        let Some(choice) = choose(&refs)? else {
            return Ok(json!({"status":"cancelled"}));
        };
        if choice == "Save print PDF" {
            let Some(path) = choose(&[
                "--file-selection",
                "--save",
                "--title=Save flattened print PDF (new file)",
                "--filename=mpmb-print.pdf",
            ])?
            else {
                return Ok(json!({"status":"cancelled"}));
            };
            std::path::PathBuf::from(path)
        } else {
            if !destinations.iter().skip(5).any(|p| p == &choice) {
                bail!("unknown print destination")
            }
            let text = format!("Send {} page(s) to {choice} with {duplex}?", selected.len());
            if choose(&[
                "--question",
                "--title=Submit print job",
                &format!("--text={text}"),
            ])?
            .is_none()
            {
                return Ok(json!({"status":"cancelled"}));
            }
            printer = Some(choice);
            std::env::temp_dir().join(format!("mpmb-print-{}-{token}.pdf", std::process::id()))
        }
    };
    let flattened = Renderer::new()?.print_copy(&projected, &selected)?;
    let mut doc = Document::load_mem(&flattened)?;
    // Print copies retain only the page tree, with all document scripts/actions
    // and unreachable template objects removed. They are intentionally static.
    let root = doc.trailer.get(b"Root")?.as_reference()?;
    let tree = doc.get_dictionary(root)?.get(b"Pages")?.clone();
    doc.objects.insert(root, Object::Dictionary(dictionary! {"Type"=>"Catalog", "Pages"=>tree,
        "ViewerPreferences"=>dictionary!{"Duplex"=>match duplex {"two-sided-long-edge"=>"DuplexFlipLongEdge", "two-sided-short-edge"=>"DuplexFlipShortEdge", _=>"Simplex"}}}));
    for id in doc.get_pages().values() {
        let page = doc.get_dictionary_mut(*id)?;
        page.remove(b"Annots");
        page.remove(b"AA");
    }
    doc.prune_objects();
    let mut bytes = Vec::new();
    doc.save_to(&mut bytes)?;
    write_new(&destination, &bytes)?;
    if let Some(printer) = printer {
        let result = Command::new("lp")
            .arg("-d")
            .arg(&printer)
            .arg("-o")
            .arg(format!("sides={duplex}"))
            .arg(&destination)
            .output();
        let _ = std::fs::remove_file(&destination);
        let result = result.context("submit CUPS job")?;
        if !result.status.success() {
            bail!(
                "printer submission failed: {}",
                String::from_utf8_lossy(&result.stderr)
            )
        }
        return Ok(
            json!({"status":"submitted", "printer":printer, "pages":selected, "duplex":duplex, "receipt":String::from_utf8_lossy(&result.stdout)}),
        );
    }
    Ok(json!({"status":"saved", "path":destination, "pages":selected, "duplex":duplex}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ranges_preserve_order_and_repetitions_and_reject_invalid_pages() {
        assert_eq!(
            pages(&json!({"printRange":[[2,3],[0,0],[2,2]]}), 4).unwrap(),
            vec![2, 3, 0, 2]
        );
        for params in [
            json!({"printRange":[]}),
            json!({"printRange":[[0,4]]}),
            json!({"printRange":[[2,1]]}),
            json!({"printRange":[[-1,0]]}),
            json!({"printRange":[[0.5,1]]}),
        ] {
            assert!(pages(&params, 4).is_err());
        }
        assert_eq!(
            pages(&json!({"firstPage":99,"lastPage":-1}), 4).unwrap(),
            vec![0, 1, 2, 3]
        );
    }
}
