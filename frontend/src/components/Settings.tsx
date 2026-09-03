import { useEffect, useState } from "react";
import type { Vendor } from "../api";
import { fetchVendorModels, listVendors, testConnection } from "../api";

interface SettingsProps {
	apiKey: string;
	model: string;
	vendor: string;
	baseUrl: string;
	onApiKeyChange: (key: string) => void;
	onModelChange: (model: string) => void;
	onVendorChange: (vendor: string) => void;
	onBaseUrlChange: (baseUrl: string) => void;
}

export function Settings({
	apiKey,
	model,
	vendor,
	baseUrl,
	onApiKeyChange,
	onModelChange,
	onVendorChange,
	onBaseUrlChange,
}: SettingsProps) {
	const [vendors, setVendors] = useState<Vendor[]>([]);
	const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
	const [testMsg, setTestMsg] = useState("");
	const [liveModels, setLiveModels] = useState<string[]>([]);
	const [fetchingModels, setFetchingModels] = useState(false);
	const [modelError, setModelError] = useState("");
	const [serverRunning, setServerRunning] = useState(false);

	useEffect(() => {
		let cancelled = false;
		const probe = async () => {
			try {
				const result = await listVendors();
				if (!cancelled) {
					setVendors(result);
					setServerRunning(true);
				}
			} catch {
				if (!cancelled) setServerRunning(false);
			}
		};
		void probe();
		const interval = window.setInterval(() => void probe(), 10000);
		return () => {
			cancelled = true;
			window.clearInterval(interval);
		};
	}, []);

	const currentVendor = vendors.find((item) => item.id === vendor);
	const requiresApiKey = currentVendor?.requires_api_key !== false;

	useEffect(() => {
		if (currentVendor && !baseUrl) onBaseUrlChange(currentVendor.base_url);
	}, [currentVendor, baseUrl, onBaseUrlChange]);

	const invalidateModels = () => {
		setLiveModels([]);
		setModelError("");
		onModelChange("");
		setTestStatus("idle");
		setTestMsg("");
	};

	const handleVendorChange = (newVendor: string) => {
		onVendorChange(newVendor);
		invalidateModels();
	};

	const handleBaseUrlChange = (value: string) => {
		onBaseUrlChange(value);
		invalidateModels();
	};

	const handleRefreshModels = async () => {
		if (!baseUrl.trim()) {
			setModelError("Enter the provider API base URL first.");
			return;
		}
		if (requiresApiKey && !apiKey) {
			setModelError("Enter the provider API key first.");
			return;
		}

		setFetchingModels(true);
		setModelError("");
		try {
			const models = await fetchVendorModels(vendor, apiKey, baseUrl.trim());
			if (models.length === 0) {
				setLiveModels([]);
				onModelChange("");
				setModelError("Provider returned no models.");
				return;
			}
			setLiveModels(models);
			if (!models.includes(model)) onModelChange(models[0]);
		} catch (error) {
			setLiveModels([]);
			onModelChange("");
			setModelError(error instanceof Error ? error.message : String(error));
		} finally {
			setFetchingModels(false);
		}
	};

	const handleTest = async () => {
		if (!baseUrl.trim()) return;
		if (!model) {
			setTestStatus("error");
			setTestMsg("Refresh the provider model list and select a model first.");
			return;
		}
		if (requiresApiKey && !apiKey) return;

		setTestStatus("testing");
		setTestMsg("");
		try {
			const result = await testConnection(vendor, apiKey, model, baseUrl.trim());
			if (result.status !== "ok") {
				setTestStatus("error");
				setTestMsg(result.detail || "Connection failed");
				return;
			}
			setTestStatus("ok");
			setTestMsg(result.reply || "Connection verified");
		} catch (error) {
			setTestStatus("error");
			setTestMsg(error instanceof Error ? error.message : String(error));
		}
	};

	return (
		<div className="settings">
			<div className="workspace-intro compact-intro settings-intro">
				<div>
					<span className="section-index">SYS / RUNTIME</span>
					<strong>Model runtime</strong>
					<p>Provider endpoint, live model discovery and session credentials for the local translation gateway.</p>
				</div>
				<div className={`backend-readout ${serverRunning ? "online" : "offline"}`}>
					<span>Backend</span>
					<strong>{serverRunning ? "Online" : "Offline"}</strong>
				</div>
			</div>

			<div className="section-bar">
				<div><span className="section-index">01</span><strong>Provider</strong></div>
				<span>Model lists are fetched directly from the configured provider endpoint.</span>
			</div>

			<div className="settings-grid">
				<div className="setting-group">
					<label htmlFor="vendor">AI provider</label>
					<select id="vendor" value={vendor} onChange={(event) => handleVendorChange(event.target.value)}>
						{vendors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
					</select>
					{currentVendor?.requires_api_key === false && (
						<p className="hint">This provider does not require an API key.</p>
					)}
				</div>

				<div className="setting-group">
					<label htmlFor="base-url">API base URL</label>
					<input
						id="base-url"
						type="text"
						value={baseUrl}
						onChange={(event) => handleBaseUrlChange(event.target.value)}
						placeholder={currentVendor?.base_url || "https://provider.example/v1"}
					/>
					<p className="hint">Editable for every provider. Example Ollama: http://192.168.1.171:11434</p>
				</div>

				<div className="setting-group">
					<label htmlFor="api-key">API key</label>
					{currentVendor?.docs_url && (
						<a href={currentVendor.docs_url} target="_blank" rel="noreferrer" className="hint">Provider key documentation</a>
					)}
					<input
						id="api-key"
						type="password"
						autoComplete="off"
						placeholder={requiresApiKey ? "Enter key for this session" : "Not required"}
						value={apiKey}
						onChange={(event) => {
							onApiKeyChange(event.target.value);
							invalidateModels();
						}}
						disabled={!requiresApiKey}
					/>
					<p className="hint">Credentials are kept in memory for the current app session only.</p>
				</div>

				<div className="setting-group">
					<label htmlFor="model">Provider models</label>
					<div className="api-key-row">
						<select
							id="model"
							value={model}
							onChange={(event) => onModelChange(event.target.value)}
							disabled={liveModels.length === 0}
						>
							{liveModels.length === 0 && <option value="">Refresh models from provider</option>}
							{liveModels.map((item) => <option key={item} value={item}>{item}</option>)}
						</select>
						<button
							className="btn-test"
							onClick={() => void handleRefreshModels()}
							disabled={fetchingModels || !baseUrl.trim() || (requiresApiKey && !apiKey)}
						>
							{fetchingModels ? "Refreshing…" : "Refresh models"}
						</button>
					</div>
					{liveModels.length > 0 && <p className="hint">{liveModels.length} models loaded directly from provider.</p>}
					{modelError && <p className="hint connection-status error">{modelError}</p>}
				</div>

				<div className="setting-group">
					<label>Connection</label>
					<button
						className="btn-test"
						onClick={() => void handleTest()}
						disabled={testStatus === "testing" || !baseUrl.trim() || !model || (requiresApiKey && !apiKey)}
					>
						{testStatus === "testing" ? "Testing…" : "Test connection"}
					</button>
					{testStatus !== "idle" && (
						<p className={`hint connection-status ${testStatus}`}>{testMsg}</p>
					)}
				</div>

				<div className="setting-group runtime-detail">
					<label>Backend status</label>
					<p className={`server-state ${serverRunning ? "online" : "offline"}`}>
						{serverRunning ? "Running / API reachable" : "Unavailable / API not reachable"}
					</p>
				</div>
			</div>
		</div>
	);
}
