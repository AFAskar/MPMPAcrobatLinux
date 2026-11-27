use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc, Mutex,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

static TEMP_SEQ: AtomicU64 = AtomicU64::new(1);
static CONFLICT_SEQ: AtomicU64 = AtomicU64::new(1);

pub const MAX_PDF_BYTES: usize = 64 * 1024 * 1024;
const MAX_SIDECAR_BYTES: usize = 4 * 1024 * 1024;
const DEFAULT_GIT_TIMEOUT_SECS: u64 = 60;
const STAGING_PREFIX: &str = ".mpmb-tmp-";
const STAGING_SUFFIX: &str = ".tmp";
const GIT_ENV_SCRUB_KEYS: &[&str] = &[
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
];

#[derive(Debug)]
pub struct TemplateNotFoundError {
    pub path: String,
}

impl std::fmt::Display for TemplateNotFoundError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "template not found: {}", self.path)
    }
}

impl std::error::Error for TemplateNotFoundError {}

#[derive(Clone, Debug)]
pub struct GitConfig {
    pub repo_url: String,
    pub branch: String,
    pub remote: String,
    pub ssh_key: Option<PathBuf>,
    pub ssh_known_hosts: Option<PathBuf>,
    pub https_token: Option<String>,
    pub author_name: String,
    pub author_email: String,
    pub conflict_prefix: String,
    pub timeout_secs: u64,
}

impl GitConfig {
    pub fn new(repo_url: impl Into<String>) -> Self {
        Self {
            repo_url: repo_url.into(),
            branch: "main".into(),
            remote: "origin".into(),
            ssh_key: None,
            ssh_known_hosts: None,
            https_token: None,
            author_name: "MPMB Reader".into(),
            author_email: "mpmb-reader@local".into(),
            conflict_prefix: "conflict".into(),
            timeout_secs: DEFAULT_GIT_TIMEOUT_SECS,
        }
    }
}

