import { useState, useRef, useCallback, useEffect } from "react";
import type { Book, ProgressData } from "../api";
import {
	startTranslate,
	cancelTranslate,
	translateProgress,
	exportBook,
} from "../api";
import { listCategories } from "../api";
import { MetadataReview } from "./MetadataReview";

interface TranslateViewProps {
	book: Book | null;
	apiKey: string;
	model: string;
	vendor: string;
}

export function TranslateView({
	book,
	apiKey,
	model,
	vendor,
}: TranslateViewProps) {
	const [running, setRunning] = useState(false);
	const [progress, setProgress] = useState<ProgressData | null>(null);
	const [category, setCategory] = useState("general");
	const [categories, setCategories] = useState<Record<string, string>>({});
	const [chapterStart, setChapterStart] = useState(1);
	const [chapterEnd, setChapterEnd] = useState(99999);
	const [exportPath, setExportPath] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [agentic, setAgentic] = useState(false);
	const [agentPhase, setAgentPhase] = useState("");
	const cancelRef = useRef<(() => void) | null>(null);

	useEffect(() => {
		listCategories().then(setCategories).catch(console.error);
	}, []);

	const handleStart = useCallback(async () => {
		if (!book || !apiKey) return;
		setRunning(true);
		setError(null);
		setExportPath(null);
		setProgress(null);

		try {
			const result = await startTranslate(
				book.file_path,
				vendor,
				apiKey,
				model,
				category,
				chapterStart,
				chapterEnd,
				agentic,
			);
			if (agentic) setAgentPhase("🤖 Researching...");
			const bookId = result.book_id;

			cancelRef.current = translateProgress(
				bookId,
				(data) => {
					setProgress(data);
					if (agentic) {
						if (data.done === 0 && data.total > 0)
							setAgentPhase("🔍 Researching...");
						else if (data.done > 0 && data.done < data.total)
							setAgentPhase("📝 Translating...");
						else if (data.done === data.total) setAgentPhase("✅ Complete");
					}
					if (data.status === "done" || data.status === "failed") {
						setRunning(false);
					}
				},
				() => setRunning(false),
				(err) => {
					setError(err);
					setRunning(false);
				},
			);
		} catch (e) {
			setError(String(e));
			setRunning(false);
		}
	}, [book, apiKey, model, category, vendor, chapterStart, chapterEnd, agentic]);

	const handleCancel = useCallback(async () => {
		if (cancelRef.current) cancelRef.current();
		await cancelTranslate();
		setRunning(false);
	}, []);

	const handleExport = useCallback(async () => {
		if (!book) return;
		try {
			const result = await exportBook(book.id);
			setExportPath(result.path);
		} catch (e) {
			setError(String(e));
		}
	}, [book]);

	if (!book) {
		return (
			<div className="translate-view">
				<h2>🌐 Translate</h2>
				<p className="muted">
					Select a book from the Library tab to start translating.
				</p>
			</div>
		);
	}

	return (
		<div className="translate-view">
			<h2>🌐 Translate</h2>

			<div className="book-info">
				<strong>{book.title || "Untitled"}</strong>
				{book.author && <span> by {book.author}</span>}
			</div>

			<MetadataReview
				book={book}
				apiKey={apiKey}
				model={model}
				vendor={vendor}
			/>

			<div className="controls">
				<label>
					From Chapter:
					<input
						type="number"
						min={1}
						defaultValue={1}
						style={{ width: 70, marginLeft: 4 }}
						onChange={(e) =>
							setChapterStart(Math.max(1, parseInt(e.target.value) || 1))
						}
					/>
				</label>
				<label>
					To Chapter:
					<input
						type="number"
						min={1}
						placeholder="999"
						style={{ width: 70, marginLeft: 4 }}
						onChange={(e) =>
							setChapterEnd(e.target.value ? parseInt(e.target.value) : 99999)
						}
					/>
				</label>
				<label>
					Category:
					<select
						value={category}
						onChange={(e) => setCategory(e.target.value)}
					>
						{Object.entries(categories).map(([key, label]) => (
							<option key={key} value={key}>
								{label}
							</option>
						))}
					</select>
				</label>
			</div>

			{error && <div className="error-banner">{error}</div>}

			{agentPhase && (
				<p
					className="hint"
					style={{ color: "#58a6ff", fontWeight: 600, marginTop: 8 }}
				>
					{agentPhase}
				</p>
			)}

			{progress && (
				<div className="progress-section">
					<div className="progress-bar-container">
						<div
							className="progress-bar-fill"
							style={{
								width:
									progress.total > 0
										? `${((progress.done + progress.failed) / progress.total) * 100}%`
										: "0%",
							}}
						/>
					</div>
					<p className="progress-text">
						{progress.done} done / {progress.failed} failed / {progress.total}{" "}
						total
					</p>
				</div>
			)}

			<div className="actions">
				{!running ? (
					<>
						<button
							className="btn-primary"
							onClick={handleStart}
							disabled={!apiKey}
							title={!apiKey ? "Set API key in Settings" : ""}
						>
							▶ {agentic ? "Agentic" : "Standard"} Translation
						</button>
						<button
							onClick={() => setAgentic(!agentic)}
							style={{
								background: agentic ? "#1f6feb" : "#21262d",
								borderColor: agentic ? "#58a6ff" : "#30363d",
							}}
						>
							{agentic ? "🤖 Agentic" : "📄 Standard"}
						</button>
					</>
				) : (
					<button className="btn-danger" onClick={handleCancel}>
						⏹ Cancel
					</button>
				)}

				<button onClick={handleExport} disabled={running}>
					📦 Export EPUB
				</button>
			</div>

			{exportPath && (
				<div className="success-banner">✅ Exported: {exportPath}</div>
			)}
		</div>
	);
}
