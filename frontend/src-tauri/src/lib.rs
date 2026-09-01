use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct SidecarState(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      let sidecar = app.shell().sidecar("ebook-translator-backend")?;
      let (_events, child) = sidecar.spawn()?;
      app.manage(SidecarState(Mutex::new(Some(child))));
      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building Ebook Translator")
    .run(|app_handle, event| {
      if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
        if let Some(state) = app_handle.try_state::<SidecarState>() {
          if let Ok(mut child) = state.0.lock() {
            if let Some(child) = child.take() {
              let _ = child.kill();
            }
          }
        }
      }
    });
}