#[derive(Clone, Debug)]
pub struct StoreConfig {
    pub root: PathBuf,
    pub git: Option<GitConfig>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SheetEntry {
    pub path: String,
    pub name: String,
    pub size_bytes: u64,
    pub sha256: String,
    pub modified_unix: u64,
    #[serde(default)]
    pub is_template: bool,
    pub has_state_sidecar: bool,
    pub character_name: Option<String>,
    pub class_and_levels: Option<String>,
    pub level: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum SaveResult {
    Saved {
        sha256: String,
        size_bytes: u64,
        sidecar_written: bool,
    },
    PartialSidecarFailed {
        sha256: String,
        size_bytes: u64,
        sidecar_error: String,
    },
    Conflict {
        expected_sha256: String,
        current_sha256: String,
    },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct GitStatus {
    pub enabled: bool,
    pub repo_url: Option<String>,
    pub branch: Option<String>,
    pub head_sha: Option<String>,
    pub head_subject: Option<String>,
    pub dirty: bool,
    pub changed_files: Vec<String>,
    pub ahead: usize,
    pub behind: usize,
    #[serde(default)]
    pub head_backed_up: bool,
    pub last_conflict_branch: Option<String>,
    pub last_error: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
struct ConflictBackupMarker {
    sha: String,
    branch: String,
    destination_hash: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PullResult {
    pub updated: bool,
    pub dirty: bool,
    pub old_head: Option<String>,
    pub new_head: Option<String>,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncResult {
    pub status: String,
    pub committed: bool,
    pub pushed: bool,
    pub commit_sha: Option<String>,
    pub branch: String,
    pub conflict_branch: Option<String>,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CommitInfo {
    pub sha: String,
    pub short_sha: String,
    pub date: String,
    pub author: String,
    pub subject: String,
}

#[derive(Default)]
struct GitRuntimeMeta {
    last_conflict_branch: Option<String>,
    last_error: Option<String>,
}

pub struct SheetStore {
    root: PathBuf,
    git: Option<GitConfig>,
    lock: Mutex<GitRuntimeMeta>,
}

impl SheetStore {
    pub fn open(config: StoreConfig) -> Result<Self> {
        fs::create_dir_all(&config.root)
            .with_context(|| format!("failed to create sheet store {}", config.root.display()))?;
        let root = config.root.canonicalize().unwrap_or(config.root);
        let store = Self {
            root,
            git: config.git,
            lock: Mutex::new(GitRuntimeMeta::default()),
        };
        if store.git.is_some() {
            store.bootstrap_git()?;
        }
        Ok(store)
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn git_enabled(&self) -> bool {
        self.git.is_some()
    }

    pub fn git_branch(&self) -> Option<&str> {
        self.git.as_ref().map(|g| g.branch.as_str())
    }

    pub fn resolve_safe_pdf_path(&self, rel: &str) -> Result<(String, PathBuf)> {
        let raw = rel.replace('\\', "/");
        let parts = validate_safe_rel_pdf_path(&raw)?;
        let normalized = parts.join("/");
        let abs = self.ensure_within_store(&parts)?;
        Ok((normalized, abs))
    }

    fn ensure_within_store(&self, parts: &[String]) -> Result<PathBuf> {
        let mut cur = self.root.clone();
        for seg in parts {
            cur.push(seg);
            match fs::symlink_metadata(&cur) {
                Ok(meta) => {
                    if meta.file_type().is_symlink() {
                        bail!(
                            "symlinks are not permitted inside the sheet store: {}",
                            cur.display()
                        );
                    }
                    let canon = cur.canonicalize().with_context(|| {
                        format!("failed to canonicalize store path {}", cur.display())
                    })?;
                    if !canon.starts_with(&self.root) {
                        bail!("resolved sheet path escapes store root");
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(e.into()),
            }
        }
        Ok(cur)
    }

    pub fn sidecar_path_for(pdf_path: &Path) -> PathBuf {
        let fname = pdf_path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("sheet.pdf");
        pdf_path.with_file_name(format!("{fname}.state.json"))
    }

    fn legacy_sidecar_path_for(pdf_path: &Path) -> PathBuf {
        let stem = pdf_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("sheet");
        pdf_path.with_file_name(format!("{stem}.state.json"))
    }

    fn check_create_sidecar_conflicts(pdf_path: &Path) -> Result<()> {
        let primary = Self::sidecar_path_for(pdf_path);
        let legacy = Self::legacy_sidecar_path_for(pdf_path);
        for (sc, is_primary) in [(primary, true), (legacy, false)] {
            let Ok(meta) = fs::symlink_metadata(&sc) else {
                continue;
            };
            if !meta.is_file() || meta.file_type().is_symlink() {
                continue;
            }
            if !sidecar_claimed_by_other_pdf(pdf_path, &sc)? {
                continue;
            }
            let owner_matches = sidecar_explicit_owner_matches(&sc, pdf_path);
            if owner_matches == Some(true) {
                continue;
            }
            // Reject whenever creating `pdf_path` would either:
            // - claim another existing sheet's legacy sidecar as `pdf_path`'s primary sidecar
            //   (which would also collide on future saves), or
            // - turn a pre-existing unstamped sidecar owned by another sheet ambiguous and
            //   hide that sheet's metadata.
            if is_primary || owner_matches.is_none() {
                bail!(
                    "conflict: destination sidecar {} belongs to another existing sheet; choose a different character name",
                    sc.file_name()
                        .and_then(|s| s.to_str())
                        .unwrap_or("sidecar")
                );
            }
        }
        Ok(())
    }

    fn ensure_primary_sidecar_writable_for(pdf_path: &Path, sidecar_path: &Path) -> Result<()> {
        let Ok(meta) = fs::symlink_metadata(sidecar_path) else {
            return Ok(());
        };
        if meta.file_type().is_symlink() || !meta.is_file() {
            bail!(
                "sidecar destination is not a regular file: {}",
                sidecar_path.display()
            );
        }
        if sidecar_claimed_by_other_pdf(pdf_path, sidecar_path)?
            && sidecar_explicit_owner_matches(sidecar_path, pdf_path) != Some(true)
        {
            bail!(
                "conflict: sidecar destination {} is shared with another existing sheet and will not be overwritten",
                sidecar_path.display()
            );
        }
        Ok(())
    }

    fn invalidate_sidecars_for(pdf_path: &Path) -> Result<()> {
        for sc in [
            Self::sidecar_path_for(pdf_path),
            Self::legacy_sidecar_path_for(pdf_path),
        ] {
            let Ok(meta) = fs::symlink_metadata(&sc) else {
                continue;
            };
            if !meta.is_file() || meta.file_type().is_symlink() {
                continue;
            }
            // Never remove a sidecar that another existing PDF in the same directory
            // derives as its primary or legacy sidecar (e.g. `Hero.pdf` vs `Hero.pdf.pdf`,
            // or case-variant siblings like `Hero.PDF` vs `Hero.pdf`), unless the sidecar
            // explicitly declares `pdf_path` as its sole owner via `pdfFileName`.
            // Fail closed if directory ownership cannot be verified.
            if sidecar_claimed_by_other_pdf(pdf_path, &sc)?
                && sidecar_explicit_owner_matches(&sc, pdf_path) != Some(true)
            {
                continue;
            }
            match fs::remove_file(&sc) {
                Ok(()) => {}
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
                Err(err) => {
                    return Err(anyhow::Error::new(err).context(format!(
                        "failed to remove stale sidecar {}; delete or unlock it before retrying",
                        sc.display()
                    )));
                }
            }
        }
        Ok(())
    }

    pub fn list_sheets(&self) -> Result<Vec<SheetEntry>> {
        let _guard = self.lock.lock().unwrap();
        let mut out = Vec::new();
        collect_pdfs(&self.root, &self.root, &mut out)?;
        out.sort_by(|a, b| a.path.cmp(&b.path));
        Ok(out)
    }

    pub fn read_sheet_bytes(&self, rel: &str) -> Result<(String, PathBuf, Vec<u8>, String)> {
        let _guard = self.lock.lock().unwrap();
        let (normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        let meta = match fs::symlink_metadata(&abs) {
            Ok(m) => m,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                return Err(anyhow::Error::new(e).context(format!("sheet not found: {normalized}")));
            }
            Err(e) => {
                return Err(
                    anyhow::Error::new(e).context(format!("failed to stat sheet: {normalized}"))
                );
            }
        };
        if meta.file_type().is_symlink() || !meta.is_file() {
            bail!("sheet path must be a regular file: {normalized}");
        }
        if meta.len() as usize > MAX_PDF_BYTES {
            bail!("sheet exceeds 64 MiB limit");
        }
        let bytes = read_bounded(&abs, MAX_PDF_BYTES)
            .with_context(|| format!("failed reading {normalized}"))?;
        let sha = sha256_hex(&bytes);
        Ok((normalized, abs, bytes, sha))
    }

    pub fn start_staged_upload(&self, rel: &str) -> Result<(String, StagedUpload)> {
        let _guard = self.lock.lock().unwrap();
        let (normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        if let Some(parent) = abs.parent() {
            fs::create_dir_all(parent)?;
        }
        let staged = StagedUpload::create(&abs)?;
        Ok((normalized, staged))
    }

    pub fn commit_staged_upload(
        &self,
        rel: &str,
        mut staged: StagedUpload,
        overwrite: bool,
    ) -> Result<SheetEntry> {
        staged.finish()?;
        // Fully parse the staged PDF before acquiring the store lock or touching
        // any existing PDF/sidecar so truncated or corrupted uploads can never
        // overwrite a valid character sheet.
        staged.validate_pdf()?;
        let _guard = self.lock.lock().unwrap();
        let (normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        if let Some(parent) = abs.parent() {
            fs::create_dir_all(parent)?;
        }
        // Hold the cross-process store lock until after sheet_entry_from_path()
        // hashes the published file so the returned entry describes the exact bytes
        // published by this operation.
        let _commit_lock = acquire_store_lock(&self.root)?;
        if overwrite {
            if let Ok(meta) = fs::symlink_metadata(&abs) {
                if meta.file_type().is_symlink() || !meta.is_file() {
                    bail!("cannot overwrite non-regular file at {normalized}");
                }
            }
            staged
                .publish_replace(&abs)
                .with_context(|| format!("failed replacing {}", abs.display()))?;
            // Invalidate any previous sidecar metadata so stale character details are not advertised.
            let _ = Self::invalidate_sidecars_for(&abs);
            sync_parent_dir(&abs);
        } else {
            if fs::symlink_metadata(&abs).is_ok() {
                bail!("sheet already exists: {normalized} (pass overwrite=true to replace)");
            }
            // Reject destinations whose sidecar path would collide with another existing
            // sheet's sidecar (e.g. pre-PR unstamped sidecar or shared legacy sidecar),
            // and clear true orphaned destination sidecars BEFORE atomic publication so
            // any removal error aborts cleanly without creating `abs` or attaching stale metadata.
            Self::check_create_sidecar_conflicts(&abs)?;
            Self::invalidate_sidecars_for(&abs)?;
            if let Err(err) = staged.publish_create_new(&abs) {
                if err
                    .downcast_ref::<std::io::Error>()
                    .is_some_and(|io| io.kind() == std::io::ErrorKind::AlreadyExists)
                    || abs.exists()
                {
                    bail!("sheet already exists: {normalized} (pass overwrite=true to replace)");
                }
                return Err(err);
            }
            sync_parent_dir(&abs);
        }
        sheet_entry_from_path(&self.root, &abs)
    }

    pub fn prepare_template_copy(
        &self,
        template_rel: &str,
        character_name: &str,
    ) -> Result<(String, PathBuf, Vec<u8>, String)> {
        let dest_rel = normalize_new_character_path(character_name)?;
        let (dest_norm, dest_abs, src_norm) = {
            let _guard = self.lock.lock().unwrap();
            let (norm, abs) = self.resolve_safe_pdf_path(&dest_rel)?;
            // Fast-fail before running any template startup/JavaScript when a sheet
            // already exists or its sidecar path collides with another existing sheet.
            if fs::symlink_metadata(&abs).is_ok() {
                bail!("sheet already exists: {norm}");
            }
            Self::check_create_sidecar_conflicts(&abs)?;
            let (src_norm, _) = self.resolve_safe_pdf_path(template_rel)?;
            if !is_template_path(&src_norm) {
                bail!("source sheet must be a template inside templates/: {src_norm}");
            }
            (norm, abs, src_norm)
        };
        let (_, _, bytes, sha) = match self.read_sheet_bytes(&src_norm) {
            Ok(v) => v,
            Err(err)
                if err.chain().any(|cause| {
                    cause
                        .downcast_ref::<std::io::Error>()
                        .is_some_and(|io| io.kind() == std::io::ErrorKind::NotFound)
                }) =>
            {
                return Err(anyhow::Error::new(TemplateNotFoundError { path: src_norm }));
            }
            Err(err) => return Err(err),
        };
        if bytes.is_empty() || bytes.len() > MAX_PDF_BYTES {
            bail!("template PDF must be between 1 byte and 64 MiB");
        }
        if !bytes.starts_with(b"%PDF-") {
            bail!("template file does not start with %PDF- header");
        }
        Ok((dest_norm, dest_abs, bytes, sha))
    }

    pub fn publish_new_sheet_bytes(&self, rel: &str, bytes: &[u8]) -> Result<SheetEntry> {
        if bytes.is_empty() || bytes.len() > MAX_PDF_BYTES {
            bail!("PDF upload must be between 1 byte and 64 MiB");
        }
        if !bytes.starts_with(b"%PDF-") {
            bail!("PDF file does not start with %PDF- header");
        }
        let (dest_norm, mut staged) = self.start_staged_upload(rel)?;
        staged.write_chunk(bytes)?;
        // Unconditionally create-only (overwrite = false) so a racing writer's file
        // is never overwritten or deleted.
        self.commit_staged_upload(&dest_norm, staged, false)
    }

    pub fn create_sheet_from_template(
        &self,
        template_rel: &str,
        character_name: &str,
    ) -> Result<SheetEntry> {
        let (dest_norm, _, bytes, _) = self.prepare_template_copy(template_rel, character_name)?;
        self.publish_new_sheet_bytes(&dest_norm, &bytes)
    }

    #[cfg(test)]
    pub fn upload_sheet(&self, rel: &str, bytes: &[u8], overwrite: bool) -> Result<SheetEntry> {
        if bytes.is_empty() || bytes.len() > MAX_PDF_BYTES {
            bail!("PDF upload must be between 1 byte and 64 MiB");
        }
        if !bytes.starts_with(b"%PDF-") {
            bail!("uploaded file does not start with %PDF- header");
        }
        let (normalized, mut staged) = self.start_staged_upload(rel)?;
        staged.write_chunk(bytes)?;
        self.commit_staged_upload(&normalized, staged, overwrite)
    }

    pub fn write_sidecar_atomic(
        &self,
        rel: &str,
        expected_pdf_sha256: &str,
        state_sidecar: &Value,
    ) -> Result<()> {
        let _guard = self.lock.lock().unwrap();
        let (_normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        let sidecar_path = Self::sidecar_path_for(&abs);
        Self::ensure_primary_sidecar_writable_for(&abs, &sidecar_path)?;
        let stamped = stamp_sidecar_meta(state_sidecar, expected_pdf_sha256, &abs);
        let mut pretty = serde_json::to_vec_pretty(&stamped)?;
        pretty.push(b'\n');
        let staged_sidecar = StagedFile::create(&sidecar_path, &pretty)?;

        let _commit_lock = acquire_store_lock(&self.root)?;
        Self::ensure_primary_sidecar_writable_for(&abs, &sidecar_path)?;
        let meta = match fs::symlink_metadata(&abs) {
            Ok(m) => m,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                bail!("conflict: sheet was deleted before sidecar retry");
            }
            Err(e) => return Err(e.into()),
        };
        if meta.file_type().is_symlink() || !meta.is_file() {
            bail!("target sheet is not a regular file");
        }
        let current_bytes = read_bounded(&abs, MAX_PDF_BYTES)?;
        let current_sha = sha256_hex(&current_bytes);
        if current_sha != expected_pdf_sha256 {
            bail!("conflict: sheet changed externally on disk before sidecar retry");
        }
        staged_sidecar
            .publish(&sidecar_path)
            .with_context(|| format!("failed replacing {}", sidecar_path.display()))?;
        sync_parent_dir(&abs);
        Ok(())
    }

    pub fn save_sheet_atomic(
        &self,
        rel: &str,
        pdf_bytes: &[u8],
        expected_sha256: Option<&str>,
        state_sidecar: Option<&Value>,
        force: bool,
    ) -> Result<SaveResult> {
        let _guard = self.lock.lock().unwrap();
        if pdf_bytes.len() > MAX_PDF_BYTES {
            bail!("serialized PDF exceeds {} bytes", MAX_PDF_BYTES);
        }
        let (_normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        let new_sha = sha256_hex(pdf_bytes);

        let check_expected = || -> Result<Option<SaveResult>> {
            if let Some(expected) = expected_sha256 {
                if !force {
                    let meta = match fs::symlink_metadata(&abs) {
                        Ok(m) => m,
                        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                            return Ok(Some(SaveResult::Conflict {
                                expected_sha256: expected.to_owned(),
                                current_sha256: "<deleted>".to_owned(),
                            }));
                        }
                        Err(e) => return Err(e.into()),
                    };
                    if meta.file_type().is_symlink() || !meta.is_file() {
                        bail!("target sheet is not a regular file");
                    }
                    let current_bytes = read_bounded(&abs, MAX_PDF_BYTES)?;
                    let current_sha = sha256_hex(&current_bytes);
                    if current_sha != expected {
                        return Ok(Some(SaveResult::Conflict {
                            expected_sha256: expected.to_owned(),
                            current_sha256: current_sha,
                        }));
                    }
                }
            }
            Ok(None)
        };

        // Run initial expected-hash check BEFORE sidecar preflight so a deleted
        // or externally modified PDF reports Conflict instead of a sidecar error.
        if let Some(conflict) = check_expected()? {
            return Ok(conflict);
        }

        if let Some(parent) = abs.parent() {
            fs::create_dir_all(parent)?;
        }

        // Validate and pre-stage sidecar BEFORE modifying the PDF; RAII guards
        // ensure staged files are always removed on any early return or error.
        let staged_sidecar = if let Some(sidecar) = state_sidecar {
            let sidecar_path = Self::sidecar_path_for(&abs);
            Self::ensure_primary_sidecar_writable_for(&abs, &sidecar_path)?;
            let stamped = stamp_sidecar_meta(sidecar, &new_sha, &abs);
            let mut pretty = serde_json::to_vec_pretty(&stamped)?;
            pretty.push(b'\n');
            let tmp = StagedFile::create(&sidecar_path, &pretty)?;
            Some((tmp, sidecar_path))
        } else {
            None
        };

        let staged_pdf = StagedFile::create(&abs, pdf_bytes)?;

        // Hold an advisory lock file during commit for cross-process coordination
        // (multiple server/CLI instances writing to the same store). Fail closed
        // if the lock cannot be acquired.
        let _commit_lock = acquire_store_lock(&self.root)?;
        if let Some(conflict) = check_expected()? {
            return Ok(conflict);
        }
        if let Some((_, ref sidecar_path)) = staged_sidecar {
            Self::ensure_primary_sidecar_writable_for(&abs, sidecar_path)?;
        }

        staged_pdf
            .publish(&abs)
            .with_context(|| format!("failed replacing {}", abs.display()))?;

        let mut sidecar_written = false;
        if let Some((tmp, sidecar_path)) = staged_sidecar {
            if let Err(err) = tmp.publish(&sidecar_path) {
                sync_parent_dir(&abs);
                return Ok(SaveResult::PartialSidecarFailed {
                    sha256: new_sha,
                    size_bytes: pdf_bytes.len() as u64,
                    sidecar_error: format!("failed replacing {}: {err}", sidecar_path.display()),
                });
            }
            sidecar_written = true;
        }
        sync_parent_dir(&abs);
        Ok(SaveResult::Saved {
            sha256: new_sha,
            size_bytes: pdf_bytes.len() as u64,
            sidecar_written,
        })
    }

    pub fn git_status(&self) -> Result<GitStatus> {
        let guard = self.lock.lock().unwrap();
        let Some(cfg) = &self.git else {
            return Ok(GitStatus {
                enabled: false,
                repo_url: None,
                branch: None,
                head_sha: None,
                head_subject: None,
                dirty: false,
                changed_files: Vec::new(),
                ahead: 0,
                behind: 0,
                head_backed_up: false,
                last_conflict_branch: None,
                last_error: None,
            });
        };
        let head = self
            .run_git_allow_fail(cfg, &["rev-parse", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());
        let head_subject = if head.is_some() {
            self.run_git_allow_fail(cfg, &["log", "-1", "--format=%s"])
                .ok()
                .filter(|s| !s.is_empty())
        } else {
            None
        };
        let branch = self
            .run_git_allow_fail(cfg, &["rev-parse", "--abbrev-ref", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty() && s != "HEAD")
            .or_else(|| Some(cfg.branch.clone()));
        let porcelain = self
            .run_git(cfg, &["status", "--porcelain"])
            .context("failed checking Git working tree status")?;
        let changed_files: Vec<String> = porcelain
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| l.trim().to_owned())
            .collect();
        let (ahead, behind) = self.ahead_behind(cfg);
        let dest_hash = self.destination_hash(cfg);
        let backup_marker = self.read_conflict_backup(cfg);
        let head_backed_up = head.as_deref().is_some_and(|h| {
            backup_marker
                .as_ref()
                .is_some_and(|m| m.sha == h && m.destination_hash == dest_hash)
        });
        let last_conflict_branch = guard.last_conflict_branch.clone().or_else(|| {
            if head_backed_up {
                backup_marker.as_ref().map(|m| m.branch.clone())
            } else {
                None
            }
        });
        Ok(GitStatus {
            enabled: true,
            repo_url: Some(redact_url(&cfg.repo_url)),
            branch,
            head_sha: head,
            head_subject,
            dirty: !changed_files.is_empty(),
            changed_files,
            ahead,
            behind,
            head_backed_up,
            last_conflict_branch,
            last_error: guard.last_error.clone(),
        })
    }

    /// Returns Git status, degrading gracefully to a status object carrying
    /// `last_error` when `git status` itself fails (e.g. a corrupt `.git/index`),
    /// so post-commit HTTP responses remain infallible once a sheet is saved or created.
    pub fn git_status_best_effort(&self) -> GitStatus {
        match self.git_status() {
            Ok(status) => status,
            Err(err) => {
                let (enabled, repo_url, branch) = match &self.git {
                    Some(cfg) => (
                        true,
                        Some(redact_url(&cfg.repo_url)),
                        Some(cfg.branch.clone()),
                    ),
                    None => (false, None, None),
                };
                GitStatus {
                    enabled,
                    repo_url,
                    branch,
                    head_sha: None,
                    head_subject: None,
                    dirty: enabled,
                    changed_files: Vec::new(),
                    ahead: 0,
                    behind: 0,
                    head_backed_up: false,
                    last_conflict_branch: None,
                    last_error: Some(format!("git status unavailable: {err:#}")),
                }
            }
        }
    }

    pub fn git_pull(&self) -> Result<PullResult> {
        let mut guard = self.lock.lock().unwrap();
        let Some(cfg) = &self.git else {
            return Ok(PullResult {
                updated: false,
                dirty: false,
                old_head: None,
                new_head: None,
                message: "Git storage is not enabled".into(),
            });
        };
        let _pull_lock = acquire_store_lock(&self.root)?;
        if let Err(err) = self.validate_checkout_state(cfg) {
            guard.last_error = Some(format!("{err:#}"));
            return Err(err);
        }
        let old_head = self
            .run_git_allow_fail(cfg, &["rev-parse", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());
        let porcelain = match self.run_git(cfg, &["status", "--porcelain"]) {
            Ok(out) => out,
            Err(err) => {
                guard.last_error = Some(format!("{err:#}"));
                return Err(err).context("failed checking Git working tree status before pull");
            }
        };
        if !porcelain.trim().is_empty() {
            return Ok(PullResult {
                updated: false,
                dirty: true,
                old_head: old_head.clone(),
                new_head: old_head,
                message: "Working tree has uncommitted local changes; sync before pulling".into(),
            });
        }
        if let Err(err) = self.run_git(cfg, &["fetch", "--", &cfg.remote, &cfg.branch]) {
            let msg = format!("{err:#}");
            if msg.contains("couldn't find remote ref") {
                guard.last_error = None;
                return Ok(PullResult {
                    updated: false,
                    dirty: false,
                    old_head: old_head.clone(),
                    new_head: old_head,
                    message: format!("Remote branch {} does not exist yet", cfg.branch),
                });
            }
            guard.last_error = Some(msg);
            return Err(err);
        }
        // Revalidate checkout branch before mutating HEAD/working tree.
        if let Err(err) = self.validate_checkout_state(cfg) {
            guard.last_error = Some(format!("{err:#}"));
            return Err(err);
        }
        // Use the exact commit fetched into FETCH_HEAD rather than assuming the
        // remote refspec wrote to `<remote>/<branch>`.
        let fetched_ref = match self.run_git(cfg, &["rev-parse", "--verify", "FETCH_HEAD"]) {
            Ok(sha) if !sha.is_empty() => sha,
            Ok(_) => {
                let err = anyhow!("FETCH_HEAD was empty after fetching {}", cfg.branch);
                guard.last_error = Some(format!("{err:#}"));
                return Err(err);
            }
            Err(err) => {
                guard.last_error = Some(format!("{err:#}"));
                return Err(err);
            }
        };
        let pull_res = if old_head.is_none() {
            self.run_git(cfg, &["checkout", "-B", &cfg.branch, &fetched_ref])
        } else {
            self.run_git(
                cfg,
                &["merge", "--ff-only", "--no-overwrite-ignore", &fetched_ref],
            )
        };
        if let Err(err) = pull_res {
            let msg = format!("{err:#}");
            guard.last_error = Some(msg);
            return Err(err);
        }
        guard.last_error = None;
        let new_head = self
            .run_git_allow_fail(cfg, &["rev-parse", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());
        let updated = old_head != new_head;
        if updated {
            self.clear_conflict_backup(cfg);
            guard.last_conflict_branch = None;
        }
        Ok(PullResult {
            updated,
            dirty: false,
            old_head,
            new_head,
            message: if updated {
                "Pulled latest changes from remote".into()
            } else {
                "Already up to date".into()
            },
        })
    }

    pub fn git_sync(&self, commit_message: &str) -> Result<SyncResult> {
        let mut guard = self.lock.lock().unwrap();
        let Some(cfg) = &self.git else {
            bail!("Git storage is not enabled");
        };
        // Hold the cross-process store lock across branch validation, pre-stage
        // validation, staging, commit, and immutable commit-SHA capture so another
        // process cannot publish a mixed PDF/sidecar pair or switch branches mid-sync.
        let commit_lock = acquire_store_lock(&self.root)?;
        if let Err(err) = self.validate_checkout_state(cfg) {
            guard.last_error = Some(format!("{err:#}"));
            return Err(err);
        }

        // Refuse to sweep unrelated pre-staged non-sheet files (including the old
        // path of a staged rename) into a sheet sync commit.
        let pre_staged = self.run_git_raw(
            cfg,
            &["diff", "--cached", "--name-only", "-z", "--no-renames"],
        )?;
        let unrelated: Vec<&str> = pre_staged
            .split('\0')
            .filter(|p| !p.is_empty() && !is_sheet_or_sidecar_path(p))
            .collect();
        if !unrelated.is_empty() {
            bail!(
                "refusing to sync with unrelated staged files in Git index: {}",
                unrelated.join(", ")
            );
        }

        // Stage ONLY non-ignored PDF sheets, state sidecars, and deletions of tracked sheets/sidecars.
        let mut sheet_paths = Vec::new();
        collect_stageable_paths(&self.root, &self.root, &mut sheet_paths)?;
        let mut stage_paths = self.filter_non_ignored_paths(cfg, sheet_paths)?;

        // Include tracked deletions strictly for sheet PDFs and sidecars.
        let deleted = self.run_git_raw(cfg, &["ls-files", "-d", "-z"])?;
        for p in deleted.split('\0') {
            if !p.is_empty() && is_sheet_or_sidecar_path(p) && !stage_paths.iter().any(|s| s == p) {
                stage_paths.push(p.to_owned());
            }
        }

        if !stage_paths.is_empty() {
            let mut add_args: Vec<&str> = vec!["add", "--all", "--"];
            for p in &stage_paths {
                add_args.push(p.as_str());
            }
            self.run_git(cfg, &add_args)?;
        }

        let staged = self.run_git_raw(
            cfg,
            &["diff", "--cached", "--name-only", "-z", "--no-renames"],
        )?;
        let mut committed = false;
        if staged.split('\0').any(|p| !p.is_empty()) {
            let msg = if commit_message.trim().is_empty() {
                "Update MPMB character sheet"
            } else {
                commit_message.trim()
            };
            self.run_git(cfg, &["commit", "-m", msg])?;
            committed = true;
        }

        // Revalidate checkout state and capture the exact immutable commit SHA
        // for `refs/heads/<cfg.branch>` WHILE still holding `commit_lock`.
        if let Err(err) = self.validate_checkout_state(cfg) {
            guard.last_error = Some(format!("{err:#}"));
            return Err(err);
        }
        let branch_ref = format!("refs/heads/{}", cfg.branch);
        let commit_sha = self
            .run_git_allow_fail(cfg, &["rev-parse", "--verify", &branch_ref])
            .ok()
            .filter(|s| !s.is_empty());

        // Release the cross-process file lock before network push so saves on
        // another process are not blocked across slow remote pushes.
        drop(commit_lock);

        let Some(sha) = commit_sha else {
            guard.last_error = None;
            return Ok(SyncResult {
                status: "clean".into(),
                committed: false,
                pushed: false,
                commit_sha: None,
                branch: cfg.branch.clone(),
                conflict_branch: None,
                message: "No sheets to commit yet".into(),
            });
        };

        // Push the captured immutable commit SHA (never symbolic HEAD) so an
        // external branch switch after commit cannot publish another branch.
        let target_refspec = format!("{sha}:refs/heads/{}", cfg.branch);
        match self.run_git(cfg, &["push", &cfg.remote, &target_refspec]) {
            Ok(_) => {
                self.clear_conflict_backup(cfg);
                guard.last_error = None;
                guard.last_conflict_branch = None;
                Ok(SyncResult {
                    status: if committed { "synced" } else { "up_to_date" }.into(),
                    committed,
                    pushed: true,
                    commit_sha: Some(sha),
                    branch: cfg.branch.clone(),
                    conflict_branch: None,
                    message: if committed {
                        format!("Committed and pushed to {}", cfg.branch)
                    } else {
                        format!("Pushed cleanly to {}", cfg.branch)
                    },
                })
            }
            Err(push_err) => {
                let err_text = format!("{push_err:#}");
                let is_divergence = err_text.contains("non-fast-forward")
                    || err_text.contains("[rejected]")
                    || err_text.contains("fetch first")
                    || err_text.contains("Updates were rejected");
                if is_divergence {
                    // Deduplicate backups by immutable commit SHA AND destination
                    // remote/branch identity: if this exact commit is already preserved
                    // on this remote's conflict branch, reuse it rather than creating
                    // unbounded duplicate backup refs.
                    let dest_hash = self.destination_hash(cfg);
                    if let Some(existing) = self.read_conflict_backup(cfg) {
                        if existing.sha == sha
                            && existing.destination_hash == dest_hash
                            && self.remote_branch_matches_sha(cfg, &existing.branch, &sha)
                                == Some(true)
                        {
                            guard.last_conflict_branch = Some(existing.branch.clone());
                            guard.last_error = Some(format!(
                                "Remote {} diverged; local edits already saved on branch {}",
                                cfg.branch, existing.branch
                            ));
                            return Ok(SyncResult {
                                status: "conflict_branch".into(),
                                committed,
                                pushed: true,
                                commit_sha: Some(sha),
                                branch: cfg.branch.clone(),
                                conflict_branch: Some(existing.branch.clone()),
                                message: format!(
                                    "Remote {} changed elsewhere; your session is already backed up on {}",
                                    cfg.branch, existing.branch
                                ),
                            });
                        }
                    }
                    let host = hostname_slug();
                    let ts_ms = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|d| d.as_millis())
                        .unwrap_or(0);
                    let short_sha = &sha[..sha.len().min(7)];
                    let seq = CONFLICT_SEQ.fetch_add(1, Ordering::Relaxed);
                    let conflict_branch =
                        format!("{}/{host}-{ts_ms}-{short_sha}-{seq}", cfg.conflict_prefix);
                    let conflict_refspec = format!("{sha}:refs/heads/{conflict_branch}");
                    self.run_git(cfg, &["push", &cfg.remote, &conflict_refspec])
                        .with_context(|| {
                            format!(
                                "primary push rejected and fallback push to {conflict_branch} failed"
                            )
                        })?;
                    self.write_conflict_backup(cfg, &sha, &conflict_branch);
                    guard.last_conflict_branch = Some(conflict_branch.clone());
                    guard.last_error = Some(format!(
                        "Remote {} diverged; saved local edits to branch {}",
                        cfg.branch, conflict_branch
                    ));
                    return Ok(SyncResult {
                        status: "conflict_branch".into(),
                        committed,
                        pushed: true,
                        commit_sha: Some(sha),
                        branch: cfg.branch.clone(),
                        conflict_branch: Some(conflict_branch.clone()),
                        message: format!(
                            "Remote {} changed elsewhere; safely pushed your session to {}",
                            cfg.branch, conflict_branch
                        ),
                    });
                }
                guard.last_error = Some(err_text);
                Err(push_err)
            }
        }
    }

    pub fn git_history(&self, rel: Option<&str>, limit: usize) -> Result<Vec<CommitInfo>> {
        let _guard = self.lock.lock().unwrap();
        let Some(cfg) = &self.git else {
            return Ok(Vec::new());
        };
        let limit_str = limit.clamp(1, 100).to_string();
        let mut args = vec![
            "log".to_owned(),
            "-n".to_owned(),
            limit_str,
            "--format=%H\x1f%h\x1f%cI\x1f%an\x1f%s".to_owned(),
        ];
        if let Some(rel) = rel.filter(|s| !s.trim().is_empty()) {
            let (norm, _) = self.resolve_safe_pdf_path(rel)?;
            args.push("--".into());
            args.push(norm);
        }
        let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
        let Ok(out) = self.run_git_allow_fail(cfg, &arg_refs) else {
            return Ok(Vec::new());
        };
        let mut commits = Vec::new();
        for line in out.lines() {
            let parts: Vec<&str> = line.split('\x1f').collect();
            if parts.len() == 5 {
                commits.push(CommitInfo {
                    sha: parts[0].to_owned(),
                    short_sha: parts[1].to_owned(),
                    date: parts[2].to_owned(),
                    author: parts[3].to_owned(),
                    subject: parts[4].to_owned(),
                });
            }
        }
        Ok(commits)
    }

    fn bootstrap_git(&self) -> Result<()> {
        let mut guard = self.lock.lock().unwrap();
        let cfg = self.git.as_ref().unwrap();
        let git_dir = self.root.join(".git");
        if !git_dir.exists() {
            let is_empty = fs::read_dir(&self.root)?.next().is_none();
            if is_empty {
                let clone_res = self.run_git_in(
                    None,
                    cfg,
                    &[
                        "clone",
                        "--origin",
                        &cfg.remote,
                        "--branch",
                        &cfg.branch,
                        &cfg.repo_url,
                        self.root.to_str().context("non-UTF8 store path")?,
                    ],
                );
                if clone_res.is_err() {
                    // Empty remote or brand-new branch: initialize locally and wire origin.
                    self.run_git(cfg, &["init", "-b", &cfg.branch])?;
                    let _ = self
                        .run_git_allow_fail(cfg, &["remote", "add", &cfg.remote, &cfg.repo_url]);
                    if let Err(err) = self.run_git(cfg, &["fetch", &cfg.remote]) {
                        guard.last_error = Some(format!("Initial fetch deferred: {err:#}"));
                    } else {
                        let remote_ref = format!("{}/{}", cfg.remote, cfg.branch);
                        if self
                            .run_git_allow_fail(cfg, &["rev-parse", "--verify", &remote_ref])
                            .is_ok()
                        {
                            let _ =
                                self.run_git(cfg, &["checkout", "-B", &cfg.branch, &remote_ref]);
                        }
                    }
                }
            } else {
                self.run_git(cfg, &["init", "-b", &cfg.branch])?;
                let _ =
                    self.run_git_allow_fail(cfg, &["remote", "add", &cfg.remote, &cfg.repo_url]);
            }
        } else {
            // Verify active branch matches configured branch on existing checkouts.
            self.validate_branch(cfg)?;
            let existing = self
                .run_git_allow_fail(cfg, &["remote", "get-url", &cfg.remote])
                .ok();
            if existing.as_deref() != Some(cfg.repo_url.as_str()) {
                if existing.is_some() {
                    self.run_git(cfg, &["remote", "set-url", &cfg.remote, &cfg.repo_url])?;
                } else {
                    self.run_git(cfg, &["remote", "add", &cfg.remote, &cfg.repo_url])?;
                }
                // Remote destination changed: discard conflict backup markers and
                // stale remote-tracking refs from the previous remote so startup
                // sync and ahead/behind accurately target the new destination.
                self.clear_conflict_backup(cfg);
                guard.last_conflict_branch = None;
                self.clear_remote_tracking_refs(cfg);
                let _ = self.run_git_allow_fail(cfg, &["fetch", "--prune", &cfg.remote]);
            }
            // Fail closed if an explicit push URL still points to a different repository.
            self.validate_remote_urls(cfg)?;
            // Revalidate any persisted backup marker against the configured
            // destination remote so a wiped/replaced remote does not suppress sync.
            if let Some(marker) = self.read_conflict_backup(cfg) {
                if marker.destination_hash != self.destination_hash(cfg)
                    || self.remote_branch_matches_sha(cfg, &marker.branch, &marker.sha)
                        == Some(false)
                {
                    self.clear_conflict_backup(cfg);
                    guard.last_conflict_branch = None;
                }
            }
        }
        self.run_git(cfg, &["config", "user.name", &cfg.author_name])?;
        self.run_git(cfg, &["config", "user.email", &cfg.author_email])?;
        // Disable CRLF line-ending conversion so Git on Windows never corrupts binary PDF bytes.
        self.run_git(cfg, &["config", "core.autocrlf", "false"])?;
        // Keep hidden temporary staging/lock files untracked even if a crash ever left one behind.
        let exclude = self.root.join(".git/info/exclude");
        if let Ok(mut existing) = fs::read_to_string(&exclude) {
            let mut changed = false;
            for pattern in [
                format!("{STAGING_PREFIX}*{STAGING_SUFFIX}"),
                ".mpmb-store.lock".to_owned(),
            ] {
                if !existing.lines().any(|l| l.trim() == pattern) {
                    if !existing.ends_with('\n') && !existing.is_empty() {
                        existing.push('\n');
                    }
                    existing.push_str(&pattern);
                    existing.push('\n');
                    changed = true;
                }
            }
            if changed {
                let _ = fs::write(&exclude, existing);
            }
        }
        Ok(())
    }

    fn validate_branch(&self, cfg: &GitConfig) -> Result<()> {
        let active_branch = self
            .run_git_allow_fail(cfg, &["symbolic-ref", "--quiet", "--short", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());
        match active_branch.as_deref() {
            Some(b) if b == cfg.branch => Ok(()),
            Some(b) => bail!(
                "Git checkout is on branch '{}' instead of configured branch '{}'",
                b,
                cfg.branch
            ),
            None => bail!(
                "Git checkout has a detached HEAD instead of configured branch '{}'",
                cfg.branch
            ),
        }
    }

    fn validate_remote_urls(&self, cfg: &GitConfig) -> Result<()> {
        let fetch_url = self
            .run_git_allow_fail(cfg, &["remote", "get-url", &cfg.remote])
            .ok()
            .filter(|s| !s.is_empty());
        if fetch_url.as_deref() != Some(cfg.repo_url.as_str()) {
            bail!(
                "remote '{}' fetch URL '{}' differs from configured repo '{}'",
                cfg.remote,
                fetch_url.as_deref().map(redact_url).unwrap_or_default(),
                redact_url(&cfg.repo_url)
            );
        }
        if let Ok(push_urls) =
            self.run_git_allow_fail(cfg, &["remote", "get-url", "--push", "--all", &cfg.remote])
        {
            for push_url in push_urls.lines().map(str::trim).filter(|s| !s.is_empty()) {
                if push_url != cfg.repo_url {
                    bail!(
                        "remote '{}' has explicit push URL '{}' differing from configured repo '{}'",
                        cfg.remote,
                        redact_url(push_url),
                        redact_url(&cfg.repo_url)
                    );
                }
            }
        }
        Ok(())
    }

    fn validate_checkout_state(&self, cfg: &GitConfig) -> Result<()> {
        self.validate_branch(cfg)?;
        self.validate_remote_urls(cfg)?;
        Ok(())
    }

    fn filter_non_ignored_paths(&self, cfg: &GitConfig, paths: Vec<String>) -> Result<Vec<String>> {
        if paths.is_empty() {
            return Ok(Vec::new());
        }
        // Query tracked and non-ignored untracked files via NUL-delimited ls-files.
        // This avoids both stdin/stdout pipe deadlocks and Git pathspec-magic parsing
        // on literal filenames such as `:(glob)hero.pdf`.
        let listed = self.run_git_raw(
            cfg,
            &[
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
        )?;
        let eligible: HashSet<&str> = listed.split('\0').filter(|s| !s.is_empty()).collect();
        Ok(paths
            .into_iter()
            .filter(|p| eligible.contains(p.as_str()))
            .collect())
    }

    fn destination_hash(&self, cfg: &GitConfig) -> String {
        // Hash remote name, target branch, and credential-stripped URL so no raw
        // URL or token is ever written into the backup marker file.
        let safe_url = redact_url(&cfg.repo_url);
        let identity = format!("{}\0{}\0{safe_url}", cfg.remote, cfg.branch);
        sha256_hex(identity.as_bytes())
    }

    fn clear_remote_tracking_refs(&self, cfg: &GitConfig) {
        let prefix = format!("refs/remotes/{}", cfg.remote);
        let Ok(refs) =
            self.run_git_allow_fail(cfg, &["for-each-ref", "--format=%(refname)", &prefix])
        else {
            return;
        };
        for r in refs.lines().map(str::trim).filter(|l| !l.is_empty()) {
            let _ = self.run_git_allow_fail(cfg, &["update-ref", "-d", r]);
        }
    }

    fn conflict_backup_marker_path(&self, cfg: &GitConfig) -> Option<PathBuf> {
        let git_dir = self
            .run_git_allow_fail(cfg, &["rev-parse", "--git-dir"])
            .ok()
            .filter(|s| !s.is_empty())?;
        let dir_path = PathBuf::from(git_dir);
        let resolved = if dir_path.is_absolute() {
            dir_path
        } else {
            self.root.join(dir_path)
        };
        Some(resolved.join("mpmb-conflict-backup.json"))
    }

    fn read_conflict_backup(&self, cfg: &GitConfig) -> Option<ConflictBackupMarker> {
        let path = self.conflict_backup_marker_path(cfg)?;
        let bytes = fs::read(path).ok()?;
        serde_json::from_slice(&bytes).ok()
    }

    fn write_conflict_backup(&self, cfg: &GitConfig, sha: &str, branch: &str) {
        let Some(path) = self.conflict_backup_marker_path(cfg) else {
            return;
        };
        let marker = ConflictBackupMarker {
            sha: sha.to_owned(),
            branch: branch.to_owned(),
            destination_hash: self.destination_hash(cfg),
        };
        if let Ok(bytes) = serde_json::to_vec(&marker) {
            let _ = write_file_atomic_replace(&path, &bytes);
        }
    }

    fn clear_conflict_backup(&self, cfg: &GitConfig) {
        if let Some(path) = self.conflict_backup_marker_path(cfg) {
            let _ = fs::remove_file(path);
        }
    }

    /// Checks whether `refs/heads/<branch>` on `cfg.remote` points to `sha`.
    /// Returns `Some(true)` if confirmed, `Some(false)` if remote responded and
    /// does not contain the matching ref, or `None` if remote is unreachable.
    fn remote_branch_matches_sha(&self, cfg: &GitConfig, branch: &str, sha: &str) -> Option<bool> {
        let ref_name = format!("refs/heads/{branch}");
        let out = self
            .run_git_allow_fail(cfg, &["ls-remote", "--heads", &cfg.remote, &ref_name])
            .ok()?;
        Some(out.lines().any(|line| {
            let mut parts = line.split_whitespace();
            parts.next() == Some(sha) && parts.next() == Some(ref_name.as_str())
        }))
    }

    fn ahead_behind(&self, cfg: &GitConfig) -> (usize, usize) {
        let remote_ref = format!("{}/{}", cfg.remote, cfg.branch);
        let range = format!("{remote_ref}...HEAD");
        if let Ok(out) =
            self.run_git_allow_fail(cfg, &["rev-list", "--left-right", "--count", &range])
        {
            let mut parts = out.split_whitespace();
            let behind = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
            let ahead = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
            return (ahead, behind);
        }
        // Remote tracking ref may not exist yet (e.g. local commits before first successful push).
        if let Ok(count) = self.run_git_allow_fail(cfg, &["rev-list", "--count", "HEAD"]) {
            if let Ok(ahead) = count.trim().parse::<usize>() {
                return (ahead, 0);
            }
        }
        (0, 0)
    }

    fn run_git(&self, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        self.run_git_in(Some(&self.root), cfg, args)
    }

    fn run_git_raw(&self, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        self.run_git_in_raw(Some(&self.root), cfg, args)
    }

    fn run_git_allow_fail(&self, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        self.run_git_in(Some(&self.root), cfg, args)
    }

    fn prepare_git_cmd(
        &self,
        cwd: Option<&Path>,
        cfg: &GitConfig,
        args: &[&str],
    ) -> Result<Command> {
        let mut cmd = Command::new("git");
        for key in GIT_ENV_SCRUB_KEYS {
            cmd.env_remove(key);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            // Put each Git invocation in its own process group so timeout
            // teardown can terminate transport grandchildren holding pipes open.
            cmd.process_group(0);
        }
        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }
        // Treat path arguments literally for commands that interpret pathspec magic
        // (so filenames like `:hero.pdf` or `:(glob)hero.pdf` work reliably).
        if matches!(args.first().copied(), Some("add" | "log")) {
            cmd.arg("--literal-pathspecs");
        }
        // Disable CRLF conversion on every Git invocation (including initial clone)
        // so Windows Git checkouts preserve exact binary PDF bytes and SHA-256 hashes.
        cmd.arg("-c").arg("core.autocrlf=false");
        // Kubernetes local-path PVCs are commonly owned by root:<fsGroup> while
        // the server runs non-root (uid 1000). Scope safe.directory explicitly
        // to the configured store root (and local repo path if applicable).
        cmd.arg("-c")
            .arg(format!("safe.directory={}", self.root.display()));
        if Path::new(&cfg.repo_url).is_absolute() {
            cmd.arg("-c")
                .arg(format!("safe.directory={}", cfg.repo_url));
        }
        cmd.args(args);
        cmd.env("GIT_TERMINAL_PROMPT", "0");
        cmd.env("GIT_AUTHOR_NAME", &cfg.author_name);
        cmd.env("GIT_AUTHOR_EMAIL", &cfg.author_email);
        cmd.env("GIT_COMMITTER_NAME", &cfg.author_name);
        cmd.env("GIT_COMMITTER_EMAIL", &cfg.author_email);

        if let Some(ssh_key) = &cfg.ssh_key {
            let mut ssh_cmd = format!(
                "ssh -i {} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15",
                shell_quote(ssh_key.to_string_lossy().as_ref())
            );
            if let Some(kh) = &cfg.ssh_known_hosts {
                ssh_cmd.push_str(&format!(
                    " -o StrictHostKeyChecking=yes -o UserKnownHostsFile={}",
                    shell_quote(kh.to_string_lossy().as_ref())
                ));
            } else {
                ssh_cmd.push_str(" -o StrictHostKeyChecking=accept-new");
            }
            cmd.env("GIT_SSH_COMMAND", ssh_cmd);
        }
        Ok(cmd)
    }

    fn run_git_in(&self, cwd: Option<&Path>, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        Ok(self.run_git_in_raw(cwd, cfg, args)?.trim().to_owned())
    }

    fn run_git_in_raw(&self, cwd: Option<&Path>, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        let mut cmd = self.prepare_git_cmd(cwd, cfg, args)?;

        // For HTTPS tokens, pass credentials via a transient GIT_ASKPASS script
        // so the token is never written into .git/config or command arguments.
        let mut askpass_guard: Option<TempAskPass> = None;
        if let Some(token) = &cfg.https_token {
            if !token.is_empty() {
                let helper = TempAskPass::create(token)?;
                cmd.env("GIT_ASKPASS", &helper.path);
                cmd.env("MPMB_GIT_ASKPASS_TOKEN", token);
                askpass_guard = Some(helper);
            }
        }

        cmd.stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let child = cmd
            .spawn()
            .with_context(|| format!("failed to execute git {}", args.join(" ")))?;
        let label = format!("git {}", args.first().copied().unwrap_or(""));
        let output =
            wait_child_with_timeout(child, Duration::from_secs(cfg.timeout_secs.max(1)), &label)?;
        drop(askpass_guard);

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
            let detail = if !stderr.is_empty() { stderr } else { stdout };
            bail!(
                "git {} failed ({}): {}",
                args.first().copied().unwrap_or(""),
                output.status,
                redact_secrets(&detail, cfg.https_token.as_deref())
            );
        }
        Ok(String::from_utf8_lossy(&output.stdout).into_owned())
    }
}

struct TempAskPass {
    path: PathBuf,
}

impl TempAskPass {
    fn create(_token: &str) -> Result<Self> {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let path = std::env::temp_dir().join(format!(
            "mpmb-git-askpass-{}-{nanos}.sh",
            std::process::id()
        ));
        let script = "#!/bin/sh\ncase \"$1\" in\n*Username*) printf '%s\\n' 'x-access-token' ;;\n*) printf '%s\\n' \"$MPMB_GIT_ASKPASS_TOKEN\" ;;\nesac\n";
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o700)
                .open(&path)?;
            file.write_all(script.as_bytes())?;
        }
        #[cfg(not(unix))]
        {
            fs::write(&path, script)?;
        }
        Ok(Self { path })
    }
}

impl Drop for TempAskPass {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn sha256_file_bounded(path: &Path, max_bytes: usize) -> Result<String> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];
    let mut total: usize = 0;
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        total = total.saturating_add(n);
        if total > max_bytes {
            bail!("file {} exceeds {} byte limit", path.display(), max_bytes);
        }
        hasher.update(&buf[..n]);
    }
    Ok(hasher
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

#[cfg(unix)]
extern "C" {
    fn kill(pid: i32, sig: i32) -> i32;
}

fn kill_process_tree(child: &mut std::process::Child) {
    #[cfg(unix)]
    {
        // Signal the child's dedicated process group directly via POSIX kill(2)
        // with SIGKILL (9) so transport grandchildren holding output pipes open
        // are terminated immediately without spawning an external binary.
        if let Ok(pgid) = i32::try_from(child.id()) {
            if pgid > 0 {
                // SAFETY: POSIX kill(-pgid, SIGKILL) with pgid > 0 targets only
                // the child's own process group created via `process_group(0)`.
                unsafe {
                    kill(-pgid, 9);
                }
            }
        }
    }
    let _ = child.kill();
    // Bound the reap step so an unkillable child (e.g. kernel D-state) cannot
    // hold the store mutex indefinitely past the Git deadline.
    let reap_deadline = Instant::now() + Duration::from_millis(500);
    while Instant::now() < reap_deadline {
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => break,
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
        }
    }
}

fn wait_child_with_timeout(
    mut child: std::process::Child,
    timeout: Duration,
    label: &str,
) -> Result<std::process::Output> {
    let mut stdout_pipe = child.stdout.take();
    let mut stderr_pipe = child.stderr.take();
    let (out_tx, out_rx) = mpsc::channel();
    let (err_tx, err_rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut buf = Vec::new();
        if let Some(ref mut s) = stdout_pipe {
            let _ = s.read_to_end(&mut buf);
        }
        let _ = out_tx.send(buf);
    });
    std::thread::spawn(move || {
        let mut buf = Vec::new();
        if let Some(ref mut s) = stderr_pipe {
            let _ = s.read_to_end(&mut buf);
        }
        let _ = err_tx.send(buf);
    });
    let deadline = Instant::now() + timeout;
    let status = loop {
        match child.try_wait()? {
            Some(status) => break status,
            None => {
                if Instant::now() >= deadline {
                    kill_process_tree(&mut child);
                    bail!("{label} timed out after {}s", timeout.as_secs());
                }
                std::thread::sleep(Duration::from_millis(15));
            }
        }
    };
    let rem_out = deadline.saturating_duration_since(Instant::now());
    let stdout = match out_rx.recv_timeout(rem_out) {
        Ok(buf) => buf,
        Err(_) => {
            kill_process_tree(&mut child);
            bail!(
                "{label} stdout collection timed out after {}s",
                timeout.as_secs()
            );
        }
    };
    let rem_err = deadline.saturating_duration_since(Instant::now());
    let stderr = match err_rx.recv_timeout(rem_err) {
        Ok(buf) => buf,
        Err(_) => {
            kill_process_tree(&mut child);
            bail!(
                "{label} stderr collection timed out after {}s",
                timeout.as_secs()
            );
        }
    };
    Ok(std::process::Output {
        status,
        stdout,
        stderr,
    })
}

fn read_bounded(path: &Path, max_bytes: usize) -> Result<Vec<u8>> {
    let mut file = fs::File::open(path)?;
    let mut buf = Vec::new();
    let mut limited = Read::by_ref(&mut file).take((max_bytes as u64).saturating_add(1));
    limited.read_to_end(&mut buf)?;
    if buf.len() > max_bytes {
        bail!("file {} exceeds {} byte limit", path.display(), max_bytes);
    }
    Ok(buf)
}

fn is_sheet_or_sidecar_path(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    lower.ends_with(".pdf") || lower.ends_with(".state.json")
}

fn stamp_sidecar_meta(sidecar: &Value, pdf_sha256: &str, pdf_path: &Path) -> Value {
    let mut stamped = sidecar.clone();
    if let Some(obj) = stamped.as_object_mut() {
        obj.insert("pdfSha256".to_owned(), Value::String(pdf_sha256.to_owned()));
        if let Some(file_name) = pdf_path.file_name().and_then(|s| s.to_str()) {
            obj.insert(
                "pdfFileName".to_owned(),
                Value::String(file_name.to_owned()),
            );
        }
    }
    stamped
}

fn sync_parent_dir(path: &Path) {
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        if let Ok(dir) = fs::File::open(parent) {
            let _ = dir.sync_all();
        }
    }
}

struct StoreFileLock {
    _file: fs::File,
}

fn acquire_store_lock(root: &Path) -> Result<StoreFileLock> {
    let lock_path = root.join(".mpmb-store.lock");
    let file = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(&lock_path)
        .with_context(|| format!("failed to open store lock {}", lock_path.display()))?;
    file.lock()
        .with_context(|| format!("failed to acquire store lock {}", lock_path.display()))?;
    Ok(StoreFileLock { _file: file })
}

struct StagedFile {
    path: Option<PathBuf>,
}

impl StagedFile {
    fn create(target: &Path, bytes: &[u8]) -> Result<Self> {
        Ok(Self {
            path: Some(stage_temp_file(target, bytes)?),
        })
    }

    fn publish(mut self, dest: &Path) -> std::io::Result<()> {
        let src = self.path.take().expect("staged file already consumed");
        match fs::rename(&src, dest) {
            Ok(()) => Ok(()),
            Err(err) => {
                let _ = fs::remove_file(&src);
                Err(err)
            }
        }
    }
}

impl Drop for StagedFile {
    fn drop(&mut self) {
        if let Some(p) = self.path.take() {
            let _ = fs::remove_file(p);
        }
    }
}

/// Bounded streaming staging file for HTTP PDF uploads so concurrent uploads
/// do not buffer entire 64 MiB payloads in server RAM.
pub struct StagedUpload {
    path: Option<PathBuf>,
    file: Option<fs::File>,
    size: usize,
    header: Vec<u8>,
}

impl StagedUpload {
    fn create(target: &Path) -> Result<Self> {
        let parent = target
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        let pid = std::process::id();
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let seq = TEMP_SEQ.fetch_add(1, Ordering::Relaxed);
        let tmp = parent.join(format!(
            "{STAGING_PREFIX}{pid}-{nanos}-{seq}{STAGING_SUFFIX}"
        ));
        let file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&tmp)
            .with_context(|| format!("failed to create staging file {}", tmp.display()))?;
        Ok(Self {
            path: Some(tmp),
            file: Some(file),
            size: 0,
            header: Vec::with_capacity(5),
        })
    }

    pub fn write_chunk(&mut self, chunk: &[u8]) -> Result<()> {
        if chunk.is_empty() {
            return Ok(());
        }
        let next_size = self.size.saturating_add(chunk.len());
        if next_size > MAX_PDF_BYTES {
            bail!("PDF upload exceeds 64 MiB limit");
        }
        if self.header.len() < 5 {
            let need = 5 - self.header.len();
            let take = need.min(chunk.len());
            self.header.extend_from_slice(&chunk[..take]);
            if self.header.len() == 5 && !self.header.starts_with(b"%PDF-") {
                bail!("uploaded file does not start with %PDF- header");
            }
        }
        let file = self
            .file
            .as_mut()
            .ok_or_else(|| anyhow!("upload staging file already finalized"))?;
        file.write_all(chunk)?;
        self.size = next_size;
        Ok(())
    }

    fn finish(&mut self) -> Result<()> {
        if let Some(file) = self.file.take() {
            file.sync_all()?;
        }
        if self.size == 0 || self.size > MAX_PDF_BYTES {
            bail!("PDF upload must be between 1 byte and 64 MiB");
        }
        if !self.header.starts_with(b"%PDF-") {
            bail!("uploaded file does not start with %PDF- header");
        }
        Ok(())
    }

    fn validate_pdf(&self) -> Result<()> {
        let staged_path = self
            .path
            .as_deref()
            .ok_or_else(|| anyhow!("staged upload path missing"))?;
        crate::pdf::Pdf::open(staged_path)
            .context("uploaded file is not a valid readable AcroForm PDF")?;
        Ok(())
    }

    fn publish_replace(mut self, dest: &Path) -> std::io::Result<()> {
        let src = self.path.take().expect("staged upload already consumed");
        match fs::rename(&src, dest) {
            Ok(()) => Ok(()),
            Err(err) => {
                let _ = fs::remove_file(&src);
                Err(err)
            }
        }
    }

    fn publish_create_new(mut self, dest: &Path) -> Result<()> {
        let src = self.path.take().expect("staged upload already consumed");
        let res = publish_file_create_new_atomic(&src, dest);
        // On Unix, `hard_link` leaves `src` linked so we always unlink it; on Windows,
        // `MoveFileExW` consumes `src` on success so we only clean it up on failure.
        #[cfg(unix)]
        let _ = fs::remove_file(&src);
        #[cfg(not(unix))]
        if res.is_err() {
            let _ = fs::remove_file(&src);
        }
        res.with_context(|| format!("failed creating {}", dest.display()))?;
        Ok(())
    }
}

#[cfg(unix)]
fn publish_file_create_new_atomic(src: &Path, dest: &Path) -> std::io::Result<()> {
    // POSIX link(2) is atomic, same-filesystem, never replaces an existing destination
    // (returns AlreadyExists), and never exposes partial bytes at `dest`.
    fs::hard_link(src, dest)
}

#[cfg(windows)]
fn publish_file_create_new_atomic(src: &Path, dest: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;

    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(
            lp_existing_file_name: *const u16,
            lp_new_file_name: *const u16,
            dw_flags: u32,
        ) -> i32;
    }

    let src_w: Vec<u16> = src.as_os_str().encode_wide().chain(Some(0)).collect();
    let dest_w: Vec<u16> = dest.as_os_str().encode_wide().chain(Some(0)).collect();
    if src_w[..src_w.len() - 1].contains(&0) || dest_w[..dest_w.len() - 1].contains(&0) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "path contains interior NUL character",
        ));
    }
    // dwFlags = 0: same-volume atomic rename with neither MOVEFILE_REPLACE_EXISTING nor
    // MOVEFILE_COPY_ALLOWED. Works on NTFS/ReFS/FAT32/exFAT/SMB, fails with
    // ERROR_ALREADY_EXISTS if `dest` exists, and never copies partial bytes into `dest`.
    // SAFETY: `src_w` and `dest_w` are valid NUL-terminated UTF-16 buffers alive for the call.
    let ok = unsafe { MoveFileExW(src_w.as_ptr(), dest_w.as_ptr(), 0) };
    if ok != 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error())
    }
}

#[cfg(all(not(unix), not(windows)))]
fn publish_file_create_new_atomic(_src: &Path, _dest: &Path) -> std::io::Result<()> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "atomic create-only file publication is unsupported on this platform",
    ))
}

