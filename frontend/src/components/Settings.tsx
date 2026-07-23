import { useState, useEffect } from "react";
import type { Vendor } from "../api";
import { listVendors, testConnection, fetchVendorModels } from "../api";

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
	const [testStatus, setTestStatus] = useState<
		"idle" | "testing" | "ok" | "error"
	>("idle");
	const [testMsg, setTestMsg] = useState("");
	const [liveModels, setLiveModels] = useState<string[] | null>(null);
	const [fetchingModels, setFetchingModels] = useState(false);
	const [serverRunning, setServerRunning] = useState(false);

    useEffect(() => {
    	listVendors()
    		.then((v) => { setVendors(v); setServerRunning(true); })
    		.catch(() => setServerRunning(false));
    
    	const interval = setInterval(async () => {
    		try {
    			await listVendors();
    			setServerRunning(true);
    		} catch {
    			setServerRunning(false);
    		}
    	}, 10000);
    	return () => clearInterval(interval);
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
		if (v) onModelChange(v.default_model);
		setTestStatus("idle");
		setLiveModels(null);
	};

	const handleTest = async () => {
		if (!apiKey && currentVendor?.requires_api_key !== false) return;
		setTestStatus("testing");
		setTestMsg("");
		try {
			const result = await testConnection(vendor, apiKey, model);
			if (result.status === "ok") {
				setTestStatus("ok");
				setTestMsg(result.reply || "Connected!");
				// Fetch live models sau khi test OK
				setFetchingModels(true);
				try {
					const models = await fetchVendorModels(vendor, apiKey);
					if (models.length > 0) setLiveModels(models);
				} catch (e) {
					console.error("Failed to fetch models", e);
				}
				setFetchingModels(false);
			} else {
				setTestStatus("error");
				setTestMsg(result.detail || "Connection failed");
			}
		} catch (e) {
			setTestStatus("error");
			setTestMsg(String(e));
		}
	};

	const currentVendor = vendors.find((v) => v.id === vendor);

	const statusLabels: Record<string, { color: string; text: string }> = {
		testing: { color: "#58a6ff", text: "⏳ Testing..." },
		ok: { color: "#3fb950", text: `✅ ${testMsg}` },
		error: { color: "#f85149", text: `❌ ${testMsg}` },
	};

	return (
		<div className="settings">
			<h2>⚙️ Settings</h2>

			<div className="setting-group">
				<label htmlFor="vendor">AI Provider</label>
				<select
					id="vendor"
					value={vendor}
					onChange={(e) => handleVendorChange(e.target.value)}
				>
					{vendors.map((v) => (
						<option key={v.id} value={v.id}>
							{v.name}
						</option>
					))}
				</select>
				{currentVendor && !currentVendor.requires_api_key && (
					<p className="hint" style={{ color: "#3fb950" }}>
						✅ No API key needed (local model).
					</p>
				)}
			</div>

			<div className="setting-group">
				<label htmlFor="api-key">
					API Key{currentVendor?.docs_url ? " " : ""}
				</label>
				{currentVendor?.docs_url && (
					<a
						href={currentVendor.docs_url}
						target="_blank"
						rel="noopener noreferrer"
						className="hint"
					>
						get key ↗
					</a>
				)}
				<div className="api-key-row">
					<input
						id="api-key"
						type="password"
						placeholder={
							currentVendor?.requires_api_key ? "sk-..." : "(not needed)"
						}
						value={apiKey}
						onChange={(e) => {
							onApiKeyChange(e.target.value);
							setTestStatus("idle");
						}}
						disabled={!currentVendor?.requires_api_key}
					/>
					<button
						onClick={handleTest}
						disabled={
							testStatus === "testing" ||
							(!apiKey && currentVendor?.requires_api_key !== false)
						}
						className="btn-test"
					>
						Test & Save
					</button>
				</div>
				{testStatus !== "idle" && (
					<p
						className="hint"
						style={{
							color: statusLabels[testStatus]?.color || "#8b949e",
							marginTop: 6,
						}}
					>
						{statusLabels[testStatus]?.text}
					</p>
				)}
				<p className="hint">
					Stored in localStorage. Can also use <code>OPENAI_API_KEY</code> env
					var.
				</p>
			</div>

			<div className="setting-group">
				<label htmlFor="model">
					Model {fetchingModels && <span className="hint">(fetching...)</span>}
				</label>
				<select
					id="model"
					value={model}
					onChange={(e) => onModelChange(e.target.value)}
				>
					{(liveModels || currentVendor?.models || []).map((m) => (
						<option key={m} value={m}>
							{m}
						</option>
					))}
				</select>
				{liveModels && liveModels.length > 0 && (
					<p className="hint" style={{ color: "#3fb950" }}>
						✅ {liveModels.length} models loaded from API
					</p>
				)}
			</div>

			<div className="setting-group">
				<label>API Base URL</label>
				<input type="text" value={currentVendor?.base_url || ""} disabled />
				<p className="hint">
					{currentVendor?.id === "ollama"
						? "Start Ollama locally, then backend auto-connects."
						: `Using ${currentVendor?.name || "selected"} API endpoint.`}
				</p>
			</div>

			<div className="setting-group">
				<h3>Server Status</h3>
				<p style={{
					color: serverRunning ? "#3fb950" : "#f85149",
					fontSize: 14,
					fontWeight: 600,
				}}>
					{serverRunning ? "🟢 RUNNING" : "🔴 STOPPED"}
				</p>
			</div>
		</div>
	);
}
