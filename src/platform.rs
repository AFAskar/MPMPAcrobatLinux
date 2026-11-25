//! Cross-platform desktop integration helpers (file pickers, URL/file opening).
//! Linux/Unix preserves the exact `zenity` / `xdg-open` behavior tested by the
//! GTK/AT-SPI desktop suites, falling back to `kdialog` when `zenity` is absent;
//! Windows uses native WinForms dialogs via PowerShell STA with explicit UTF-8
//! output encoding and `cmd /C start`.
use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};

#[cfg(any(test, target_os = "windows"))]
fn ps_escape(text: &str) -> String {
    text.replace('\'', "''")
}

#[cfg(any(test, target_os = "windows"))]
fn windows_filter_string(label: &str, patterns: &[&str], include_all_files: bool) -> String {
    let joined = patterns.join(";");
    let base = format!("{label} ({joined})|{joined}");
    if include_all_files {
        format!("{base}|All files (*.*)|*.*")
    } else {
        base
    }
}

#[cfg(any(test, target_os = "windows"))]
fn windows_open_script(
    title: &str,
    filter_label: &str,
    patterns: &[&str],
    start_dir: Option<&Path>,
    include_all_files: bool,
) -> String {
    let filter = windows_filter_string(filter_label, patterns, include_all_files);
    let init_dir = start_dir
        .map(|d| {
            format!(
                "$d.InitialDirectory = '{}';",
                ps_escape(&d.to_string_lossy())
            )
        })
        .unwrap_or_default();
    format!(
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; \
         Add-Type -AssemblyName System.Windows.Forms; \
         $d = New-Object System.Windows.Forms.OpenFileDialog; \
         $d.Title = '{}'; \
         $d.Filter = '{}'; \
         {} \
         if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ \
             [Console]::Out.Write($d.FileName) \
         }}",
        ps_escape(title),
        ps_escape(&filter),
        init_dir
    )
}

#[cfg(any(test, target_os = "windows"))]
fn windows_save_script(
    title: &str,
    filter_label: Option<(&str, &[&str])>,
    initial_path: Option<&str>,
) -> String {
    let filter_stmt = filter_label
        .map(|(label, patterns)| {
            let f = windows_filter_string(label, patterns, true);
            format!("$d.Filter = '{}';", ps_escape(&f))
        })
        .unwrap_or_default();
    let file_stmt = initial_path
        .map(|p| format!("$d.FileName = '{}';", ps_escape(p)))
        .unwrap_or_default();
    format!(
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; \
         Add-Type -AssemblyName System.Windows.Forms; \
         $d = New-Object System.Windows.Forms.SaveFileDialog; \
         $d.Title = '{}'; \
         {} {} \
         if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ \
             [Console]::Out.Write($d.FileName) \
         }}",
        ps_escape(title),
        filter_stmt,
        file_stmt
    )
}