fn same_file_name_str(a: &str, b: &str) -> bool {
    #[cfg(windows)]
    {
        a.eq_ignore_ascii_case(b)
    }
    #[cfg(not(windows))]
    {
        a == b
    }
}

fn same_dir_entry_name(a: &std::ffi::OsStr, b: &std::ffi::OsStr) -> bool {
    #[cfg(windows)]
    {
        match (a.to_str(), b.to_str()) {
            (Some(sa), Some(sb)) => sa.eq_ignore_ascii_case(sb),
            _ => a == b,
        }
    }
    #[cfg(not(windows))]
    {
        a == b
    }
}

/// Returns whether any *other* existing regular `.pdf` file in `pdf_path`'s parent
/// directory derives `sidecar_path` as either its primary (`<name>.state.json`) or
/// legacy (`<stem>.state.json`) sidecar path. Fails closed (`Err`) if the directory
/// cannot be enumerated so callers never delete or misattribute an unverified sidecar.
fn sidecar_claimed_by_other_pdf(pdf_path: &Path, sidecar_path: &Path) -> Result<bool> {
    let parent = pdf_path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .ok_or_else(|| {
            anyhow!(
                "cannot determine parent directory for {}",
                pdf_path.display()
            )
        })?;
    let self_name = pdf_path
        .file_name()
        .ok_or_else(|| anyhow!("cannot determine filename for {}", pdf_path.display()))?;
    let target_sc_name = sidecar_path
        .file_name()
        .ok_or_else(|| anyhow!("cannot determine filename for {}", sidecar_path.display()))?;
    let entries = fs::read_dir(parent).with_context(|| {
        format!(
            "failed to inspect directory {} for sidecar ownership",
            parent.display()
        )
    })?;
    for entry_res in entries {
        let entry = entry_res.with_context(|| {
            format!(
                "failed reading directory entry in {} for sidecar ownership",
                parent.display()
            )
        })?;
        let name = entry.file_name();
        if same_dir_entry_name(&name, self_name) {
            continue;
        }
        let Some(name_str) = name.to_str() else {
            continue;
        };
        if !name_str.to_ascii_lowercase().ends_with(".pdf") {
            continue;
        }
        let ty = entry.file_type().with_context(|| {
            format!(
                "failed inspecting directory entry {} for sidecar ownership",
                entry.path().display()
            )
        })?;
        if !ty.is_file() {
            continue;
        }
        let other_path = entry.path();
        let other_primary = SheetStore::sidecar_path_for(&other_path);
        let other_legacy = SheetStore::legacy_sidecar_path_for(&other_path);
        if other_primary
            .file_name()
            .is_some_and(|n| same_dir_entry_name(n, target_sc_name))
            || other_legacy
                .file_name()
                .is_some_and(|n| same_dir_entry_name(n, target_sc_name))
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Inspects a sidecar file for an explicit `pdfFileName` ownership tag and returns
/// `Some(true)` if it matches `pdf_path`, `Some(false)` if it names another PDF, or
/// `None` if the sidecar is unstamped or unreadable.
fn sidecar_explicit_owner_matches(sidecar_path: &Path, pdf_path: &Path) -> Option<bool> {
    let self_name = pdf_path.file_name().and_then(|s| s.to_str())?;
    let sm = fs::symlink_metadata(sidecar_path).ok()?;
    if sm.file_type().is_symlink() || !sm.is_file() || sm.len() as usize > MAX_SIDECAR_BYTES {
        return None;
    }
    let parsed = read_bounded(sidecar_path, MAX_SIDECAR_BYTES)
        .ok()
        .and_then(|b| serde_json::from_slice::<Value>(&b).ok())?;
    let owner = parsed.get("pdfFileName").and_then(Value::as_str)?;
    Some(same_file_name_str(owner, self_name))
}

impl Drop for StagedUpload {
    fn drop(&mut self) {
        drop(self.file.take());
        if let Some(p) = self.path.take() {
            let _ = fs::remove_file(p);
        }
    }
}

fn stage_temp_file(path: &Path, bytes: &[u8]) -> Result<PathBuf> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let pid = std::process::id();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let seq = TEMP_SEQ.fetch_add(1, Ordering::Relaxed);
    // Short fixed-length staging basename independent of destination filename length.
    let tmp = parent.join(format!(
        "{STAGING_PREFIX}{pid}-{nanos}-{seq}{STAGING_SUFFIX}"
    ));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&tmp)
        .with_context(|| format!("failed to create staging file {}", tmp.display()))?;
    if let Err(err) = file.write_all(bytes).and_then(|_| file.sync_all()) {
        drop(file);
        let _ = fs::remove_file(&tmp);
        return Err(err).with_context(|| format!("failed writing staging file {}", tmp.display()));
    }
    drop(file);
    Ok(tmp)
}

