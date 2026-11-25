use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
    process::Command,
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};

static TEMP_SEQ: AtomicU64 = AtomicU64::new(1);
static CONFLICT_SEQ: AtomicU64 = AtomicU64::new(1);

pub const MAX_PDF_BYTES: usize = 64 * 1024 * 1024;

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
    pub last_conflict_branch: Option<String>,
    pub last_error: Option<String>,
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

    pub fn resolve_safe_pdf_path(&self, rel: &str) -> Result<(String, PathBuf)> {
        let trimmed = rel.trim().replace('\\', "/");
        if trimmed.is_empty() || trimmed.len() > 240 {
            bail!("invalid sheet path");
        }
        if trimmed.bytes().any(|b| b < 0x20 || b == 0x7f) {
            bail!("sheet path contains control characters");
        }
        let path = Path::new(&trimmed);
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
        let abs = parts.iter().fold(self.root.clone(), |acc, p| acc.join(p));
        Ok((normalized, abs))
    }

    pub fn sidecar_path_for(pdf_path: &Path) -> PathBuf {
        let stem = pdf_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("sheet");
        pdf_path.with_file_name(format!("{stem}.state.json"))
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
        let meta = fs::metadata(&abs).with_context(|| format!("sheet not found: {normalized}"))?;
        if meta.len() as usize > MAX_PDF_BYTES {
            bail!("sheet exceeds 64 MiB limit");
        }
        let bytes = fs::read(&abs).with_context(|| format!("failed reading {normalized}"))?;
        let sha = sha256_hex(&bytes);
        Ok((normalized, abs, bytes, sha))
    }

    pub fn upload_sheet(&self, rel: &str, bytes: &[u8], overwrite: bool) -> Result<SheetEntry> {
        let _guard = self.lock.lock().unwrap();
        if bytes.is_empty() || bytes.len() > MAX_PDF_BYTES {
            bail!("PDF upload must be between 1 byte and 64 MiB");
        }
        if !bytes.starts_with(b"%PDF-") {
            bail!("uploaded file does not start with %PDF- header");
        }
        let (normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        if abs.exists() && !overwrite {
            bail!("sheet already exists: {normalized} (pass overwrite=true to replace)");
        }
        if let Some(parent) = abs.parent() {
            fs::create_dir_all(parent)?;
        }
        write_file_atomic_replace(&abs, bytes)?;
        sheet_entry_from_path(&self.root, &abs)
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
        let (_normalized, abs) = self.resolve_safe_pdf_path(rel)?;
        if let Some(expected) = expected_sha256 {
            if !force {
                if !abs.exists() {
                    return Ok(SaveResult::Conflict {
                        expected_sha256: expected.to_owned(),
                        current_sha256: "<deleted>".to_owned(),
                    });
                }
                let current_bytes = fs::read(&abs)?;
                let current_sha = sha256_hex(&current_bytes);
                if current_sha != expected {
                    return Ok(SaveResult::Conflict {
                        expected_sha256: expected.to_owned(),
                        current_sha256: current_sha,
                    });
                }
            }
        }
        if let Some(parent) = abs.parent() {
            fs::create_dir_all(parent)?;
        }
        write_file_atomic_replace(&abs, pdf_bytes)?;
        let mut sidecar_written = false;
        if let Some(sidecar) = state_sidecar {
            let sidecar_path = Self::sidecar_path_for(&abs);
            let mut pretty = serde_json::to_vec_pretty(sidecar)?;
            pretty.push(b'\n');
            write_file_atomic_replace(&sidecar_path, &pretty)?;
            sidecar_written = true;
        }
        Ok(SaveResult::Saved {
            sha256: sha256_hex(pdf_bytes),
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
            .run_git_allow_fail(cfg, &["status", "--porcelain"])
            .unwrap_or_default();
        let changed_files: Vec<String> = porcelain
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| l.trim().to_owned())
            .collect();
        let (ahead, behind) = self.ahead_behind(cfg);
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
            last_conflict_branch: guard.last_conflict_branch.clone(),
            last_error: guard.last_error.clone(),
        })
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
        let old_head = self
            .run_git_allow_fail(cfg, &["rev-parse", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());
        let porcelain = self
            .run_git_allow_fail(cfg, &["status", "--porcelain"])
            .unwrap_or_default();
        if !porcelain.trim().is_empty() {
            return Ok(PullResult {
                updated: false,
                dirty: true,
                old_head: old_head.clone(),
                new_head: old_head,
                message: "Working tree has uncommitted local changes; sync before pulling".into(),
            });
        }
        if let Err(err) = self.run_git(cfg, &["fetch", &cfg.remote, &cfg.branch]) {
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
        let remote_ref = format!("{}/{}", cfg.remote, cfg.branch);
        let pull_res = if old_head.is_none() {
            self.run_git(cfg, &["checkout", "-B", &cfg.branch, &remote_ref])
        } else {
            self.run_git(cfg, &["merge", "--ff-only", &remote_ref])
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
        // Stage all PDF sheets, state sidecars, and deletions without staging temporary files.
        let mut sheet_paths = Vec::new();
        collect_stageable_paths(&self.root, &self.root, &mut sheet_paths)?;
        let mut add_args: Vec<&str> = vec!["add", "--all", "--"];
        if sheet_paths.is_empty() {
            // Still stage deletions if files were removed.
            let _ = self.run_git_allow_fail(cfg, &["add", "-u"]);
        } else {
            for p in &sheet_paths {
                add_args.push(p.as_str());
            }
            self.run_git(cfg, &add_args)?;
            let _ = self.run_git_allow_fail(cfg, &["add", "-u"]);
        }

        let staged = self
            .run_git_allow_fail(cfg, &["diff", "--cached", "--name-only"])
            .unwrap_or_default();
        let mut committed = false;
        if !staged.trim().is_empty() {
            let msg = if commit_message.trim().is_empty() {
                "Update MPMB character sheet"
            } else {
                commit_message.trim()
            };
            self.run_git(cfg, &["commit", "-m", msg])?;
            committed = true;
        }

        let commit_sha = self
            .run_git_allow_fail(cfg, &["rev-parse", "HEAD"])
            .ok()
            .filter(|s| !s.is_empty());

        if commit_sha.is_none() {
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
        }

        let target_refspec = format!("HEAD:refs/heads/{}", cfg.branch);
        match self.run_git(cfg, &["push", &cfg.remote, &target_refspec]) {
            Ok(_) => {
                guard.last_error = None;
                guard.last_conflict_branch = None;
                Ok(SyncResult {
                    status: if committed { "synced" } else { "up_to_date" }.into(),
                    committed,
                    pushed: true,
                    commit_sha,
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
                    let host = hostname_slug();
                    let ts_ms = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|d| d.as_millis())
                        .unwrap_or(0);
                    let short_sha = commit_sha
                        .as_deref()
                        .map(|s| &s[..s.len().min(7)])
                        .unwrap_or("head");
                    let seq = CONFLICT_SEQ.fetch_add(1, Ordering::Relaxed);
                    let conflict_branch =
                        format!("{}/{host}-{ts_ms}-{short_sha}-{seq}", cfg.conflict_prefix);
                    let conflict_refspec = format!("HEAD:refs/heads/{conflict_branch}");
                    self.run_git(cfg, &["push", &cfg.remote, &conflict_refspec])
                        .with_context(|| {
                            format!(
                                "primary push rejected and fallback push to {conflict_branch} failed"
                            )
                        })?;
                    guard.last_conflict_branch = Some(conflict_branch.clone());
                    guard.last_error = Some(format!(
                        "Remote {} diverged; saved local edits to branch {}",
                        cfg.branch, conflict_branch
                    ));
                    return Ok(SyncResult {
                        status: "conflict_branch".into(),
                        committed,
                        pushed: true,
                        commit_sha,
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
            let existing = self
                .run_git_allow_fail(cfg, &["remote", "get-url", &cfg.remote])
                .ok();
            if existing.as_deref() != Some(cfg.repo_url.as_str()) {
                if existing.is_some() {
                    self.run_git(cfg, &["remote", "set-url", &cfg.remote, &cfg.repo_url])?;
                } else {
                    self.run_git(cfg, &["remote", "add", &cfg.remote, &cfg.repo_url])?;
                }
            }
        }
        self.run_git(cfg, &["config", "user.name", &cfg.author_name])?;
        self.run_git(cfg, &["config", "user.email", &cfg.author_email])?;
        // Keep temporary staging files untracked even if a crash ever left one behind.
        let exclude = self.root.join(".git/info/exclude");
        if let Ok(mut existing) = fs::read_to_string(&exclude) {
            if !existing.contains("*.mpmb-tmp-*") {
                if !existing.ends_with('\n') && !existing.is_empty() {
                    existing.push('\n');
                }
                existing.push_str("*.mpmb-tmp-*\n");
                let _ = fs::write(&exclude, existing);
            }
        }
        Ok(())
    }

    fn ahead_behind(&self, cfg: &GitConfig) -> (usize, usize) {
        let remote_ref = format!("{}/{}", cfg.remote, cfg.branch);
        let range = format!("{remote_ref}...HEAD");
        let Ok(out) =
            self.run_git_allow_fail(cfg, &["rev-list", "--left-right", "--count", &range])
        else {
            return (0, 0);
        };
        let mut parts = out.split_whitespace();
        let behind = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
        let ahead = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
        (ahead, behind)
    }

    fn run_git(&self, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        self.run_git_in(Some(&self.root), cfg, args)
    }

    fn run_git_allow_fail(&self, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        self.run_git_in(Some(&self.root), cfg, args)
    }

    fn run_git_in(&self, cwd: Option<&Path>, cfg: &GitConfig, args: &[&str]) -> Result<String> {
        let mut cmd = Command::new("git");
        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }
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
                "ssh -i {} -o IdentitiesOnly=yes -o BatchMode=yes",
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

        let output = cmd
            .output()
            .with_context(|| format!("failed to execute git {}", args.join(" ")))?;
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
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
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

pub fn write_file_atomic_replace(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let stem = path.file_name().and_then(|n| n.to_str()).unwrap_or("sheet");
    let pid = std::process::id();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let seq = TEMP_SEQ.fetch_add(1, Ordering::Relaxed);
    let tmp = parent.join(format!(".{stem}.mpmb-tmp-{pid}-{nanos}-{seq}"));
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
    if let Err(err) = fs::rename(&tmp, path) {
        let _ = fs::remove_file(&tmp);
        return Err(err).with_context(|| format!("failed replacing {}", path.display()));
    }
    if let Ok(dir) = fs::File::open(parent) {
        let _ = dir.sync_all();
    }
    Ok(())
}

fn collect_pdfs(root: &Path, dir: &Path, out: &mut Vec<SheetEntry>) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.starts_with('.') {
            continue;
        }
        let path = entry.path();
        let ty = entry.file_type()?;
        if ty.is_dir() {
            collect_pdfs(root, &path, out)?;
        } else if ty.is_file() && name_str.to_ascii_lowercase().ends_with(".pdf") {
            out.push(sheet_entry_from_path(root, &path)?);
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
        let name_str = name.to_string_lossy();
        if name_str.starts_with('.') || name_str.contains(".mpmb-tmp-") {
            continue;
        }
        let path = entry.path();
        let ty = entry.file_type()?;
        if ty.is_dir() {
            collect_stageable_paths(root, &path, out)?;
        } else if ty.is_file() {
            let lower = name_str.to_ascii_lowercase();
            if lower.ends_with(".pdf") || lower.ends_with(".state.json") {
                if let Ok(rel) = path.strip_prefix(root) {
                    out.push(rel.to_string_lossy().replace('\\', "/"));
                }
            }
        }
    }
    Ok(())
}

fn sheet_entry_from_path(root: &Path, abs: &Path) -> Result<SheetEntry> {
    let rel = abs
        .strip_prefix(root)
        .unwrap_or(abs)
        .to_string_lossy()
        .replace('\\', "/");
    let name = abs
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| rel.clone());
    let meta = fs::metadata(abs)?;
    let bytes = fs::read(abs)?;
    let modified_unix = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let sidecar_path = SheetStore::sidecar_path_for(abs);
    let sidecar_json = if sidecar_path.is_file() {
        fs::read(&sidecar_path)
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
    } else {
        None
    };
    let str_opt = |v: &Value| {
        v.as_str()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
    };
    Ok(SheetEntry {
        path: rel,
        name,
        size_bytes: meta.len(),
        sha256: sha256_hex(&bytes),
        modified_unix,
        has_state_sidecar: sidecar_path.is_file(),
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
        if let Some(at) = rest.find('@') {
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

    fn init_bare_remote(path: &Path) {
        let status = Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(path)
            .status()
            .unwrap();
        assert!(status.success(), "git init --bare failed");
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

        let (norm, abs) = store.resolve_safe_pdf_path("campaign/Ashnar.pdf").unwrap();
        assert_eq!(norm, "campaign/Ashnar.pdf");
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

        let v1 = b"%PDF-1.7\n%v1\n";
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
        let v1 = b"%PDF-1.7\n%initial\n";
        store_a
            .upload_sheet("campaign/hero.pdf", v1, false)
            .unwrap();
        store_a
            .save_sheet_atomic(
                "campaign/hero.pdf",
                v1,
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
        let refs_out = Command::new("git")
            .current_dir(&bare)
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
        let v1 = b"%PDF-1.7\n%v1\n";
        let up = store.upload_sheet("hero.pdf", v1, false).unwrap();

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
        let bytes = b"%PDF-1.7\n%unicode-special\n";
        store.upload_sheet(tricky, bytes, false).unwrap();
        store
            .save_sheet_atomic(
                tricky,
                bytes,
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
            .upload_sheet("s.pdf", b"%PDF-1.7\n%0\n", false)
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

        let b1_pdf = Command::new("git")
            .current_dir(&bare)
            .args(["show", &format!("{b1}:s.pdf")])
            .output()
            .unwrap();
        let b2_pdf = Command::new("git")
            .current_dir(&bare)
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
            .upload_sheet("s.pdf", b"%PDF-1.7\n%v0\n", false)
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
            .upload_sheet("shared.pdf", b"%PDF-1.7\n%init\n", false)
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
                        let _ = st
                            .save_sheet_atomic(
                                "shared.pdf",
                                payload.as_bytes(),
                                Some("intentionally-stale-sha"),
                                Some(&sidecar),
                                false,
                            )
                            .unwrap();
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
}
