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

const WORKSPACES: Array<{ id: Workspace; label: string; bookScoped: boolean }> = [
	{ id: "library", label: "Library", bookScoped: false },
	{ id: "translate", label: "Translate", bookScoped: true },
	{ id: "reader", label: "Inspect", bookScoped: true },
	{ id: "glossary", label: "Glossary", bookScoped: true },
	{ id: "export", label: "Export", bookScoped: true },
	{ id: "settings", label: "Settings", bookScoped: false },
];

function App() {
	const [activeWorkspace, setActiveWorkspace] = useState<Workspace>("library");
	const [selectedBook, setSelectedBook] = useState<Book | null>(null);
	const [apiKey, setApiKey] = useState("");
	const [model, setModel] = useState(
		() => localStorage.getItem("et_model") || "gpt-4o-mini",
	);
	const [vendor, setVendor] = useState(
		() => localStorage.getItem("et_vendor") || "openai",
	);

	useEffect(() => {
		// Remove credentials persisted by older builds. Keys are session-memory only now.
		localStorage.removeItem("et_api_key");
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
		localStorage.setItem("et_model", value);
	};

	const handleVendorChange = (value: string) => {
		setVendor(value);
		localStorage.setItem("et_vendor", value);
	};

	const canOpen = (workspace: Workspace) => {
		const item = WORKSPACES.find((candidate) => candidate.id === workspace);
		return !item?.bookScoped || selectedBook !== null;
	};

	return (
		<div className="workbench-shell">
			<aside className="workbench-rail">
				<div className="brand-block">
					<div className="brand-mark">ET</div>
					<div>
						<strong>Ebook Translator</strong>
						<span>Translation Workbench</span>
					</div>
				</div>

				<nav className="workspace-nav" aria-label="Workspace navigation">
					{WORKSPACES.map((item) => (
						<button
							key={item.id}
							className={activeWorkspace === item.id ? "active" : ""}
							disabled={!canOpen(item.id)}
							onClick={() => setActiveWorkspace(item.id)}
						>
							<span>{item.label}</span>
							{item.bookScoped && <small>Book</small>}
						</button>
					))}
				</nav>

				<div className="provider-summary">
					<span>Provider</span>
					<strong>{vendor}</strong>
					<code>{model || "default model"}</code>
				</div>
			</aside>

			<section className="workbench-stage">
				<header className="stage-header">
					<div>
						<span className="eyebrow">Active workspace</span>
						<h1>{WORKSPACES.find((item) => item.id === activeWorkspace)?.label}</h1>
					</div>
					{selectedBook && (
						<div className="active-book-chip">
							<span>Active book</span>
							<strong>{selectedBook.title || "Untitled"}</strong>
						</div>
					)}
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
							onApiKeyChange={handleApiKeyChange}
							onModelChange={handleModelChange}
							onVendorChange={handleVendorChange}
						/>
					)}
				</main>
			</section>

			<aside className="inspector-pane">
				<div className="inspector-heading">
					<span className="eyebrow">Inspector</span>
					<strong>{selectedBook ? "Book context" : "No active book"}</strong>
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
						<section className="inspector-grid">
							<div>
								<label>Status</label>
								<strong className={`status-text ${selectedBook.status}`}>
									{selectedBook.status}
								</strong>
							</div>
							<div>
								<label>Progress</label>
								<strong className="mono-value">
									{selectedBook.done_chunks}/{selectedBook.total_chunks}
								</strong>
							</div>
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
					<p className="muted">Select a book in Library to unlock the translation workflow.</p>
				)}
			</aside>
		</div>
	);
}

export default App;
