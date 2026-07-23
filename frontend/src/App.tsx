import { useState } from "react";
import "./App.css";
import { Library } from "./components/Library";
import { TranslateView } from "./components/TranslateView";
import { GlossaryEditor } from "./components/GlossaryEditor";
import { Settings } from "./components/Settings";
import type { Book } from "./api";

type Tab = "library" | "translate" | "glossary" | "settings";

function App() {
	const [activeTab, setActiveTab] = useState<Tab>("library");
	const [selectedBook, setSelectedBook] = useState<Book | null>(null);
	const [apiKey, setApiKey] = useState(
		() => localStorage.getItem("et_api_key") || "",
	);
	const [model, setModel] = useState(
		() => localStorage.getItem("et_model") || "gpt-4o-mini",
	);
	const [vendor, setVendor] = useState(
		() => localStorage.getItem("et_vendor") || "openai",
	);

	const handleSelectBook = (book: Book) => {
		setSelectedBook(book);
		setActiveTab("translate");
	};

	const handleApiKeyChange = (key: string) => {
		setApiKey(key);
		localStorage.setItem("et_api_key", key);
	};

	const handleModelChange = (m: string) => {
		setModel(m);
		localStorage.setItem("et_model", m);
	};

	const handleVendorChange = (v: string) => {
		setVendor(v);
		localStorage.setItem("et_vendor", v);
	};

	return (
		<div className="app">
			<nav className="sidebar">
				<h1 className="logo">📖 ET</h1>
				<div className="nav-tabs">
					<button
						className={`nav-btn ${activeTab === "library" ? "active" : ""}`}
						onClick={() => setActiveTab("library")}
					>
						📚 Library
					</button>
					<button
						className={`nav-btn ${activeTab === "translate" ? "active" : ""}`}
						onClick={() => setActiveTab("translate")}
					>
						🌐 Translate
					</button>
					<button
						className={`nav-btn ${activeTab === "glossary" ? "active" : ""}`}
						onClick={() => setActiveTab("glossary")}
					>
						📝 Glossary
					</button>
					<button
						className={`nav-btn ${activeTab === "settings" ? "active" : ""}`}
						onClick={() => setActiveTab("settings")}
					>
						⚙️ Settings
					</button>
				</div>
			</nav>

			<main className="content">
				{activeTab === "library" && (
					<Library
						onSelectBook={handleSelectBook}
						selectedBook={selectedBook}
						onRefresh={() => {}}
					/>
				)}
				{activeTab === "translate" && (
					<TranslateView book={selectedBook} apiKey={apiKey} model={model} vendor={vendor} />
				)}
				{activeTab === "glossary" && (
					<GlossaryEditor bookId={selectedBook?.id ?? null} />
				)}
				{activeTab === "settings" && (
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
		</div>
	);
}

export default App;
