import { useState, useEffect } from 'react';
import type { Vendor } from '../api';
import { listVendors } from '../api';

interface SettingsProps {
  apiKey: string;
  model: string;
  vendor: string;
  onApiKeyChange: (key: string) => void;
  onModelChange: (model: string) => void;
  onVendorChange: (vendor: string) => void;
}

export function Settings({
  apiKey, model, vendor,
  onApiKeyChange, onModelChange, onVendorChange,
}: SettingsProps) {
  const [vendors, setVendors] = useState<Vendor[]>([]);

  useEffect(() => {
    listVendors().then(setVendors).catch(console.error);
  }, []);

  useEffect(() => {
    const v = vendors.find((v) => v.id === vendor);
    if (v && v.default_model && !model) {
      onModelChange(v.default_model);
    }
  }, [vendor, vendors]);

  const handleVendorChange = (newVendor: string) => {
    onVendorChange(newVendor);
    const v = vendors.find((v) => v.id === newVendor);
    if (v) {
      onModelChange(v.default_model);
    }
  };

  const currentVendor = vendors.find((v) => v.id === vendor);

  return (
    <div className="settings">
      <h2>⚙️ Settings</h2>

      <div className="setting-group">
        <label htmlFor="vendor">AI Provider</label>
        <select id="vendor" value={vendor} onChange={(e) => handleVendorChange(e.target.value)}>
          {vendors.map((v) => (
            <option key={v.id} value={v.id}>{v.name}</option>
          ))}
        </select>
        {currentVendor && !currentVendor.requires_api_key && (
          <p className="hint success">✅ No API key needed (local model).</p>
        )}
      </div>

      <div className="setting-group">
        <label htmlFor="api-key">API Key{currentVendor?.docs_url ? ' ' : ''}</label>
        {currentVendor?.docs_url && (
          <a href={currentVendor.docs_url} target="_blank" rel="noopener noreferrer" className="hint">
            get key ↗
          </a>
        )}
        <input
          id="api-key"
          type="password"
          placeholder={currentVendor?.requires_api_key ? 'sk-...' : '(not needed)'}
          value={apiKey}
          onChange={(e) => onApiKeyChange(e.target.value)}
          disabled={!currentVendor?.requires_api_key}
        />
        <p className="hint">
          Stored in localStorage. Can also use <code>OPENAI_API_KEY</code> env var.
        </p>
      </div>

      <div className="setting-group">
        <label htmlFor="model">Model</label>
        <select id="model" value={model} onChange={(e) => onModelChange(e.target.value)}>
          {currentVendor?.models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <div className="setting-group">
        <label>API Base URL</label>
        <input
          type="text"
          value={currentVendor?.base_url || ''}
          disabled
        />
        <p className="hint">
          {currentVendor?.id === 'ollama'
            ? 'Start Ollama locally, then backend auto-connects.'
            : `Using ${currentVendor?.name || 'selected'} API endpoint.`}
        </p>
      </div>

      <div className="setting-group">
        <h3>Server Status</h3>
        <p className="hint">
          Backend runs at <code>http://127.0.0.1:8080</code>.
          Start: <code>python -m ebook_translator.server</code>
        </p>
      </div>
    </div>
  );
}
