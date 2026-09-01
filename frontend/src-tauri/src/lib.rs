use tauri_plugin_shell::ShellExt;

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
      let (_events, _child) = sidecar.spawn()?;
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running Ebook Translator");
}
