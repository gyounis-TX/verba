mod commands;

use commands::{get_sidecar_port, kill_sidecar, SidecarState};
use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .manage(Mutex::new(SidecarState { port: None }))
        .invoke_handler(tauri::generate_handler![get_sidecar_port, kill_sidecar])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // Use Tauri's sidecar mechanism to spawn the bundled binary.
            // This resolves the binary path relative to the app bundle
            // (works on macOS .app, Windows .msi, and during development).
            let sidecar_command = app
                .shell()
                .sidecar("sidecar")
                .expect("Failed to create sidecar command");

            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("Failed to spawn sidecar");

            // Read stdout/stderr events to capture the PORT line
            std::thread::spawn({
                let handle = app_handle.clone();
                move || {
                    use tauri_plugin_shell::process::CommandEvent;
                    while let Some(event) = rx.blocking_recv() {
                        match event {
                            CommandEvent::Stdout(line) => {
                                let line = String::from_utf8_lossy(&line);
                                let line = line.trim();
                                eprintln!("[sidecar stdout] {}", line);
                                if let Some(port_str) = line.strip_prefix("PORT:") {
                                    if let Ok(port) = port_str.parse::<u16>() {
                                        let state =
                                            handle.state::<Mutex<SidecarState>>();
                                        let mut state = state.lock().unwrap();
                                        state.port = Some(port);
                                        eprintln!("Sidecar started on port {}", port);
                                    }
                                }
                            }
                            CommandEvent::Stderr(line) => {
                                let line = String::from_utf8_lossy(&line);
                                eprintln!("[sidecar stderr] {}", line.trim());
                            }
                            CommandEvent::Terminated(status) => {
                                eprintln!("Sidecar terminated: {:?}", status);
                                break;
                            }
                            _ => {}
                        }
                    }
                }
            });

            // Store the shell child handle for cleanup on exit
            app_handle.manage(Mutex::new(Some(child)));

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            let state = app_handle.try_state::<
                Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
            >();
            if let Some(state) = state {
                let mut guard = match state.lock() {
                    Ok(g) => g,
                    Err(_) => return,
                };
                if let Some(child) = guard.take() {
                    let _ = child.kill();
                    eprintln!("Sidecar process killed");
                }
            }
        }
    });
}
