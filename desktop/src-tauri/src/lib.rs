//! Desktop shell. Responsibilities are deliberately small:
//!   1. start the Python sidecar on a random loopback port,
//!   2. mint a per-launch API token and hand it to the sidecar (stdin) and the UI (IPC),
//!   3. open the native file picker and return the chosen statement's text.
//! The webview never receives filesystem or shell access.

use std::fs::File;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_dialog::DialogExt;

const MAX_STATEMENT_BYTES: u64 = 10 * 1024 * 1024;

struct Backend {
    port: u16,
    token: String,
    child: Mutex<Option<Child>>,
}

#[derive(Serialize)]
struct BackendInfo {
    base_url: String,
    token: String,
}

#[derive(Serialize)]
struct StatementFile {
    name: String,
    content: String,
}

/// Returns the sidecar address and token once the sidecar is accepting connections, so
/// the UI's first request cannot race its startup.
#[tauri::command]
async fn get_backend_info(state: State<'_, Backend>) -> Result<BackendInfo, String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], state.port));
    let deadline = Instant::now() + Duration::from_secs(90);
    loop {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok() {
            break;
        }
        if Instant::now() >= deadline {
            return Err("The local engine did not start in time.".into());
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    Ok(BackendInfo {
        base_url: format!("http://127.0.0.1:{}", state.port),
        token: state.token.clone(),
    })
}

/// Debug builds only: lets the webview report client-side failures to the dev terminal.
/// Callers must pass diagnostics only (error names, status codes), never user data.
#[tauri::command]
fn debug_log(message: String) {
    #[cfg(debug_assertions)]
    eprintln!("LocalLedger webview: {}", message.chars().take(300).collect::<String>());
    #[cfg(not(debug_assertions))]
    let _ = message;
}

/// Opens the native macOS open panel. The path never crosses into JavaScript, so the
/// webview cannot ask for arbitrary files.
#[tauri::command]
async fn pick_statement_file(app: tauri::AppHandle) -> Result<Option<StatementFile>, String> {
    let picked = app
        .dialog()
        .file()
        .set_title("Import bank statement")
        .add_filter("Statements", &["csv", "tsv", "txt"])
        .blocking_pick_file();
    let Some(picked) = picked else {
        return Ok(None);
    };
    let path = picked.into_path().map_err(|_| "Unsupported file location.".to_string())?;
    let meta = std::fs::metadata(&path).map_err(|_| "Could not read the file.".to_string())?;
    if meta.len() > MAX_STATEMENT_BYTES {
        return Err("File is larger than the 10 MB import limit.".into());
    }
    let bytes = std::fs::read(&path).map_err(|_| "Could not read the file.".to_string())?;
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "statement.csv".into());
    Ok(Some(StatementFile {
        name,
        content: String::from_utf8_lossy(&bytes).into_owned(),
    }))
}

fn random_token() -> std::io::Result<String> {
    let mut bytes = [0u8; 32];
    File::open("/dev/urandom")?.read_exact(&mut bytes)?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind(("127.0.0.1", 0))?.local_addr()?.port())
}

fn backend_command() -> Command {
    if cfg!(debug_assertions) {
        // Development: run the backend from source with uv.
        let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend");
        let mut cmd = Command::new("uv");
        cmd.args(["run", "--project"])
            .arg(&backend_dir)
            .args(["python", "-m", "localledger"])
            .env("LOCALLEDGER_DEV", "1");
        cmd
    } else {
        // Release: the PyInstaller sidecar bundled next to the main executable.
        let exe = std::env::current_exe().expect("current executable path");
        Command::new(exe.with_file_name("localledger-backend"))
    }
}

fn spawn_backend(port: u16, token: &str) -> std::io::Result<Child> {
    let mut child = backend_command()
        .env("LOCALLEDGER_PORT", port.to_string())
        .env("LOCALLEDGER_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::piped())
        .spawn()?;
    // The token goes over stdin so it never shows up in `ps` output or the environment.
    if let Some(mut stdin) = child.stdin.take() {
        writeln!(stdin, "{token}")?;
    }
    Ok(child)
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let port = free_port()?;
            let token = random_token()?;
            let child = match spawn_backend(port, &token) {
                Ok(child) => Some(child),
                Err(err) => {
                    eprintln!("LocalLedger: could not start the local backend: {err}");
                    None
                }
            };
            app.manage(Backend { port, token, child: Mutex::new(child) });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_info, pick_statement_file, debug_log])
        .build(tauri::generate_context!())
        .expect("error while building LocalLedger");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut child) = handle.state::<Backend>().child.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
