import { useEffect, useState } from "react";
import type { Vendor } from "../api";
import { fetchVendorModels, listVendors, testConnection } from "../api";

interface SettingsProps {
	apiKey: string;
	model: string;
	vendor: string;
	onApiKeyChange: (key: string) => void;
	onModelChange: (model: string) => void;
	onVendorChange: (vendor: string) => void;
}

export function Settings({
	apiKey,
	model,
	vendor,
	onApiKeyChange,
	onModelChange,
	onVendorChange,
}: SettingsProps) {
	const [vendors, setVendors] = useState<Vendor[]>([]);
	const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
	const [testMsg, setTestMsg] = useState("");
	const [liveModels, setLiveModels] = useState<string[] | null>(null);
	const [fetchingModels, setFetchingModels] = useState(false);
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

	useEffect(() => {
		if (!currentVendor) return;
		if (!model || model === "gpt-4o-mini") onModelChange(currentVendor.default_model);
	}, [currentVendor, model, onModelChange]);

	useEffect(() => {
		if (!vendor) return;
		const stored = localStorage.getItem(`et_models_${vendor}`);
		setLiveModels(stored ? JSON.parse(stored) : null);
	}, [vendor]);

	const handleVendorChange = (newVendor: string) => {
		onVendorChange(newVendor);
		const next = vendors.find((item) => item.id === newVendor);
		if (next) onModelChange(next.default_model);
		setTestStatus("idle");
		setTestMsg("");
	};

	const handleTest = async () => {
		if (!apiKey && currentVendor?.requires_api_key !== false) return;
		setTestStatus("testing");
		setTestMsg("");
		try {
			const result = await testConnection(vendor, apiKey, model);
			if (result.status !== "ok") {
				setTestStatus("error");
				setTestMsg(result.detail || "Connection failed");
				return;
			}

			setTestStatus("ok");
			setTestMsg(result.reply || "Connection verified");
			setFetchingModels(true);
			try {
				const models = await fetchVendorModels(vendor, apiKey);
				if (models.length > 0) {
					setLiveModels(models);
					localStorage.setItem(`et_models_${vendor}`, JSON.stringify(models));
				}
			} finally {
				setFetchingModels(false);
			}
		} catch (error) {
			setTestStatus("error");
			setTestMsg(error instanceof Error ? error.message : String(error));
		}
	};

	const models = liveModels || currentVendor?.models || [];

	return (
		<div className="settings">
			<div className="workspace-intro compact-intro settings-intro">
				<div>
					<span className="section-index">SYS / RUNTIME</span>
					<strong>Model runtime</strong>
					<p>Provider, model and session credentials for the local translation gateway.</p>
				</div>
				<div className={`backend-readout ${serverRunning ? "online" : "offline"}`}>
					<span>Backend</span>
					<strong>{serverRunning ? "Online" : "Offline"}</strong>
				</div>
			</div>
			<div className="section-bar">
				<div><span className="section-index">01</span><strong>Provider</strong></div>
				<span>Credentials remain in memory for this app session only.</span>
			</div>
			<div className="settings-grid">
			<div className="setting-group">
				<label htmlFor="vendor">AI provider</label>
				<select id="vendor" value={vendor} onChange={(event) => handleVendorChange(event.target.value)}>
					{vendors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
				</select>
				{currentVendor?.requires_api_key === false && (
					<p className="hint">This provider is local and does not require an API key.</p>
				)}
			</div>

			<div className="setting-group">
				<label htmlFor="api-key">API key</label>
				{currentVendor?.docs_url && (
					<a href={currentVendor.docs_url} target="_blank" rel="noreferrer" className="hint">Provider key documentation</a>
				)}
				<div className="api-key-row">
					<input
						id="api-key"
						type="password"
						autoComplete="off"
						placeholder={currentVendor?.requires_api_key === false ? "Not required" : "Enter key for this session"}
						value={apiKey}
						onChange={(event) => {
							onApiKeyChange(event.target.value);
							setTestStatus("idle");
						}}
						disabled={currentVendor?.requires_api_key === false}
					/>
					<button
						className="btn-test"
						onClick={() => void handleTest()}
						disabled={testStatus === "testing" || (!apiKey && currentVendor?.requires_api_key !== false)}
					>
						{testStatus === "testing" ? "Testing…" : "Test connection"}
					</button>
				</div>
				{testStatus !== "idle" && (
					<p className={`hint connection-status ${testStatus}`}>{testMsg}</p>
				)}
				<p className="hint">Credentials are kept in memory for the current app session only.</p>
			</div>

			<div className="setting-group">
				<label htmlFor="model">Model {fetchingModels ? "· refreshing list" : ""}</label>
				<select id="model" value={model} onChange={(event) => onModelChange(event.target.value)}>
					{models.length === 0 && model && <option value={model}>{model}</option>}
					{models.map((item) => <option key={item} value={item}>{item}</option>)}
				</select>
				{liveModels && <p className="hint">{liveModels.length} models loaded from provider.</p>}
			</div>

			<div className="setting-group">
				<label>API base URL</label>
				<input type="text" value={currentVendor?.base_url || ""} disabled />
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
