import { useEffect, useState } from "react";
import "./App.css";
import { Library } from "./components/Library";
import { TranslateView } from "./components/TranslateView";
import { GlossaryEditor } from "./components/GlossaryEditor";
import { ExportTab } from "./components/ExportTab";
import { Settings } from "./components/Settings";
import { Reader } from "./components/Reader";
import type { Book } from "./api";

type Workspace =
	| "library"
	| "translate"
	| "reader"
	| "glossary"
	| "export"
	| "settings";

const WORKSPACES: Array<{
	id: Workspace;
	label: string;
	bookScoped: boolean;
	index: string;
	description: string;
}> = [
	{ id: "library", label: "Library", bookScoped: false, index: "01", description: "Sources" },
	{ id: "translate", label: "Translate", bookScoped: true, index: "02", description: "Run" },
	{ id: "reader", label: "Inspect", bookScoped: true, index: "03", description: "QA + edit" },
	{ id: "glossary", label: "Glossary", bookScoped: true, index: "04", description: "Terms" },
	{ id: "export", label: "Export", bookScoped: true, index: "05", description: "Deliver" },
	{ id: "settings", label: "Settings", bookScoped: false, index: "06", description: "Runtime" },
];

function App() {
	const [activeWorkspace, setActiveWorkspace] = useState<Workspace>("library");
	const [selectedBook, setSelectedBook] = useState<Book | null>(null);
	const [apiKey, setApiKey] = useState("");
	const [model, setModel] = useState("");
	const [vendor, setVendor] = useState(
		() => localStorage.getItem("et_vendor") || "openai",
	);
	const [baseUrl, setBaseUrl] = useState(() => {
		const initialVendor = localStorage.getItem("et_vendor") || "openai";
		return localStorage.getItem(`et_base_url_${initialVendor}`) || "";
	});

	useEffect(() => {
		// Remove legacy runtime selections. Credentials and model discovery are session-scoped.
		localStorage.removeItem("et_api_key");
		localStorage.removeItem("et_model");
	}, []);

	const handleSelectBook = (book: Book) => {
		setSelectedBook(book);
		setActiveWorkspace("translate");
	};

	const handleApiKeyChange = (key: string) => {
		setApiKey(key);
	};

	const handleModelChange = (value: string) => {
		setModel(value);
	};

	const handleVendorChange = (value: string) => {
		setVendor(value);
		localStorage.setItem("et_vendor", value);
		setBaseUrl(localStorage.getItem(`et_base_url_${value}`) || "");
	};

	const handleBaseUrlChange = (value: string) => {
		setBaseUrl(value);
		localStorage.setItem(`et_base_url_${vendor}`, value);
	};

	const canOpen = (workspace: Workspace) => {
		const item = WORKSPACES.find((candidate) => candidate.id === workspace);
		return !item?.bookScoped || selectedBook !== null;
	};

	const activeMeta = WORKSPACES.find((item) => item.id === activeWorkspace);
	const progressPercent = selectedBook && selectedBook.total_chunks > 0
		? Math.round((selectedBook.done_chunks / selectedBook.total_chunks) * 100)
		: 0;

	return (
		<div className="workbench-shell">
			<aside className="workbench-rail">
				<div className="brand-block">
					<div className="brand-mark">ET</div>
					<div>
						<strong>Ebook Translator</strong>
						<span>Local translation workbench</span>
					</div>
				</div>
				<div className="rail-rule" />

				<nav className="workspace-nav" aria-label="Workspace navigation">
					{WORKSPACES.map((item) => (
						<button
							key={item.id}
							className={activeWorkspace === item.id ? "active" : ""}
							disabled={!canOpen(item.id)}
							onClick={() => setActiveWorkspace(item.id)}
						>
							<span className="nav-index">{item.index}</span>
							<span className="nav-copy">
								<strong>{item.label}</strong>
								<small>{item.description}</small>
							</span>
						</button>
					))}
				</nav>

				<div className="provider-summary">
					<div className="provider-kicker">
						<span className="status-dot" />
						<span>Runtime</span>
					</div>
					<strong>{vendor}</strong>
					<code>{model || "default model"}</code>
				</div>
			</aside>

			<section className="workbench-stage">
				<header className="stage-header">
					<div className="stage-heading-group">
						<span className="workspace-index">{activeMeta?.index}</span>
						<div>
							<span className="eyebrow">Workspace / {activeMeta?.description}</span>
							<h1>{activeMeta?.label}</h1>
						</div>
					</div>
					<div className="stage-context">
						<div className="runtime-pill">
							<span>{vendor}</span>
							<strong>{model || "default"}</strong>
						</div>
						{selectedBook && (
							<div className="active-book-chip">
								<span>Active document</span>
								<strong>{selectedBook.title || "Untitled"}</strong>
							</div>
						)}
					</div>
				</header>

				<main className="stage-content">
					{activeWorkspace === "library" && (
						<Library
							onSelectBook={handleSelectBook}
							selectedBook={selectedBook}
							onRefresh={() => {}}
						/>
					)}
					{activeWorkspace === "translate" && (
						<TranslateView
							book={selectedBook}
							apiKey={apiKey}
							model={model}
							vendor={vendor}
							baseUrl={baseUrl}
						/>
					)}
					{activeWorkspace === "reader" && (
						<Reader bookId={selectedBook?.id ?? null} />
					)}
					{activeWorkspace === "glossary" && (
						<GlossaryEditor bookId={selectedBook?.id ?? null} />
					)}
					{activeWorkspace === "export" && (
						<ExportTab selectedBook={selectedBook} />
					)}
					{activeWorkspace === "settings" && (
						<Settings
							apiKey={apiKey}
							model={model}
							vendor={vendor}
							baseUrl={baseUrl}
							onApiKeyChange={handleApiKeyChange}
							onModelChange={handleModelChange}
							onVendorChange={handleVendorChange}
							onBaseUrlChange={handleBaseUrlChange}
						/>
					)}
				</main>
			</section>

			<aside className="inspector-pane">
				<div className="inspector-heading">
					<span className="eyebrow">Inspector</span>
					<strong>{selectedBook ? "Document context" : "No active document"}</strong>
				</div>
				{selectedBook ? (
					<div className="inspector-sections">
						<section>
							<label>Title</label>
							<p>{selectedBook.title || "Untitled"}</p>
						</section>
						{selectedBook.localized_title && (
							<section>
								<label>Localized title</label>
								<p>{selectedBook.localized_title}</p>
							</section>
						)}
						<section>
							<label>Author</label>
							<p>{selectedBook.author || "Unknown"}</p>
						</section>
						<section>
							<div className="inspector-grid inspector-metrics">
								<div>
									<label>Status</label>
									<strong className={`status-text ${selectedBook.status}`}>
										{selectedBook.status}
									</strong>
								</div>
								<div>
									<label>Progress</label>
									<strong className="mono-value">{progressPercent}%</strong>
								</div>
							</div>
							<div className="inspector-progress-track">
								<div className="inspector-progress-fill" style={{ width: `${progressPercent}%` }} />
							</div>
							<p className="inspector-progress-copy mono-value">
								{selectedBook.done_chunks} complete / {selectedBook.total_chunks} chunks
							</p>
						</section>
						<section>
							<label>Language</label>
							<p className="mono-value">
								{selectedBook.source_lang} → {selectedBook.target_lang}
							</p>
						</section>
						<section>
							<label>Category</label>
							<p>{selectedBook.category || "general"}</p>
						</section>
					</div>
				) : (
					<div className="inspector-empty">
						<span className="empty-rule" />
						<p className="muted">Open a document from Library to unlock translation, inspection and export tools.</p>
					</div>
				)}
			</aside>
		</div>
	);
}

export default App;