#[allow(dead_code)]
pub fn write_file_atomic_replace(path: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = StagedFile::create(path, bytes)?;
    tmp.publish(path)
        .with_context(|| format!("failed replacing {}", path.display()))?;
    sync_parent_dir(path);
    Ok(())
}

fn collect_pdfs(root: &Path, dir: &Path, out: &mut Vec<SheetEntry>) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name();
        let Some(name_str) = name.to_str() else {
            // Skip non-UTF-8 filenames so lossy replacement characters cannot
            // alias distinct files on disk.
            continue;
        };
        if name_str.starts_with('.') || name_str.contains('\\') || name_str != name_str.trim() {
            continue;
        }
        let path = entry.path();
        let ty = entry.file_type()?;
        if ty.is_symlink() {
            continue;
        }
        if ty.is_dir() {
            collect_pdfs(root, &path, out)?;
        } else if ty.is_file() && name_str.to_ascii_lowercase().ends_with(".pdf") {
            match sheet_entry_from_path(root, &path) {
                Ok(item) => out.push(item),
                Err(err) => {
                    eprintln!("WARN: skipping sheet {}: {err:#}", path.display());
                }
            }
        }
    }
    Ok(())
}

fn collect_stageable_paths(root: &Path, dir: &Path, out: &mut Vec<String>) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name();
        let Some(name_str) = name.to_str() else {
            continue;
        };
        if name_str.starts_with('.') || name_str.contains('\\') || name_str != name_str.trim() {
            continue;
        }
        let path = entry.path();
        let ty = entry.file_type()?;
        if ty.is_symlink() {
            continue;
        }
        if ty.is_dir() {
            collect_stageable_paths(root, &path, out)?;
        } else if ty.is_file() && is_sheet_or_sidecar_path(name_str) {
            if let Ok(rel) = path.strip_prefix(root) {
                if let Some(rel_str) = rel.to_str() {
                    out.push(rel_str.replace('\\', "/"));
                }
            }
        }
    }
    Ok(())
}

pub fn is_template_path(rel: &str) -> bool {
    let raw = rel.replace('\\', "/");
    let mut parts = Path::new(&raw).components().filter_map(|c| match c {
        Component::Normal(seg) => seg.to_str(),
        _ => None,
    });
    matches!(parts.next(), Some(first) if first.eq_ignore_ascii_case("templates"))
        && parts.next().is_some()
}

pub fn normalize_new_character_path(name: &str) -> Result<String> {
    let trimmed = name.trim().replace('\\', "/");
    if trimmed.is_empty() {
        bail!("character name cannot be empty");
    }
    let with_ext = if trimmed.to_ascii_lowercase().ends_with(".pdf") {
        trimmed
    } else {
        format!("{trimmed}.pdf")
    };
    let parts = validate_safe_rel_pdf_path(&with_ext)?;
    let normalized = parts.join("/");
    if is_template_path(&normalized) {
        bail!("character path cannot be inside templates/");
    }
    Ok(normalized)
}

fn validate_safe_rel_pdf_path(rel: &str) -> Result<Vec<String>> {
    if rel.is_empty() || rel.len() > 240 {
        bail!("invalid sheet path");
    }
    if rel.bytes().any(|b| b < 0x20 || b == 0x7f) {
        bail!("sheet path contains control characters");
    }
    let path = Path::new(rel);
    let mut parts = Vec::new();
    for comp in path.components() {
        match comp {
            Component::Normal(seg) => {
                let s = seg
                    .to_str()
                    .ok_or_else(|| anyhow!("sheet path must be valid UTF-8"))?;
                if s.is_empty() || s.starts_with('.') || s == ".git" {
                    bail!("sheet path cannot contain hidden or .git segments");
                }
                if s != s.trim() {
                    bail!("sheet path segments cannot have leading or trailing whitespace");
                }
                parts.push(s.to_owned());
            }
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                bail!("sheet path must stay inside the sheet store");
            }
        }
    }
    if parts.is_empty() {
        bail!("sheet path is empty");
    }
    let normalized = parts.join("/");
    if !normalized.to_ascii_lowercase().ends_with(".pdf") {
        bail!("sheet path must end with .pdf");
    }
    Ok(parts)
}

