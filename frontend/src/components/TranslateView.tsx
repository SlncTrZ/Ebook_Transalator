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
	const [exportPath, setExportPath] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
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
				1,
				99999,
			);
			const bookId = result.book_id;

			cancelRef.current = translateProgress(
				bookId,
				(data) => {
					setProgress(data);
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
	}, [book, apiKey, model, category]);

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
				onStartTranslate={(_id, _start, _end) => {
					setRunning(true);
					// _start/_end for chapter range
				}}
			/>

			<div className="controls">
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
					<button
						className="btn-primary"
						onClick={handleStart}
						disabled={!apiKey}
						title={!apiKey ? "Set API key in Settings" : ""}
					>
						▶ Start Translation
					</button>
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
