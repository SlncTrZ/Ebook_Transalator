interface SettingsProps {
  apiKey: string;
  model: string;
  onApiKeyChange: (key: string) => void;
  onModelChange: (model: string) => void;
}

const MODELS = [
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini (fast, cheap)' },
  { value: 'gpt-4o', label: 'GPT-4o (quality)' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku' },
  { value: 'claude-3-sonnet-20240229', label: 'Claude 3 Sonnet' },
];

export function Settings({
  apiKey,
  model,
  onApiKeyChange,
  onModelChange,
}: SettingsProps) {
  return (
    <div className="settings">
      <h2>⚙️ Settings</h2>

      <div className="setting-group">
        <label htmlFor="api-key">API Key</label>
        <input
          id="api-key"
          type="password"
          placeholder="sk-..."
          value={apiKey}
          onChange={(e) => onApiKeyChange(e.target.value)}
        />
        <p className="hint">
          Stored in localStorage. Never shared. Can also be set via{' '}
          <code>OPENAI_API_KEY</code> env var.
        </p>
      </div>

      <div className="setting-group">
        <label htmlFor="model">Model</label>
        <select id="model" value={model} onChange={(e) => onModelChange(e.target.value)}>
          {MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="setting-group">
        <label>API Base URL</label>
        <input
          type="text"
          defaultValue="https://api.openai.com/v1"
          disabled
        />
        <p className="hint">
          Custom base URL for OpenAI-compatible APIs (e.g., Ollama, vLLM).
          Coming soon.
        </p>
      </div>

      <div className="setting-group">
        <h3>Server Status</h3>
        <p className="hint">
          Backend runs at <code>http://127.0.0.1:8080</code>.
          Start it with: <code>python -m ebook_translator.server</code>
        </p>
      </div>
    </div>
  );
}