fn sheet_entry_from_path(root: &Path, abs: &Path) -> Result<SheetEntry> {
    let rel_path = abs.strip_prefix(root).unwrap_or(abs);
    let rel = rel_path
        .to_str()
        .ok_or_else(|| anyhow!("sheet path must be valid UTF-8"))?
        .replace('\\', "/");
    // Enforce the exact same identifier validation as `resolve_safe_pdf_path`
    // (UTF-8, <=240 bytes, no control chars, no hidden/whitespace-padded segments)
    // so every discovered sheet identifier is guaranteed to reopen cleanly.
    let parts = validate_safe_rel_pdf_path(&rel)?;
    let rel = parts.join("/");
    let name = abs
        .file_name()
        .and_then(|n| n.to_str())
        .map(str::to_owned)
        .unwrap_or_else(|| rel.clone());
    let meta = fs::symlink_metadata(abs)?;
    if meta.file_type().is_symlink() || !meta.is_file() {
        bail!("not a regular file");
    }
    if meta.len() as usize > MAX_PDF_BYTES {
        bail!("sheet exceeds 64 MiB limit");
    }
    let pdf_sha = sha256_file_bounded(abs, MAX_PDF_BYTES)?;
    let pdf_modified = meta.modified().ok();
    let modified_unix = pdf_modified
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let primary_sidecar = SheetStore::sidecar_path_for(abs);
    let legacy_sidecar = SheetStore::legacy_sidecar_path_for(abs);
    let sidecar_candidate = if primary_sidecar.is_file() {
        Some((primary_sidecar, false))
    } else if legacy_sidecar.is_file() {
        Some((legacy_sidecar, true))
    } else {
        None
    };
    let sidecar_json = sidecar_candidate.as_ref().and_then(|(p, is_legacy)| {
        let sm = fs::symlink_metadata(p).ok()?;
        if sm.file_type().is_symlink() || !sm.is_file() || sm.len() as usize > MAX_SIDECAR_BYTES {
            return None;
        }
        let parsed = read_bounded(p, MAX_SIDECAR_BYTES)
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok())?;
        // Enforce sidecar ownership: if `pdfFileName` is stamped, it must match this PDF;
        // if unstamped, reject ambiguous sidecars that another existing PDF in the same
        // directory also derives as its primary or legacy sidecar (e.g. `Hero.pdf` vs
        // `Hero.pdf.pdf`, or case-variant siblings sharing `Hero.state.json`).
        let abs_file_name = abs.file_name().and_then(|s| s.to_str());
        match parsed.get("pdfFileName").and_then(Value::as_str) {
            Some(owner) => {
                if !abs_file_name.is_some_and(|cur| same_file_name_str(owner, cur)) {
                    return None;
                }
            }
            None => {
                // Fail closed if directory enumeration fails so unverified unstamped
                // sidecars are never misattributed.
                if sidecar_claimed_by_other_pdf(abs, p).unwrap_or(true) {
                    return None;
                }
            }
        }
        // Use sidecar metadata only when its recorded PDF SHA-256 matches the
        // current PDF bytes. Legacy pre-hash sidecars (without `pdfSha256` and
        // without the v1 schema tag) are accepted only if they are at least as
        // recent as the PDF file.
        match parsed.get("pdfSha256").and_then(Value::as_str) {
            Some(recorded) if recorded.eq_ignore_ascii_case(&pdf_sha) => Some(parsed),
            Some(_) => None,
            None => {
                let has_v1_schema = parsed.get("schema").is_some();
                let sidecar_fresh = match (sm.modified().ok(), pdf_modified) {
                    (Some(sc_t), Some(pdf_t)) => sc_t >= pdf_t,
                    _ => false,
                };
                if *is_legacy && !has_v1_schema && sidecar_fresh {
                    Some(parsed)
                } else {
                    None
                }
            }
        }
    });
    let str_opt = |v: &Value| {
        v.as_str()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
    };
    let is_template = is_template_path(&rel);
    Ok(SheetEntry {
        path: rel,
        name,
        size_bytes: meta.len(),
        sha256: pdf_sha,
        modified_unix,
        is_template,
        has_state_sidecar: sidecar_json.is_some(),
        character_name: sidecar_json
            .as_ref()
            .and_then(|j| str_opt(&j["character"]["name"])),
        class_and_levels: sidecar_json
            .as_ref()
            .and_then(|j| str_opt(&j["character"]["classAndLevels"])),
        level: sidecar_json
            .as_ref()
            .and_then(|j| str_opt(&j["character"]["level"])),
    })
}

fn shell_quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

fn hostname_slug() -> String {
    let raw = std::env::var("HOSTNAME")
        .or_else(|_| fs::read_to_string("/etc/hostname"))
        .unwrap_or_else(|_| "mpmb".into());
    let slug: String = raw
        .trim()
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' {
                c.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .take(24)
        .collect();
    if slug.is_empty() {
        "mpmb".into()
    } else {
        slug
    }
}

fn redact_url(url: &str) -> String {
    if let Some(scheme_end) = url.find("://") {
        let rest = &url[scheme_end + 3..];
        let authority_end = rest.find('/').unwrap_or(rest.len());
        if let Some(at) = rest[..authority_end].find('@') {
            return format!("{}***@{}", &url[..scheme_end + 3], &rest[at + 1..]);
        }
    }
    url.to_owned()
}

