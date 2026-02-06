use std::sync::Mutex;
use tauri::State;

pub struct SidecarState {
    pub port: Option<u16>,
}

#[tauri::command]
pub fn get_sidecar_port(state: State<'_, Mutex<SidecarState>>) -> Result<u16, String> {
    let state = state.lock().map_err(|e| e.to_string())?;
    state.port.ok_or_else(|| "Sidecar not ready".to_string())
}

#[tauri::command]
pub fn kill_sidecar(
    child_state: State<'_, Mutex<Option<tauri_plugin_shell::process::CommandChild>>>,
) -> Result<(), String> {
    let mut guard = child_state.lock().map_err(|e| e.to_string())?;
    if let Some(child) = guard.take() {
        child.kill().map_err(|e| e.to_string())?;
        eprintln!("Sidecar killed for update");
    }
    Ok(())
}