pub fn open_file_dialog(
    title: &str,
    filter_label: &str,
    patterns: &[&str],
    start_dir: Option<&Path>,
    include_all_files: bool,
) -> Result<Option<PathBuf>> {
    #[cfg(not(target_os = "windows"))]
    {
        let mut cmd = std::process::Command::new("zenity");
        cmd.arg("--file-selection")
            .arg(format!("--title={title}"))
            .arg(format!(
                "--file-filter={filter_label} | {}",
                patterns.join(" ")
            ));
        if include_all_files {
            cmd.arg("--file-filter=All files | *");
        }
        if let Some(dir) = start_dir {
            cmd.arg(format!("--filename={}/", dir.display()));
        }
        let output = match cmd.output() {
            Ok(out) => out,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                // Fall back to kdialog on KDE/Plasma systems without zenity.
                let mut kd = std::process::Command::new("kdialog");
                kd.arg("--getopenfilename")
                    .arg(
                        start_dir
                            .map(|d| d.to_string_lossy().into_owned())
                            .unwrap_or_else(|| ".".to_owned()),
                    )
                    .arg(format!("{filter_label} ({})", patterns.join(" ")))
                    .arg("--title")
                    .arg(title);
                kd.output()
                    .context("open native file picker (install zenity or kdialog)")?
            }
            Err(err) => return Err(err).context("open native file picker"),
        };
        if output.status.code() == Some(1) {
            return Ok(None);
        }
        if !output.status.success() {
            bail!(
                "Native file picker failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let text = String::from_utf8(output.stdout)?
            .trim_end_matches(['\r', '\n'])
            .to_owned();
        if text.is_empty() {
            Ok(None)
        } else {
            Ok(Some(PathBuf::from(text)))
        }
    }
    #[cfg(target_os = "windows")]
    {
        let script =
            windows_open_script(title, filter_label, patterns, start_dir, include_all_files);
        let output = std::process::Command::new("powershell")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-WindowStyle",
                "Hidden",
                "-Command",
                &script,
            ])
            .output()
            .context("open Windows file picker")?;
        if !output.status.success() {
            bail!(
                "Windows file picker failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let text = String::from_utf8(output.stdout)?
            .trim_end_matches(['\r', '\n'])
            .to_owned();
        if text.is_empty() {
            Ok(None)
        } else {
            Ok(Some(PathBuf::from(text)))
        }
    }
}

pub fn save_file_dialog(
    title: &str,
    filter_label: Option<(&str, &[&str])>,
    initial_path: Option<&str>,
) -> Result<Option<PathBuf>> {
    #[cfg(not(target_os = "windows"))]
    {
        let mut cmd = std::process::Command::new("zenity");
        cmd.args(["--file-selection", "--save"])
            .arg(format!("--title={title}"));
        if let Some((label, patterns)) = filter_label {
            cmd.arg(format!("--file-filter={label} | {}", patterns.join(" ")));
        }
        if let Some(path) = initial_path {
            cmd.arg(format!("--filename={path}"));
        }
        let output = match cmd.output() {
            Ok(out) => out,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                let mut kd = std::process::Command::new("kdialog");
                kd.arg("--getsavefilename")
                    .arg(initial_path.unwrap_or("mpmb-character.pdf"));
                if let Some((label, patterns)) = filter_label {
                    kd.arg(format!("{label} ({})", patterns.join(" ")));
                }
                kd.arg("--title").arg(title);
                kd.output()
                    .context("open native save dialog (install zenity or kdialog)")?
            }
            Err(err) => return Err(err).context("open native save dialog"),
        };
        if output.status.code() == Some(1) {
            return Ok(None);
        }
        if !output.status.success() {
            bail!(
                "Native save dialog failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let text = String::from_utf8(output.stdout)?
            .trim_end_matches(['\r', '\n'])
            .to_owned();
        if text.is_empty() {
            Ok(None)
        } else {
            Ok(Some(PathBuf::from(text)))
        }
    }
    #[cfg(target_os = "windows")]
    {
        let script = windows_save_script(title, filter_label, initial_path);
        let output = std::process::Command::new("powershell")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-WindowStyle",
                "Hidden",
                "-Command",
                &script,
            ])
            .output()
            .context("open Windows save dialog")?;
        if !output.status.success() {
            bail!(
                "Windows save dialog failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let text = String::from_utf8(output.stdout)?
            .trim_end_matches(['\r', '\n'])
            .to_owned();
        if text.is_empty() {
            Ok(None)
        } else {
            Ok(Some(PathBuf::from(text)))
        }
    }
}

pub fn open_url_detached(url: &str) -> Result<()> {
    #[cfg(not(target_os = "windows"))]
    {
        std::process::Command::new("xdg-open")
            .arg(url)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .context("launch URL with xdg-open")?;
        Ok(())
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", url])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .context("launch URL with Windows shell")?;
        Ok(())
    }
}

pub fn open_file_blocking(path: &Path) -> Result<bool> {
    #[cfg(not(target_os = "windows"))]
    {
        Ok(std::process::Command::new("xdg-open")
            .arg(path)
            .status()?
            .success())
    }
    #[cfg(target_os = "windows")]
    {
        Ok(std::process::Command::new("cmd")
            .args(["/C", "start", ""])
            .arg(path)
            .status()?
            .success())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_filter_and_utf8_powershell_scripts_escape_quotes_and_unicode() {
        assert_eq!(
            windows_filter_string("XFDF", &["*.xfdf", "*.xml"], false),
            "XFDF (*.xfdf;*.xml)|*.xfdf;*.xml"
        );
        assert_eq!(
            windows_filter_string("PDF", &["*.pdf"], true),
            "PDF (*.pdf)|*.pdf|All files (*.*)|*.*"
        );
        let open = windows_open_script(
            "Open MPMB's Sheet",
            "PDF",
            &["*.pdf"],
            Some(Path::new("C:\\Users\\Élodie's Sheets")),
            false,
        );
        assert!(open.starts_with("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;"));
        assert!(open.contains("Open MPMB''s Sheet"));
        assert!(open.contains("Élodie''s Sheets"));

        let save = windows_save_script(
            "Save Copy",
            Some(("PDF", &["*.pdf"])),
            Some("C:\\Users\\Ω\\sheet's.pdf"),
        );
        assert!(save.starts_with("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;"));
        assert!(save.contains("sheet''s.pdf"));
    }
}