fn redact_secrets(text: &str, token: Option<&str>) -> String {
    let mut out = text.to_owned();
    if let Some(tok) = token.filter(|t| !t.is_empty()) {
        out = out.replace(tok, "***");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn temp_dir(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!(
            "mpmb-storage-{label}-{}-{nanos}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn test_git_cmd(cwd: Option<&Path>) -> Command {
        let mut cmd = Command::new("git");
        for key in GIT_ENV_SCRUB_KEYS {
            cmd.env_remove(key);
        }
        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }
        cmd
    }

    fn init_bare_remote(path: &Path) {
        let status = test_git_cmd(None)
            .args(["init", "--bare", "-b", "main"])
            .arg(path)
            .status()
            .unwrap();
        assert!(status.success(), "git init --bare failed");
    }

    fn valid_test_pdf(tag: &str) -> Vec<u8> {
        use lopdf::{dictionary, Object, StringFormat};
        let mut doc = lopdf::Document::with_version("1.7");
        let pages_id = doc.new_object_id();
        let field_id = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"PC Name".to_vec(), StringFormat::Literal),
            "V" => Object::String(tag.as_bytes().to_vec(), StringFormat::Literal),
            "Rect" => vec![10.into(), 10.into(), 200.into(), 40.into()],
        });
        let page_id = doc.add_object(dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
            "Annots" => vec![field_id.into()],
        });
        doc.objects.insert(
            pages_id,
            Object::Dictionary(dictionary! {
                "Type" => "Pages",
                "Kids" => vec![page_id.into()],
                "Count" => 1,
            }),
        );
        let form_id = doc.add_object(dictionary! {
            "Fields" => vec![field_id.into()],
        });
        let cat_id = doc.add_object(dictionary! {
            "Type" => "Catalog",
            "Pages" => pages_id,
            "AcroForm" => form_id,
        });
        doc.trailer.set("Root", cat_id);
        let mut out = Vec::new();
        doc.save_to(&mut out).unwrap();
        out
    }

    #[test]
    fn safe_path_validation_rejects_traversal_hidden_and_non_pdf() {
        let root = temp_dir("safe-paths");
        let store = SheetStore::open(StoreConfig {
            root: root.clone(),
            git: None,
        })
        .unwrap();

        for bad in [
            "",
            "../escape.pdf",
            "/etc/passwd.pdf",
            ".git/config.pdf",
            "sub/.hidden.pdf",
            "notes.txt",
            "bad\0name.pdf",
        ] {
            assert!(
                store.resolve_safe_pdf_path(bad).is_err(),
                "expected rejection for {bad:?}"
            );
        }

        let (norm, abs) = store.resolve_safe_pdf_path("campaign/hero.pdf").unwrap();
        assert_eq!(norm, "campaign/hero.pdf");
        assert!(abs.starts_with(store.root()));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn atomic_save_enforces_external_modification_conflict_guard_and_writes_sidecar() {
        let root = temp_dir("conflict-guard");
        let store = SheetStore::open(StoreConfig {
            root: root.clone(),
            git: None,
        })
        .unwrap();

        let v1_buf = valid_test_pdf("v1");
        let v1 = v1_buf.as_slice();
        let uploaded = store.upload_sheet("hero.pdf", v1, false).unwrap();
        assert_eq!(uploaded.sha256, sha256_hex(v1));
        assert!(store.upload_sheet("hero.pdf", v1, false).is_err());

        // Matching expected SHA succeeds and writes the human-readable sidecar.
        let v2 = b"%PDF-1.7\n%v2\n";
        let sidecar = json!({
            "character": {"name": "Aelar", "classAndLevels": "Wizard 5", "level": "5"},
            "hp": {"current": "32", "max": "32"}
        });
        let saved = store
            .save_sheet_atomic(
                "hero.pdf",
                v2,
                Some(&uploaded.sha256),
                Some(&sidecar),
                false,
            )
            .unwrap();
        let v2_sha = match saved {
            SaveResult::Saved {
                sha256,
                sidecar_written,
                ..
            } => {
                assert!(sidecar_written);
                sha256
            }
            other => panic!("expected Saved, got {other:?}"),
        };

        // List reads character metadata from the sidecar cleanly.
        let listed = store.list_sheets().unwrap();
        assert_eq!(listed.len(), 1);
        assert!(listed[0].has_state_sidecar);
        assert_eq!(listed[0].character_name.as_deref(), Some("Aelar"));
        assert_eq!(listed[0].level.as_deref(), Some("5"));

        // Stale SHA triggers Conflict without overwriting v2.
        let v3 = b"%PDF-1.7\n%v3-stale\n";
        let conflict = store
            .save_sheet_atomic("hero.pdf", v3, Some(&uploaded.sha256), None, false)
            .unwrap();
        assert_eq!(
            conflict,
            SaveResult::Conflict {
                expected_sha256: uploaded.sha256,
                current_sha256: v2_sha.clone(),
            }
        );
        let (_, _, disk_bytes, disk_sha) = store.read_sheet_bytes("hero.pdf").unwrap();
        assert_eq!(disk_bytes, v2);
        assert_eq!(disk_sha, v2_sha);

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn git_store_pushes_pulls_and_preserves_diverged_edits_on_conflict_branch() {
        let base = temp_dir("git-e2e");
        let bare = base.join("remote.git");
        let work_a = base.join("client-a");
        let work_b = base.join("client-b");
        init_bare_remote(&bare);
        let url = bare.to_string_lossy().into_owned();

        // Client A initializes against the empty bare remote and pushes first sheet + sidecar.
        let store_a = SheetStore::open(StoreConfig {
            root: work_a.clone(),
            git: Some(GitConfig::new(url.clone())),
        })
        .unwrap();
        let v1 = valid_test_pdf("initial");
        store_a
            .upload_sheet("campaign/hero.pdf", &v1, false)
            .unwrap();
        store_a
            .save_sheet_atomic(
                "campaign/hero.pdf",
                &v1,
                None,
                Some(&json!({"character":{"name":"Lyra","level":"3"}})),
                true,
            )
            .unwrap();
        let sync1 = store_a.git_sync("Initial Lyra level 3").unwrap();
        assert_eq!(sync1.status, "synced");
        assert!(sync1.committed);
        assert!(sync1.pushed);
        assert!(sync1.conflict_branch.is_none());

        // Client B clones the bare remote and sees Lyra immediately.
        let store_b = SheetStore::open(StoreConfig {
            root: work_b.clone(),
            git: Some(GitConfig::new(url)),
        })
        .unwrap();
        let sheets_b = store_b.list_sheets().unwrap();
        assert_eq!(sheets_b.len(), 1);
        assert_eq!(sheets_b[0].path, "campaign/hero.pdf");
        assert_eq!(sheets_b[0].character_name.as_deref(), Some("Lyra"));

        // Client A advances to level 4 and pushes to main.
        let v2_a = b"%PDF-1.7\n%level4-from-desktop\n";
        store_a
            .save_sheet_atomic(
                "campaign/hero.pdf",
                v2_a,
                None,
                Some(&json!({"character":{"name":"Lyra","level":"4"}})),
                true,
            )
            .unwrap();
        let sync_a2 = store_a.git_sync("Desktop level 4").unwrap();
        assert_eq!(sync_a2.status, "synced");

        // Meanwhile Client B edits without pulling first — push to main is rejected,
        // so store_b MUST preserve Client B's commit on a remote conflict/* branch!
        let v2_b = b"%PDF-1.7\n%session-hp-from-phone\n";
        store_b
            .save_sheet_atomic(
                "campaign/hero.pdf",
                v2_b,
                None,
                Some(&json!({"character":{"name":"Lyra","level":"3","hp":"18"}})),
                true,
            )
            .unwrap();
        let sync_b = store_b.git_sync("Phone HP update").unwrap();
        assert_eq!(sync_b.status, "conflict_branch");
        assert!(sync_b.committed);
        assert!(sync_b.pushed);
        let conflict_branch = sync_b
            .conflict_branch
            .expect("conflict branch should be created on divergence");
        assert!(conflict_branch.starts_with("conflict/"));

        // Independently verify the bare remote actually contains BOTH main and the conflict branch.
        let refs_out = test_git_cmd(Some(&bare))
            .args(["for-each-ref", "--format=%(refname:short)"])
            .output()
            .unwrap();
        let refs_str = String::from_utf8_lossy(&refs_out.stdout);
        assert!(refs_str.lines().any(|l| l == "main"));
        assert!(refs_str.lines().any(|l| l == conflict_branch));

        // Verify history listing works on client A.
        let history = store_a.git_history(Some("campaign/hero.pdf"), 10).unwrap();
        assert_eq!(history.len(), 2);
        assert_eq!(history[0].subject, "Desktop level 4");
        assert_eq!(history[1].subject, "Initial Lyra level 3");

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn external_deletion_triggers_conflict_until_forced() {
        let root = temp_dir("deleted-conflict");
        let store = SheetStore::open(StoreConfig {
            root: root.clone(),
            git: None,
        })
        .unwrap();
        let v1 = valid_test_pdf("del-v1");
        let up = store.upload_sheet("hero.pdf", &v1, false).unwrap();

        // Simulate external deletion (e.g. deleted on desktop before phone saves).
        fs::remove_file(store.root().join("hero.pdf")).unwrap();

        let conflict = store
            .save_sheet_atomic(
                "hero.pdf",
                b"%PDF-1.7\n%v2\n",
                Some(&up.sha256),
                None,
                false,
            )
            .unwrap();
        assert_eq!(
            conflict,
            SaveResult::Conflict {
                expected_sha256: up.sha256.clone(),
                current_sha256: "<deleted>".into(),
            }
        );
        assert!(!store.root().join("hero.pdf").exists());

        // Explicit force=true recreates the sheet cleanly.
        let forced = store
            .save_sheet_atomic("hero.pdf", b"%PDF-1.7\n%v2\n", Some(&up.sha256), None, true)
            .unwrap();
        assert!(matches!(forced, SaveResult::Saved { .. }));
        assert!(store.root().join("hero.pdf").exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn special_mpmb_and_unicode_filenames_roundtrip_through_git_and_sidecar() {
        let base = temp_dir("special-names");
        let bare = base.join("remote.git");
        let work = base.join("work");
        init_bare_remote(&bare);
        let store = SheetStore::open(StoreConfig {
            root: work.clone(),
            git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
        })
        .unwrap();

        let tricky = "Campaign 2024/Élodie's Sheet (v24.2.0+261023) [Printer Friendly].pdf";
        let bytes = valid_test_pdf("unicode-special");
        store.upload_sheet(tricky, &bytes, false).unwrap();
        store
            .save_sheet_atomic(
                tricky,
                &bytes,
                None,
                Some(&json!({"character":{"name":"Élodie","level":"7"}})),
                true,
            )
            .unwrap();
        let sync = store.git_sync("Add Élodie's 2024 sheet").unwrap();
        assert_eq!(sync.status, "synced");

        let listed = store.list_sheets().unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].path, tricky);
        assert_eq!(listed[0].character_name.as_deref(), Some("Élodie"));

        let history = store.git_history(Some(tricky), 5).unwrap();
        assert_eq!(history.len(), 1);
        assert_eq!(history[0].subject, "Add Élodie's 2024 sheet");

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn rapid_back_to_back_diverged_pushes_create_distinct_conflict_branches() {
        let base = temp_dir("rapid-conflicts");
        let bare = base.join("remote.git");
        let work_a = base.join("a");
        let work_b = base.join("b");
        init_bare_remote(&bare);
        let url = bare.to_string_lossy().into_owned();

        let store_a = SheetStore::open(StoreConfig {
            root: work_a,
            git: Some(GitConfig::new(url.clone())),
        })
        .unwrap();
        store_a
            .upload_sheet("s.pdf", &valid_test_pdf("0"), false)
            .unwrap();
        store_a.git_sync("base").unwrap();

        let store_b = SheetStore::open(StoreConfig {
            root: work_b,
            git: Some(GitConfig::new(url)),
        })
        .unwrap();

        // Advance remote main via A.
        store_a
            .save_sheet_atomic("s.pdf", b"%PDF-1.7\n%a1\n", None, None, true)
            .unwrap();
        store_a.git_sync("a1").unwrap();

        // Two rapid diverged pushes from B within the same second must BOTH succeed
        // on distinct remote conflict branches without colliding.
        store_b
            .save_sheet_atomic("s.pdf", b"%PDF-1.7\n%b1\n", None, None, true)
            .unwrap();
        let c1 = store_b.git_sync("b1").unwrap();
        store_b
            .save_sheet_atomic("s.pdf", b"%PDF-1.7\n%b2\n", None, None, true)
            .unwrap();
        let c2 = store_b.git_sync("b2").unwrap();

        assert_eq!(c1.status, "conflict_branch");
        assert_eq!(c2.status, "conflict_branch");
        let b1 = c1.conflict_branch.unwrap();
        let b2 = c2.conflict_branch.unwrap();
        assert_ne!(b1, b2, "rapid conflict branches must be unique");

        let b1_pdf = test_git_cmd(Some(&bare))
            .args(["show", &format!("{b1}:s.pdf")])
            .output()
            .unwrap();
        let b2_pdf = test_git_cmd(Some(&bare))
            .args(["show", &format!("{b2}:s.pdf")])
            .output()
            .unwrap();
        assert_eq!(b1_pdf.stdout, b"%PDF-1.7\n%b1\n");
        assert_eq!(b2_pdf.stdout, b"%PDF-1.7\n%b2\n");

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn git_pull_refuses_dirty_tree_and_diverged_history_without_losing_edits() {
        let base = temp_dir("pull-guards");
        let bare = base.join("remote.git");
        let work_a = base.join("a");
        let work_b = base.join("b");
        init_bare_remote(&bare);
        let url = bare.to_string_lossy().into_owned();

        let store_a = SheetStore::open(StoreConfig {
            root: work_a,
            git: Some(GitConfig::new(url.clone())),
        })
        .unwrap();
        store_a
            .upload_sheet("s.pdf", &valid_test_pdf("v0"), false)
            .unwrap();
        store_a.git_sync("v0").unwrap();

        let store_b = SheetStore::open(StoreConfig {
            root: work_b,
            git: Some(GitConfig::new(url)),
        })
        .unwrap();

        // Advance remote via A.
        store_a
            .save_sheet_atomic("s.pdf", b"%PDF-1.7\n%remote-v1\n", None, None, true)
            .unwrap();
        store_a.git_sync("remote-v1").unwrap();

        // Dirty local edit on B: pull must refuse with dirty=true and preserve local bytes.
        store_b
            .save_sheet_atomic("s.pdf", b"%PDF-1.7\n%local-dirty\n", None, None, true)
            .unwrap();
        let pull_dirty = store_b.git_pull().unwrap();
        assert!(pull_dirty.dirty);
        assert!(!pull_dirty.updated);
        assert_eq!(
            store_b.read_sheet_bytes("s.pdf").unwrap().2,
            b"%PDF-1.7\n%local-dirty\n"
        );

        // Commit locally on B (diverged from remote): ff-only pull must fail cleanly
        // without corrupting or discarding B's local commit.
        let _ = store_b.git_sync("local-commit").unwrap();
        assert!(store_b.git_pull().is_err());
        assert_eq!(
            store_b.read_sheet_bytes("s.pdf").unwrap().2,
            b"%PDF-1.7\n%local-dirty\n"
        );

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn upload_rejects_empty_and_non_pdf_payloads() {
        let root = temp_dir("upload-validation");
        let store = SheetStore::open(StoreConfig {
            root: root.clone(),
            git: None,
        })
        .unwrap();
        assert!(store.upload_sheet("empty.pdf", b"", false).is_err());
        assert!(store.upload_sheet("fake.pdf", b"not a pdf", false).is_err());
        assert!(store.list_sheets().unwrap().is_empty());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn concurrent_multithreaded_store_operations_never_corrupt_files_or_collide() {
        use std::sync::{Arc, Barrier};

        let base = temp_dir("mt-store");
        let bare = base.join("remote.git");
        let work = base.join("work");
        init_bare_remote(&bare);
        let store = Arc::new(
            SheetStore::open(StoreConfig {
                root: work,
                git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
            })
            .unwrap(),
        );
        store
            .upload_sheet("shared.pdf", &valid_test_pdf("init"), false)
            .unwrap();

        let threads = 8;
        let barrier = Arc::new(Barrier::new(threads));
        let mut handles = Vec::new();
        for tid in 0..threads {
            let st = Arc::clone(&store);
            let bar = Arc::clone(&barrier);
            handles.push(std::thread::spawn(move || {
                bar.wait();
                for iter in 0..10 {
                    let payload = format!("%PDF-1.7\n%thread-{tid}-iter-{iter}\n");
                    let sidecar = json!({"character":{"name":format!("Hero-{tid}-{iter}")}});
                    // Mix forced writes, CAS conflict-checked writes, reads, listings, and syncs.
                    if iter % 3 == 0 {
                        let res = st
                            .save_sheet_atomic(
                                "shared.pdf",
                                payload.as_bytes(),
                                Some("intentionally-stale-sha"),
                                Some(&sidecar),
                                false,
                            )
                            .unwrap();
                        assert!(matches!(res, SaveResult::Conflict { .. }));
                    } else {
                        let res = st
                            .save_sheet_atomic(
                                "shared.pdf",
                                payload.as_bytes(),
                                None,
                                Some(&sidecar),
                                true,
                            )
                            .unwrap();
                        assert!(matches!(res, SaveResult::Saved { .. }));
                    }
                    let (_, _, bytes, _) = st.read_sheet_bytes("shared.pdf").unwrap();
                    assert!(bytes.starts_with(b"%PDF-1.7\n"));
                    let listed = st.list_sheets().unwrap();
                    assert_eq!(listed.len(), 1);
                }
                if tid % 2 == 0 {
                    let sync = st.git_sync(&format!("sync from thread {tid}")).unwrap();
                    assert!(sync.pushed || sync.status == "clean");
                }
            }));
        }
        for h in handles {
            h.join().unwrap();
        }
        // Final sync must succeed cleanly with zero leftover .mpmb-tmp-* staging files.
        let final_sync = store.git_sync("final").unwrap();
        assert!(final_sync.pushed);
        for entry in fs::read_dir(store.root()).unwrap() {
            let name = entry.unwrap().file_name().to_string_lossy().into_owned();
            assert!(
                !name.contains(".mpmb-tmp-"),
                "stray staging file leaked: {name}"
            );
        }
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn storage_hardening_symlinks_sidecars_pushurl_branch_and_ignored_files() {
        let base = temp_dir("storage-hardening");
        let outside = base.join("outside");
        fs::create_dir_all(&outside).unwrap();
        fs::write(outside.join("leak.pdf"), b"%PDF-1.7\n%secret\n").unwrap();

        let bare = base.join("remote.git");
        let bare2 = base.join("remote2.git");
        init_bare_remote(&bare);
        init_bare_remote(&bare2);
        let work = base.join("work");

        let store = SheetStore::open(StoreConfig {
            root: work.clone(),
            git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
        })
        .unwrap();

        // 1. Symlink escape is rejected on read/upload/save.
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&outside, work.join("linked")).unwrap();
            assert!(store.read_sheet_bytes("linked/leak.pdf").is_err());
            assert!(store
                .upload_sheet("linked/new.pdf", &valid_test_pdf("x"), true)
                .is_err());
        }

        // 2. Sidecar directory error leaves PDF untouched.
        let orig = valid_test_pdf("orig");
        let uploaded = store.upload_sheet("hero.pdf", &orig, false).unwrap();
        let sc = SheetStore::sidecar_path_for(&work.join("hero.pdf"));
        fs::create_dir_all(&sc).unwrap();
        let err = store.save_sheet_atomic(
            "hero.pdf",
            b"%PDF-1.7\n%updated\n",
            Some(&uploaded.sha256),
            Some(&json!({"character": {"name": "Hero"}})),
            false,
        );
        assert!(err.is_err());
        assert_eq!(store.read_sheet_bytes("hero.pdf").unwrap().2, orig);
        fs::remove_dir(&sc).unwrap();

        // 3. Overwrite upload invalidates stale sidecar metadata.
        let saved = store
            .save_sheet_atomic(
                "hero.pdf",
                b"%PDF-1.7\n%v2\n",
                Some(&uploaded.sha256),
                Some(&json!({"character": {"name": "OldHero"}})),
                false,
            )
            .unwrap();
        assert!(matches!(
            saved,
            SaveResult::Saved {
                sidecar_written: true,
                ..
            }
        ));
        let replaced = store
            .upload_sheet("hero.pdf", &valid_test_pdf("v3"), true)
            .unwrap();
        assert!(!replaced.has_state_sidecar);
        assert_eq!(replaced.character_name, None);

        // 4. Ignored PDF does not block syncing other sheets, and unrelated tracked files stay unstaged.
        fs::write(work.join(".gitignore"), "drafts/\n").unwrap();
        store
            .upload_sheet("drafts/local-only.pdf", &valid_test_pdf("draft"), false)
            .unwrap();
        #[cfg(unix)]
        store
            .upload_sheet(":colon.pdf", &valid_test_pdf("colon"), false)
            .unwrap();
        fs::write(work.join("README.md"), "unrelated\n").unwrap();
        let sync = store.git_sync("sync sheets only").unwrap();
        assert!(sync.committed && sync.pushed);
        #[cfg(unix)]
        {
            let history = store.git_history(Some(":colon.pdf"), 5).unwrap();
            assert_eq!(history.len(), 1);
        }
        let committed_files = String::from_utf8(
            test_git_cmd(Some(&bare))
                .args(["show", "--name-only", "--format=", "main"])
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap();
        assert!(committed_files.contains("hero.pdf"));
        #[cfg(unix)]
        assert!(committed_files.contains(":colon.pdf"));
        assert!(!committed_files.contains("drafts/local-only.pdf"));
        assert!(!committed_files.contains("README.md"));

        // 5. Explicit mismatched pushurl fails closed on re-open.
        let status = test_git_cmd(Some(&work))
            .args([
                "remote",
                "set-url",
                "--push",
                "origin",
                &bare2.to_string_lossy(),
            ])
            .status()
            .unwrap();
        assert!(status.success());
        let err = SheetStore::open(StoreConfig {
            root: work.clone(),
            git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
        });
        assert!(err.is_err());

        // Clear explicit pushurl and test wrong active branch rejection.
        let _ = test_git_cmd(Some(&work))
            .args(["config", "--unset", "remote.origin.pushurl"])
            .status();
        let status = test_git_cmd(Some(&work))
            .args(["checkout", "-b", "other-branch"])
            .status()
            .unwrap();
        assert!(status.success());
        let err = SheetStore::open(StoreConfig {
            root: work.clone(),
            git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
        });
        assert!(err.is_err());

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn storage_round2_hardening_paths_locks_sidecars_fetch_head_and_renames() {
        let base = temp_dir("storage-round2");
        let bare = base.join("remote.git");
        let work_a = base.join("a");
        let work_b = base.join("b");
        init_bare_remote(&bare);
        let url = bare.to_string_lossy().into_owned();

        let store_a = SheetStore::open(StoreConfig {
            root: work_a.clone(),
            git: Some(GitConfig::new(url.clone())),
        })
        .unwrap();

        // 1. Whitespace-padded sheet paths are rejected so returned paths always reopen the same file.
        for bad in ["./ hero.pdf", " hero.pdf", "sub/ hero.pdf", "hero.pdf "] {
            assert!(
                store_a.resolve_safe_pdf_path(bad).is_err(),
                "expected whitespace path rejection for {bad:?}"
            );
        }
        // Discovery also skips any leading-space PDF checked into the directory.
        fs::write(work_a.join(" stray.pdf"), b"%PDF-1.7\n%stray\n").unwrap();
        assert!(store_a.list_sheets().unwrap().is_empty());
        fs::remove_file(work_a.join(" stray.pdf")).unwrap();

        // 2. Oversized serialized PDF is rejected before staging, leaving existing PDF untouched.
        let v1 = valid_test_pdf("r2-v1");
        let up = store_a.upload_sheet("hero.pdf", &v1, false).unwrap();
        let oversized = vec![b'x'; MAX_PDF_BYTES + 1];
        assert!(store_a
            .save_sheet_atomic(
                "hero.pdf",
                &oversized,
                Some(&up.sha256),
                Some(&json!({"character": {"name": "TooBig"}})),
                false,
            )
            .is_err());
        assert_eq!(store_a.read_sheet_bytes("hero.pdf").unwrap().2, v1);

        // 3. Stale sidecar metadata (mismatched pdfSha256) is ignored by listing.
        let saved = store_a
            .save_sheet_atomic(
                "hero.pdf",
                b"%PDF-1.7\n%v2\n",
                Some(&up.sha256),
                Some(&json!({"character": {"name": "V2Name"}})),
                false,
            )
            .unwrap();
        assert!(matches!(saved, SaveResult::Saved { .. }));
        assert_eq!(
            store_a.list_sheets().unwrap()[0].character_name.as_deref(),
            Some("V2Name")
        );
        // Externally replace PDF without touching sidecar.
        fs::write(work_a.join("hero.pdf"), b"%PDF-1.7\n%external-v3\n").unwrap();
        let listed = store_a.list_sheets().unwrap();
        assert_eq!(listed[0].character_name, None);
        assert!(!listed[0].has_state_sidecar);

        // 4. Deleted PDF reports Conflict even when the sidecar path is a directory.
        let v4 = valid_test_pdf("r2-v4");
        let up4 = store_a.upload_sheet("del.pdf", &v4, false).unwrap();
        fs::remove_file(work_a.join("del.pdf")).unwrap();
        let del_sc = SheetStore::sidecar_path_for(&work_a.join("del.pdf"));
        fs::create_dir_all(&del_sc).unwrap();
        let conflict = store_a
            .save_sheet_atomic(
                "del.pdf",
                b"%PDF-1.7\n%v5\n",
                Some(&up4.sha256),
                Some(&json!({"character": {"name": "Ghost"}})),
                false,
            )
            .unwrap();
        assert_eq!(
            conflict,
            SaveResult::Conflict {
                expected_sha256: up4.sha256,
                current_sha256: "<deleted>".into(),
            }
        );
        fs::remove_dir(&del_sc).unwrap();

        // 5. Unacquirable store lock (.mpmb-store.lock as a directory) fails closed on save & overwrite.
        let lock_path = work_a.join(".mpmb-store.lock");
        let _ = fs::remove_file(&lock_path);
        fs::create_dir_all(&lock_path).unwrap();
        assert!(store_a
            .save_sheet_atomic("hero.pdf", b"%PDF-1.7\n%blocked\n", None, None, true)
            .is_err());
        assert!(store_a
            .upload_sheet("hero.pdf", &valid_test_pdf("blocked-up"), true)
            .is_err());
        fs::remove_dir(&lock_path).unwrap();

        // 6. Literal pathspec-magic filename `:(glob)hero.pdf` syncs cleanly on Unix.
        #[cfg(unix)]
        {
            store_a
                .upload_sheet(":(glob)hero.pdf", &valid_test_pdf("glob"), false)
                .unwrap();
        }
        let sync1 = store_a.git_sync("Initial with literal pathspec").unwrap();
        assert!(sync1.pushed);

        // 7. Staged rename from unrelated file (`notes.txt` -> `renamed.pdf`) is rejected.
        fs::write(work_a.join("notes.txt"), "%PDF-1.7\n%notes\n").unwrap();
        assert!(test_git_cmd(Some(&work_a))
            .args(["add", "notes.txt"])
            .status()
            .unwrap()
            .success());
        assert!(test_git_cmd(Some(&work_a))
            .args([
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@local",
                "commit",
                "-m",
                "track notes",
            ])
            .status()
            .unwrap()
            .success());
        assert!(test_git_cmd(Some(&work_a))
            .args(["mv", "notes.txt", "renamed.pdf"])
            .status()
            .unwrap()
            .success());
        assert!(
            store_a.git_sync("should reject rename").is_err(),
            "staged rename deleting unrelated notes.txt must be rejected"
        );
        // Undo staged rename cleanly.
        assert!(test_git_cmd(Some(&work_a))
            .args(["reset", "--hard", "HEAD"])
            .status()
            .unwrap()
            .success());

        // 8. git_pull merges FETCH_HEAD even when remote fetch refspec maps to a custom ref.
        let store_b = SheetStore::open(StoreConfig {
            root: work_b.clone(),
            git: Some(GitConfig::new(url)),
        })
        .unwrap();
        assert!(test_git_cmd(Some(&work_b))
            .args([
                "config",
                "remote.origin.fetch",
                "+refs/heads/main:refs/remotes/origin/mirror-main",
            ])
            .status()
            .unwrap()
            .success());
        store_a
            .save_sheet_atomic("hero.pdf", b"%PDF-1.7\n%v-fetch-head\n", None, None, true)
            .unwrap();
        store_a
            .git_sync("advance main for FETCH_HEAD test")
            .unwrap();
        let pulled = store_b.git_pull().unwrap();
        assert!(pulled.updated, "pull should fast-forward via FETCH_HEAD");
        assert_eq!(
            store_b.read_sheet_bytes("hero.pdf").unwrap().2,
            b"%PDF-1.7\n%v-fetch-head\n"
        );

        // 9. wait_child_with_timeout bounds collection AND terminates grandchildren holding stderr open.
        #[cfg(unix)]
        {
            use std::os::unix::ffi::OsStrExt;
            use std::os::unix::process::CommandExt;

            // 9a. Non-UTF-8, control-char, and >240-byte paths are skipped during
            // discovery so every listed sheet identifier reopens cleanly.
            let non_utf8_name = std::ffi::OsStr::from_bytes(b"bad\xff.pdf");
            fs::write(work_a.join(non_utf8_name), b"%PDF-1.7\n%non-utf8\n").unwrap();
            let repl_name = "bad\u{FFFD}.pdf";
            fs::write(work_a.join(repl_name), b"%PDF-1.7\n%utf8-repl\n").unwrap();
            fs::write(work_a.join("bad\nnewline.pdf"), b"%PDF-1.7\n%nl\n").unwrap();
            let deep_dir = work_a.join("a".repeat(120)).join("b".repeat(120));
            fs::create_dir_all(&deep_dir).unwrap();
            fs::write(deep_dir.join("too-long.pdf"), b"%PDF-1.7\n%long\n").unwrap();
            let listed_paths: Vec<String> = store_a
                .list_sheets()
                .unwrap()
                .into_iter()
                .map(|s| s.path)
                .collect();
            assert_eq!(
                listed_paths.iter().filter(|p| *p == repl_name).count(),
                1,
                "non-UTF-8 file must not alias replacement-char filename"
            );
            assert!(
                !listed_paths.iter().any(|p| p.contains('\n')),
                "control-char filename must be skipped during discovery"
            );
            assert!(
                !listed_paths.iter().any(|p| p.len() > 240),
                "over-240-byte path must be skipped during discovery"
            );
            for p in &listed_paths {
                let (re_norm, _) = store_a.resolve_safe_pdf_path(p).unwrap();
                assert_eq!(&re_norm, p);
            }
            let mut stageable = Vec::new();
            collect_stageable_paths(&work_a, &work_a, &mut stageable).unwrap();
            assert_eq!(
                stageable.iter().filter(|p| *p == repl_name).count(),
                1,
                "non-UTF-8 file must be skipped during staging"
            );
            fs::remove_file(work_a.join(non_utf8_name)).unwrap();
            fs::remove_file(work_a.join(repl_name)).unwrap();
            fs::remove_file(work_a.join("bad\nnewline.pdf")).unwrap();
            fs::remove_dir_all(work_a.join("a".repeat(120))).unwrap();

            // 9b. Direct process-group signaling terminates BOTH:
            //     (i) a descendant holding stderr open after child exits, and
            //     (ii) a live child + descendant on the active timeout path.
            for (label, script) in [
                (
                    "exited-child-pipe-holder",
                    "sleep 30 >&2 & echo $! > PID; exit 0",
                ),
                (
                    "live-child-timeout",
                    "sleep 30 >&2 & echo $! > PID; exec sleep 30",
                ),
            ] {
                let pid_file = base.join(format!("{label}.pid"));
                let cmd_script = script.replace("PID", &pid_file.display().to_string());
                let mut cmd = Command::new("sh");
                cmd.process_group(0)
                    .args(["-c", &cmd_script])
                    .stdin(Stdio::null())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped());
                let child = cmd.spawn().unwrap();
                let child_pid = i32::try_from(child.id()).unwrap();
                let started = Instant::now();
                let res = wait_child_with_timeout(child, Duration::from_millis(250), label);
                assert!(res.is_err(), "{label} should time out");
                assert!(
                    started.elapsed() < Duration::from_secs(3),
                    "{label} hung past deadline: {:?}",
                    started.elapsed()
                );
                let grandchild_pid: i32 = fs::read_to_string(&pid_file)
                    .unwrap()
                    .trim()
                    .parse()
                    .unwrap();
                for target_pid in [child_pid, grandchild_pid] {
                    let mut alive = true;
                    for _ in 0..40 {
                        let rc = unsafe { kill(target_pid, 0) };
                        if rc != 0 {
                            alive = false;
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(25));
                    }
                    assert!(
                        !alive,
                        "{label}: process {target_pid} survived kill_process_tree"
                    );
                }
            }
        }

        // 10. Two independent SheetStore instances sharing the same root serialize
        //     save_sheet_atomic and git_sync via `.mpmb-store.lock`, so no committed
        //     revision ever contains a mismatched PDF/sidecar pair.
        let sync_base = base.join("dual-instance");
        let sync_bare = sync_base.join("remote.git");
        let sync_work = sync_base.join("work");
        init_bare_remote(&sync_bare);
        let sync_url = sync_bare.to_string_lossy().into_owned();
        let writer_store = SheetStore::open(StoreConfig {
            root: sync_work.clone(),
            git: Some(GitConfig::new(sync_url.clone())),
        })
        .unwrap();
        writer_store
            .upload_sheet("pair.pdf", &valid_test_pdf("pair-v0"), false)
            .unwrap();
        writer_store
            .save_sheet_atomic(
                "pair.pdf",
                b"%PDF-1.7\n%v0\n",
                None,
                Some(&json!({"character": {"name": "Iter-0"}})),
                true,
            )
            .unwrap();
        writer_store.git_sync("initial pair").unwrap();

        let syncer_store = SheetStore::open(StoreConfig {
            root: sync_work.clone(),
            git: Some(GitConfig::new(sync_url)),
        })
        .unwrap();

        let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
        let b1 = std::sync::Arc::clone(&barrier);
        let writer_handle = std::thread::spawn(move || {
            b1.wait();
            for i in 1..=12 {
                let pdf = format!("%PDF-1.7\n%dual-instance-iter-{i}\n");
                let sc = json!({"character": {"name": format!("Iter-{i}")}});
                let res = writer_store
                    .save_sheet_atomic("pair.pdf", pdf.as_bytes(), None, Some(&sc), true)
                    .unwrap();
                assert!(matches!(res, SaveResult::Saved { .. }));
            }
        });
        let b2 = std::sync::Arc::clone(&barrier);
        let syncer_handle = std::thread::spawn(move || {
            b2.wait();
            for i in 1..=6 {
                let _ = syncer_store.git_sync(&format!("sync-{i}")).unwrap();
            }
            syncer_store.git_sync("final-dual-sync").unwrap()
        });
        writer_handle.join().unwrap();
        let final_res = syncer_handle.join().unwrap();
        assert!(final_res.pushed || final_res.status == "clean");

        // Verify EVERY commit on remote `main` has a consistent PDF + sidecar `pdfSha256`.
        let revs_out = test_git_cmd(Some(&sync_bare))
            .args(["rev-list", "main"])
            .output()
            .unwrap();
        let revs = String::from_utf8(revs_out.stdout).unwrap();
        let mut checked_commits = 0usize;
        for rev in revs.lines().filter(|l| !l.trim().is_empty()) {
            let pdf_out = test_git_cmd(Some(&sync_bare))
                .args(["show", &format!("{rev}:pair.pdf")])
                .output()
                .unwrap();
            let sc_out = test_git_cmd(Some(&sync_bare))
                .args(["show", &format!("{rev}:pair.pdf.state.json")])
                .output()
                .unwrap();
            assert!(pdf_out.status.success() && sc_out.status.success());
            let sc_json: Value = serde_json::from_slice(&sc_out.stdout).unwrap();
            assert_eq!(
                sc_json["pdfSha256"].as_str(),
                Some(sha256_hex(&pdf_out.stdout).as_str()),
                "commit {rev} recorded mismatched PDF and sidecar"
            );
            checked_commits += 1;
        }
        assert!(checked_commits >= 2);

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn truncated_upload_is_rejected_and_preserves_pdf_and_sidecar_bytes() {
        let root = temp_dir("truncated-upload");
        let store = SheetStore::open(StoreConfig {
            root: root.clone(),
            git: None,
        })
        .unwrap();

        let original_pdf = valid_test_pdf("GoodSheet");
        let uploaded = store
            .upload_sheet("Beta.pdf", &original_pdf, false)
            .unwrap();
        let saved = store
            .save_sheet_atomic(
                "Beta.pdf",
                &original_pdf,
                Some(&uploaded.sha256),
                Some(&json!({"character": {"name": "BetaHero", "level": "6"}})),
                false,
            )
            .unwrap();
        assert!(matches!(
            saved,
            SaveResult::Saved {
                sidecar_written: true,
                ..
            }
        ));

        let pdf_path = store.root().join("Beta.pdf");
        let sidecar_path = SheetStore::sidecar_path_for(&pdf_path);
        let before_pdf = fs::read(&pdf_path).unwrap();
        let before_sidecar = fs::read(&sidecar_path).unwrap();

        // Attempting to overwrite with a truncated copy (first 40 bytes) MUST fail
        // and leave both Beta.pdf and Beta.pdf.state.json byte-identical.
        let truncated = &original_pdf[..40.min(original_pdf.len())];
        let err = store.upload_sheet("Beta.pdf", truncated, true).unwrap_err();
        assert!(
            format!("{err:#}").contains("not a valid readable"),
            "unexpected error for truncated upload: {err:#}"
        );
        assert_eq!(fs::read(&pdf_path).unwrap(), before_pdf);
        assert_eq!(fs::read(&sidecar_path).unwrap(), before_sidecar);
        // No stray staging files left behind.
        for entry in fs::read_dir(store.root()).unwrap() {
            let name = entry.unwrap().file_name().to_string_lossy().into_owned();
            assert!(!name.contains(STAGING_PREFIX), "stray temp file: {name}");
        }

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn git_sync_and_pull_fail_closed_after_external_branch_switch_or_detached_head() {
        let base = temp_dir("cross-branch-guard");
        let bare = base.join("remote.git");
        let work = base.join("work");
        init_bare_remote(&bare);
        let url = bare.to_string_lossy().into_owned();

        let store = SheetStore::open(StoreConfig {
            root: work.clone(),
            git: Some(GitConfig::new(url)),
        })
        .unwrap();
        store
            .upload_sheet("Alpha.pdf", &valid_test_pdf("Alpha"), false)
            .unwrap();
        let sync0 = store.git_sync("baseline").unwrap();
        assert!(sync0.pushed);

        let remote_main_before = String::from_utf8(
            test_git_cmd(Some(&bare))
                .args(["rev-parse", "refs/heads/main"])
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap()
        .trim()
        .to_owned();

        // Externally switch the working copy to a different branch and commit Draft.pdf.
        assert!(test_git_cmd(Some(&work))
            .args(["checkout", "-b", "draft"])
            .status()
            .unwrap()
            .success());
        fs::write(work.join("Draft.pdf"), valid_test_pdf("Draft")).unwrap();
        assert!(test_git_cmd(Some(&work))
            .args(["add", "Draft.pdf"])
            .status()
            .unwrap()
            .success());
        assert!(test_git_cmd(Some(&work))
            .args([
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@local",
                "commit",
                "-m",
                "draft-only commit",
            ])
            .status()
            .unwrap()
            .success());

        // Both git_sync and git_pull MUST fail closed and leave remote main untouched.
        let sync_err = store.git_sync("should fail on draft").unwrap_err();
        assert!(
            format!("{sync_err:#}").contains("branch 'draft'"),
            "unexpected branch sync error: {sync_err:#}"
        );
        assert!(store.git_pull().is_err());

        let remote_main_after = String::from_utf8(
            test_git_cmd(Some(&bare))
                .args(["rev-parse", "refs/heads/main"])
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap()
        .trim()
        .to_owned();
        assert_eq!(
            remote_main_after, remote_main_before,
            "remote main must not advance to draft branch commit"
        );

        // Detach HEAD and verify both git_sync and git_pull also fail closed.
        assert!(test_git_cmd(Some(&work))
            .args(["checkout", "--detach", "HEAD"])
            .status()
            .unwrap()
            .success());
        let detach_err = store.git_sync("should fail detached").unwrap_err();
        assert!(
            format!("{detach_err:#}").contains("detached HEAD"),
            "unexpected detached HEAD error: {detach_err:#}"
        );
        assert!(store.git_pull().is_err());

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn template_path_rules_and_create_sheet_from_template() {
        assert!(is_template_path("templates/MPMB-2024.pdf"));
        assert!(is_template_path("Templates/nested/blank.pdf"));
        assert!(!is_template_path("templates.pdf"));
        assert!(!is_template_path("aelar.pdf"));
        assert!(!is_template_path("campaigns/templates/aelar.pdf"));

        assert_eq!(
            normalize_new_character_path("  Aelar Stormwind  ").unwrap(),
            "Aelar Stormwind.pdf"
        );
        assert_eq!(
            normalize_new_character_path("party/Bryn.pdf").unwrap(),
            "party/Bryn.pdf"
        );
        assert!(normalize_new_character_path("").is_err());
        assert!(normalize_new_character_path("templates/Nope").is_err());
        assert!(normalize_new_character_path("Templates/Nope.pdf").is_err());
        assert!(normalize_new_character_path("../escape.pdf").is_err());

        let dir = temp_dir("template-copy");
        let store = SheetStore::open(StoreConfig {
            root: dir.clone(),
            git: None,
        })
        .unwrap();

        let tpl = store
            .upload_sheet(
                "templates/MPMB-2024-Blank.pdf",
                &valid_test_pdf("Blank"),
                false,
            )
            .unwrap();
        assert!(tpl.is_template);
        // Write a sidecar beside the template to ensure it is NOT copied to new characters.
        store
            .write_sidecar_atomic(
                "templates/MPMB-2024-Blank.pdf",
                &tpl.sha256,
                &json!({"character": {"name": "TemplateMeta"}}),
            )
            .unwrap();

        let created = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Aelar")
            .unwrap();
        assert_eq!(created.path, "Aelar.pdf");
        assert!(!created.is_template);
        assert_eq!(created.sha256, tpl.sha256);
        assert!(!created.has_state_sidecar);

        // Duplicate creation always fails cleanly (create-only).
        let dup = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Aelar")
            .unwrap_err();
        assert!(format!("{dup:#}").contains("already exists"));

        // Non-template source is rejected.
        let non_tpl = store
            .create_sheet_from_template("Aelar.pdf", "Clone")
            .unwrap_err();
        assert!(format!("{non_tpl:#}").contains("must be a template"));

        // Destination inside templates/ is rejected.
        let bad_dest = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "templates/Clone")
            .unwrap_err();
        assert!(format!("{bad_dest:#}").contains("inside templates/"));

        // prepare_template_copy fast-fails on existing destination without touching disk,
        // and publish_new_sheet_bytes atomically refuses to overwrite an existing file.
        let prep_dup = store
            .prepare_template_copy("templates/MPMB-2024-Blank.pdf", "Aelar")
            .unwrap_err();
        assert!(format!("{prep_dup:#}").contains("already exists"));
        let (dest_norm, _, bytes, _) = store
            .prepare_template_copy("templates/MPMB-2024-Blank.pdf", "RaceDest")
            .unwrap();
        assert_eq!(dest_norm, "RaceDest.pdf");
        assert!(!dir.join("RaceDest.pdf").exists());
        // Simulate a competing writer creating RaceDest.pdf before publish_new_sheet_bytes.
        let competing = valid_test_pdf("Competing");
        store
            .upload_sheet("RaceDest.pdf", &competing, false)
            .unwrap();
        let pub_err = store
            .publish_new_sheet_bytes(&dest_norm, &bytes)
            .unwrap_err();
        assert!(format!("{pub_err:#}").contains("already exists"));
        assert_eq!(fs::read(dir.join("RaceDest.pdf")).unwrap(), competing);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn template_create_invalidates_orphaned_primary_and_legacy_sidecars_and_reports_missing_template(
    ) {
        let dir = temp_dir("template-orphan-sidecars");
        let store = SheetStore::open(StoreConfig {
            root: dir.clone(),
            git: None,
        })
        .unwrap();

        let tpl = store
            .upload_sheet(
                "templates/MPMB-2024-Blank.pdf",
                &valid_test_pdf("Blank"),
                false,
            )
            .unwrap();

        // Missing template returns typed TemplateNotFoundError.
        let missing_err = store
            .prepare_template_copy("templates/Missing.pdf", "FreshHero")
            .unwrap_err();
        assert!(
            missing_err
                .downcast_ref::<TemplateNotFoundError>()
                .is_some(),
            "expected typed TemplateNotFoundError, got: {missing_err:#}"
        );

        // 1. Orphaned primary sidecar (<name>.pdf.state.json) matching template SHA-256.
        let primary_orphan = dir.join("OrphanPrimary.pdf.state.json");
        fs::write(
            &primary_orphan,
            serde_json::to_vec_pretty(&json!({
                "schema": "mpmb-sheet-state-v1",
                "pdfSha256": tpl.sha256,
                "character": { "name": "Stale Primary Hero", "classAndLevels": "Wizard 9", "level": "9" }
            }))
            .unwrap(),
        )
        .unwrap();
        let created_primary = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "OrphanPrimary")
            .unwrap();
        assert!(!created_primary.has_state_sidecar);
        assert_eq!(created_primary.character_name, None);
        assert_eq!(created_primary.class_and_levels, None);
        assert_eq!(created_primary.level, None);
        assert!(
            !primary_orphan.exists(),
            "orphaned primary sidecar should be invalidated"
        );

        // 2. Orphaned legacy sidecar (<stem>.state.json) matching template SHA-256.
        let legacy_hashed_orphan = dir.join("OrphanLegacyHashed.state.json");
        fs::write(
            &legacy_hashed_orphan,
            serde_json::to_vec_pretty(&json!({
                "pdfSha256": tpl.sha256,
                "character": { "name": "Stale Legacy Hashed", "classAndLevels": "Rogue 7", "level": "7" }
            }))
            .unwrap(),
        )
        .unwrap();
        let created_legacy_hashed = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "OrphanLegacyHashed")
            .unwrap();
        assert!(!created_legacy_hashed.has_state_sidecar);
        assert_eq!(created_legacy_hashed.character_name, None);
        assert_eq!(created_legacy_hashed.level, None);
        assert!(
            !legacy_hashed_orphan.exists(),
            "orphaned hashed legacy sidecar should be invalidated"
        );

        // 3. Orphaned pre-hash legacy sidecar (<stem>.state.json without pdfSha256/schema).
        let legacy_prehash_orphan = dir.join("OrphanLegacyPreHash.state.json");
        fs::write(
            &legacy_prehash_orphan,
            serde_json::to_vec_pretty(&json!({
                "character": { "name": "Stale Legacy PreHash", "classAndLevels": "Bard 5", "level": "5" }
            }))
            .unwrap(),
        )
        .unwrap();
        let created_legacy_prehash = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "OrphanLegacyPreHash")
            .unwrap();
        assert!(!created_legacy_prehash.has_state_sidecar);
        assert_eq!(created_legacy_prehash.character_name, None);
        assert_eq!(created_legacy_prehash.level, None);
        assert!(
            !legacy_prehash_orphan.exists(),
            "orphaned pre-hash legacy sidecar should be invalidated"
        );

        // 4. Duplicate create attempt must NEVER touch an existing sheet's sidecar.
        store
            .write_sidecar_atomic(
                "OrphanPrimary.pdf",
                &created_primary.sha256,
                &json!({"character": {"name": "Real Live Hero", "level": "3"}}),
            )
            .unwrap();
        let dup_err = store
            .publish_new_sheet_bytes("OrphanPrimary.pdf", &valid_test_pdf("Other"))
            .unwrap_err();
        assert!(format!("{dup_err:#}").contains("already exists"));
        let listed = store.list_sheets().unwrap();
        let live = listed
            .iter()
            .find(|s| s.path == "OrphanPrimary.pdf")
            .unwrap();
        assert!(live.has_state_sidecar);
        assert_eq!(live.character_name.as_deref(), Some("Real Live Hero"));

        // 5. Creating `Hero.pdf.pdf` must NOT delete `Hero.pdf`'s primary sidecar
        //    (`Hero.pdf.state.json`) and must NOT attach `Hero.pdf`'s metadata to
        //    `Hero.pdf.pdf` even when both share the exact same template hash.
        let hero_entry = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Hero")
            .unwrap();
        store
            .write_sidecar_atomic(
                "Hero.pdf",
                &hero_entry.sha256,
                &json!({"character": {"name": "Original Hero", "level": "12"}}),
            )
            .unwrap();
        let hero_sidecar_path = dir.join("Hero.pdf.state.json");
        let hero_sidecar_bytes = fs::read(&hero_sidecar_path).unwrap();

        let double_pdf = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Hero.pdf.pdf")
            .unwrap();
        assert_eq!(double_pdf.path, "Hero.pdf.pdf");
        assert!(
            !double_pdf.has_state_sidecar,
            "Hero.pdf.pdf must not attach Hero.pdf's primary sidecar as a legacy sidecar"
        );
        assert_eq!(double_pdf.character_name, None);
        assert_eq!(double_pdf.level, None);
        assert_eq!(
            fs::read(&hero_sidecar_path).unwrap(),
            hero_sidecar_bytes,
            "creating Hero.pdf.pdf must not modify or delete Hero.pdf.state.json"
        );
        let listed_after_double = store.list_sheets().unwrap();
        let hero_listed = listed_after_double
            .iter()
            .find(|s| s.path == "Hero.pdf")
            .unwrap();
        assert!(hero_listed.has_state_sidecar);
        assert_eq!(hero_listed.character_name.as_deref(), Some("Original Hero"));
        let double_listed = listed_after_double
            .iter()
            .find(|s| s.path == "Hero.pdf.pdf")
            .unwrap();
        assert!(!double_listed.has_state_sidecar);
        assert_eq!(double_listed.character_name, None);

        // 6. Real pre-PR upgrade case: when `PrePrHero.pdf` exists with an UNSTAMPED
        //    primary sidecar `PrePrHero.pdf.state.json` (no `pdfFileName`), creating
        //    `PrePrHero.pdf.pdf` is rejected with a conflict BEFORE publishing so the
        //    preexisting character's metadata is never hidden by ambiguity.
        let tpl_bytes = fs::read(dir.join("templates/MPMB-2024-Blank.pdf")).unwrap();
        store
            .upload_sheet("PrePrHero.pdf", &tpl_bytes, false)
            .unwrap();
        let pre_pr_sidecar_path = dir.join("PrePrHero.pdf.state.json");
        let pre_pr_sidecar_bytes = serde_json::to_vec_pretty(&json!({
            "schema": "mpmb-sheet-state/v1",
            "pdfSha256": tpl.sha256,
            "character": { "name": "Pre-PR Hero", "level": "13" }
        }))
        .unwrap();
        fs::write(&pre_pr_sidecar_path, &pre_pr_sidecar_bytes).unwrap();
        let pre_pr_before = store
            .list_sheets()
            .unwrap()
            .into_iter()
            .find(|s| s.path == "PrePrHero.pdf")
            .unwrap();
        assert!(pre_pr_before.has_state_sidecar);
        assert_eq!(pre_pr_before.character_name.as_deref(), Some("Pre-PR Hero"));
        assert_eq!(pre_pr_before.level.as_deref(), Some("13"));
        let pre_pr_err = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "PrePrHero.pdf.pdf")
            .unwrap_err();
        assert!(
            format!("{pre_pr_err:#}").contains("conflict"),
            "creating sibling that makes pre-PR unstamped sidecar ambiguous must conflict: {pre_pr_err:#}"
        );
        assert!(!dir.join("PrePrHero.pdf.pdf").exists());
        assert_eq!(
            fs::read(&pre_pr_sidecar_path).unwrap(),
            pre_pr_sidecar_bytes
        );
        let listed_pre_pr = store.list_sheets().unwrap();
        let pre_pr_listed = listed_pre_pr
            .iter()
            .find(|s| s.path == "PrePrHero.pdf")
            .unwrap();
        assert!(pre_pr_listed.has_state_sidecar);
        assert_eq!(pre_pr_listed.character_name.as_deref(), Some("Pre-PR Hero"));
        assert_eq!(pre_pr_listed.level.as_deref(), Some("13"));

        // 7. Reverse direction: when `Reverse.pdf.pdf` already exists with a legacy
        //    sidecar `Reverse.pdf.state.json`, creating `Reverse.pdf` is rejected with
        //    conflict BEFORE publishing so `Reverse.pdf.state.json` is neither deleted
        //    nor clobbered, and `Reverse.pdf.pdf` keeps its metadata.
        store
            .upload_sheet("Reverse.pdf.pdf", &tpl_bytes, false)
            .unwrap();
        let reverse_legacy_path = dir.join("Reverse.pdf.state.json");
        let reverse_legacy_bytes = serde_json::to_vec_pretty(&json!({
            "pdfSha256": tpl.sha256,
            "character": { "name": "Legacy Double PDF Owner", "level": "14" }
        }))
        .unwrap();
        fs::write(&reverse_legacy_path, &reverse_legacy_bytes).unwrap();
        let reverse_before = store
            .list_sheets()
            .unwrap()
            .into_iter()
            .find(|s| s.path == "Reverse.pdf.pdf")
            .unwrap();
        assert!(reverse_before.has_state_sidecar);
        assert_eq!(
            reverse_before.character_name.as_deref(),
            Some("Legacy Double PDF Owner")
        );
        assert_eq!(reverse_before.level.as_deref(), Some("14"));

        let reverse_err = store
            .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Reverse")
            .unwrap_err();
        assert!(
            format!("{reverse_err:#}").contains("conflict"),
            "creating Reverse.pdf over Reverse.pdf.pdf's legacy sidecar must conflict: {reverse_err:#}"
        );
        assert!(!dir.join("Reverse.pdf").exists());
        assert_eq!(
            fs::read(&reverse_legacy_path).unwrap(),
            reverse_legacy_bytes,
            "Reverse.pdf.state.json bytes must remain untouched"
        );
        let listed_after_reverse = store.list_sheets().unwrap();
        let reverse_dbl_listed = listed_after_reverse
            .iter()
            .find(|s| s.path == "Reverse.pdf.pdf")
            .unwrap();
        assert!(reverse_dbl_listed.has_state_sidecar);
        assert_eq!(
            reverse_dbl_listed.character_name.as_deref(),
            Some("Legacy Double PDF Owner")
        );
        assert_eq!(reverse_dbl_listed.level.as_deref(), Some("14"));

        // 8. Later saves cannot clobber a shared legacy sidecar even if both PDFs
        //    already coexist externally on disk.
        let extern_pdf = dir.join("Extern.pdf");
        fs::write(&extern_pdf, &tpl_bytes).unwrap();
        fs::write(dir.join("Extern.pdf.pdf"), &tpl_bytes).unwrap();
        let extern_legacy_sc = dir.join("Extern.pdf.state.json");
        let extern_legacy_bytes = serde_json::to_vec_pretty(&json!({
            "pdfSha256": tpl.sha256,
            "character": { "name": "Extern Double Owner", "level": "16" }
        }))
        .unwrap();
        fs::write(&extern_legacy_sc, &extern_legacy_bytes).unwrap();
        let new_pdf_bytes = valid_test_pdf("ExternEdited");
        let save_err = store
            .save_sheet_atomic(
                "Extern.pdf",
                &new_pdf_bytes,
                Some(&tpl.sha256),
                Some(&json!({"character": {"name": "Clobber Attempt"}})),
                false,
            )
            .unwrap_err();
        assert!(
            format!("{save_err:#}").contains("conflict"),
            "save_sheet_atomic must not clobber shared legacy sidecar: {save_err:#}"
        );
        assert_eq!(fs::read(&extern_pdf).unwrap(), tpl_bytes);
        assert_eq!(fs::read(&extern_legacy_sc).unwrap(), extern_legacy_bytes);
        let sc_err = store
            .write_sidecar_atomic(
                "Extern.pdf",
                &tpl.sha256,
                &json!({"character": {"name": "Clobber Attempt"}}),
            )
            .unwrap_err();
        assert!(
            format!("{sc_err:#}").contains("conflict"),
            "write_sidecar_atomic must not clobber shared legacy sidecar: {sc_err:#}"
        );
        assert_eq!(fs::read(&extern_legacy_sc).unwrap(), extern_legacy_bytes);

        // 9. On case-sensitive filesystems, when `Sibling.PDF` exists with an unstamped
        //    legacy `Sibling.state.json`, creating `Sibling.pdf` is rejected with conflict
        //    BEFORE publishing so `Sibling.PDF` keeps its metadata and sidecar bytes.
        let sibling_upper = dir.join("Sibling.PDF");
        let sibling_lower = dir.join("Sibling.pdf");
        fs::write(&sibling_upper, &tpl_bytes).unwrap();
        if !sibling_lower.exists() {
            let sibling_legacy = dir.join("Sibling.state.json");
            let sibling_legacy_bytes = serde_json::to_vec_pretty(&json!({
                "pdfSha256": tpl.sha256,
                "character": { "name": "Upper Owner", "level": "11" }
            }))
            .unwrap();
            fs::write(&sibling_legacy, &sibling_legacy_bytes).unwrap();
            let sibling_before = store
                .list_sheets()
                .unwrap()
                .into_iter()
                .find(|s| s.path == "Sibling.PDF")
                .unwrap();
            assert!(sibling_before.has_state_sidecar);
            assert_eq!(
                sibling_before.character_name.as_deref(),
                Some("Upper Owner")
            );
            assert_eq!(sibling_before.level.as_deref(), Some("11"));
            let sibling_err = store
                .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "Sibling")
                .unwrap_err();
            assert!(
                format!("{sibling_err:#}").contains("conflict"),
                "creating case-variant sibling over shared unstamped legacy sidecar must conflict: {sibling_err:#}"
            );
            assert!(!sibling_lower.exists());
            assert_eq!(
                fs::read(&sibling_legacy).unwrap(),
                sibling_legacy_bytes,
                "legacy sidecar belonging to Sibling.PDF must not be deleted or modified"
            );
            let listed_after_sibling = store.list_sheets().unwrap();
            let sibling_upper_listed = listed_after_sibling
                .iter()
                .find(|s| s.path == "Sibling.PDF")
                .unwrap();
            assert!(sibling_upper_listed.has_state_sidecar);
            assert_eq!(
                sibling_upper_listed.character_name.as_deref(),
                Some("Upper Owner")
            );
            assert_eq!(sibling_upper_listed.level.as_deref(), Some("11"));
        }

        // 10. Unremovable orphaned sidecar fails cleanly before publication AND retrying
        //     the same name succeeds cleanly once the orphan is unlocked/removable.
        #[cfg(windows)]
        {
            let locked_orphan = dir.join("LockedOrphan.pdf.state.json");
            fs::write(
                &locked_orphan,
                serde_json::to_vec_pretty(&json!({
                    "pdfSha256": tpl.sha256,
                    "character": { "name": "Locked Stale Hero" }
                }))
                .unwrap(),
            )
            .unwrap();
            let orig_perms = fs::metadata(&locked_orphan).unwrap().permissions();
            let mut ro_perms = orig_perms.clone();
            ro_perms.set_readonly(true);
            fs::set_permissions(&locked_orphan, ro_perms).unwrap();
            let locked_err = store
                .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "LockedOrphan")
                .unwrap_err();
            assert!(
                format!("{locked_err:#}").contains("failed to remove stale sidecar"),
                "expected stale sidecar removal error, got: {locked_err:#}"
            );
            assert!(
                !dir.join("LockedOrphan.pdf").exists(),
                "destination PDF must not be published when orphaned sidecar cannot be removed"
            );
            fs::set_permissions(&locked_orphan, orig_perms).unwrap();
            let retried = store
                .create_sheet_from_template("templates/MPMB-2024-Blank.pdf", "LockedOrphan")
                .unwrap();
            assert_eq!(retried.path, "LockedOrphan.pdf");
            assert!(!retried.has_state_sidecar);
            assert_eq!(retried.character_name, None);
            assert!(!locked_orphan.exists());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let ro_dir = dir.join("readonly-orphan-dir");
            fs::create_dir_all(&ro_dir).unwrap();
            let locked_orphan = ro_dir.join("LockedOrphan.pdf.state.json");
            let locked_orphan_bytes = serde_json::to_vec_pretty(&json!({
                "pdfSha256": tpl.sha256,
                "character": { "name": "Locked Stale Hero" }
            }))
            .unwrap();
            fs::write(&locked_orphan, &locked_orphan_bytes).unwrap();
            // Stage the upload while the directory is writable, then make the directory
            // read-only so `commit_staged_upload` deterministically hits the failed
            // `remove_file` path inside `invalidate_sidecars_for` BEFORE `publish_create_new`.
            let (norm, mut staged) = store
                .start_staged_upload("readonly-orphan-dir/LockedOrphan.pdf")
                .unwrap();
            staged.write_chunk(&tpl_bytes).unwrap();
            fs::set_permissions(&ro_dir, fs::Permissions::from_mode(0o555)).unwrap();
            let commit_res = store.commit_staged_upload(&norm, staged, false);
            fs::set_permissions(&ro_dir, fs::Permissions::from_mode(0o755)).unwrap();
            // Skip failure assertion only when running as UID 0 (root bypasses 0555 dir checks).
            if locked_orphan.exists() {
                let err = commit_res.unwrap_err();
                assert!(
                    format!("{err:#}").contains("failed to remove stale sidecar"),
                    "expected stale sidecar removal error, got: {err:#}"
                );
                assert!(
                    !ro_dir.join("LockedOrphan.pdf").exists(),
                    "destination PDF must not be published when orphaned sidecar removal fails"
                );
                assert_eq!(fs::read(&locked_orphan).unwrap(), locked_orphan_bytes);
                let listed_after_fail = store.list_sheets().unwrap();
                assert!(
                    !listed_after_fail
                        .iter()
                        .any(|s| s.path == "readonly-orphan-dir/LockedOrphan.pdf"),
                    "failed create must not appear in sheet listing"
                );
                // Once directory is writable again, retrying the exact same destination succeeds cleanly.
                let retried = store
                    .create_sheet_from_template(
                        "templates/MPMB-2024-Blank.pdf",
                        "readonly-orphan-dir/LockedOrphan",
                    )
                    .unwrap();
                assert_eq!(retried.path, "readonly-orphan-dir/LockedOrphan.pdf");
                assert!(!retried.has_state_sidecar);
                assert_eq!(retried.character_name, None);
                assert!(!locked_orphan.exists());
            }

            // 11. Write+exec, non-enumerable directory (`0o333`): directory enumeration
            //     fails closed so an existing sibling's sidecar is NEVER deleted as an
            //     apparent orphan and creation aborts cleanly.
            let wo_dir = dir.join("write-only-dir");
            fs::create_dir_all(&wo_dir).unwrap();
            let wo_upper = wo_dir.join("WoSibling.PDF");
            let wo_lower = wo_dir.join("WoSibling.pdf");
            fs::write(&wo_upper, &tpl_bytes).unwrap();
            if !wo_lower.exists() {
                let wo_legacy = wo_dir.join("WoSibling.state.json");
                let wo_legacy_bytes = serde_json::to_vec_pretty(&json!({
                    "pdfSha256": tpl.sha256,
                    "character": { "name": "WriteOnly Sibling", "level": "17" }
                }))
                .unwrap();
                fs::write(&wo_legacy, &wo_legacy_bytes).unwrap();
                let wo_before = store
                    .list_sheets()
                    .unwrap()
                    .into_iter()
                    .find(|s| s.path == "write-only-dir/WoSibling.PDF")
                    .unwrap();
                assert!(wo_before.has_state_sidecar);
                assert_eq!(
                    wo_before.character_name.as_deref(),
                    Some("WriteOnly Sibling")
                );
                assert_eq!(wo_before.level.as_deref(), Some("17"));

                // Stage while writable+readable, then drop read bit (`0o333`) so
                // `read_dir` fails while `lstat`, `unlink`, and `hard_link` would succeed.
                let (wo_norm, mut wo_staged) = store
                    .start_staged_upload("write-only-dir/WoSibling.pdf")
                    .unwrap();
                wo_staged.write_chunk(&tpl_bytes).unwrap();
                fs::set_permissions(&wo_dir, fs::Permissions::from_mode(0o333)).unwrap();
                let read_dir_blocked = fs::read_dir(&wo_dir).is_err();
                let wo_create_res = store.create_sheet_from_template(
                    "templates/MPMB-2024-Blank.pdf",
                    "write-only-dir/WoSibling",
                );
                let wo_commit_res = store.commit_staged_upload(&wo_norm, wo_staged, false);
                fs::set_permissions(&wo_dir, fs::Permissions::from_mode(0o755)).unwrap();
                if read_dir_blocked {
                    let create_err = wo_create_res.unwrap_err();
                    assert!(
                        format!("{create_err:#}").contains("failed to inspect directory"),
                        "expected fail-closed ownership scan error on create, got: {create_err:#}"
                    );
                    let commit_err = wo_commit_res.unwrap_err();
                    assert!(
                        format!("{commit_err:#}").contains("failed to inspect directory"),
                        "expected fail-closed ownership scan error on commit, got: {commit_err:#}"
                    );
                    assert!(
                        !wo_lower.exists(),
                        "destination PDF must not be created when ownership scan fails"
                    );
                    assert_eq!(
                        fs::read(&wo_legacy).unwrap(),
                        wo_legacy_bytes,
                        "sibling legacy sidecar must NOT be deleted when directory enumeration fails"
                    );
                    let wo_after = store
                        .list_sheets()
                        .unwrap()
                        .into_iter()
                        .find(|s| s.path == "write-only-dir/WoSibling.PDF")
                        .unwrap();
                    assert!(wo_after.has_state_sidecar);
                    assert_eq!(
                        wo_after.character_name.as_deref(),
                        Some("WriteOnly Sibling")
                    );
                    assert_eq!(wo_after.level.as_deref(), Some("17"));
                }
            }
        }

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn publish_create_new_is_atomic_and_refuses_overwrite_without_copy_fallback() {
        let dir = temp_dir("publish-create-new");
        let target = dir.join("Hero.pdf");
        let payload = valid_test_pdf("Hero");

        // 1. StagedUpload::publish_create_new publishes atomically and cleans up staging file.
        let mut staged = StagedUpload::create(&target).unwrap();
        staged.write_chunk(&payload).unwrap();
        staged.finish().unwrap();
        staged.publish_create_new(&target).unwrap();
        assert_eq!(fs::read(&target).unwrap(), payload);
        let leftover_tmp = fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .any(|e| e.file_name().to_string_lossy().starts_with(STAGING_PREFIX));
        assert!(!leftover_tmp, "staging temp file must be cleaned up");

        // 2. publish_create_new refuses to overwrite an existing destination, keeps its
        //    bytes intact, and removes the staging temp file.
        let mut staged2 = StagedUpload::create(&target).unwrap();
        staged2.write_chunk(&valid_test_pdf("Other")).unwrap();
        staged2.finish().unwrap();
        let err = staged2.publish_create_new(&target).unwrap_err();
        assert!(
            err.downcast_ref::<std::io::Error>()
                .is_some_and(|io| io.kind() == std::io::ErrorKind::AlreadyExists),
            "expected AlreadyExists, got: {err:#}"
        );
        assert_eq!(fs::read(&target).unwrap(), payload);
        let leftover_tmp2 = fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .any(|e| e.file_name().to_string_lossy().starts_with(STAGING_PREFIX));
        assert!(
            !leftover_tmp2,
            "staging temp file must be cleaned up after AlreadyExists"
        );

        // 3. Failing atomic publication into a missing parent fails cleanly without leaving
        //    any partial destination file or staging file behind.
        let missing_dest = dir.join("no-such-dir").join("Ghost.pdf");
        let mut staged3 = StagedUpload::create(&target).unwrap();
        staged3.write_chunk(&payload).unwrap();
        staged3.finish().unwrap();
        assert!(staged3.publish_create_new(&missing_dest).is_err());
        assert!(!missing_dest.exists());
        let leftover_tmp3 = fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .any(|e| e.file_name().to_string_lossy().starts_with(STAGING_PREFIX));
        assert!(
            !leftover_tmp3,
            "staging temp file must be cleaned up after publish error"
        );

        let _ = fs::remove_dir_all(&dir);
    }
}
