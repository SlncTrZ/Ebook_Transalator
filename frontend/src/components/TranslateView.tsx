import { useCallback, useEffect, useRef, useState } from "react";
import type { Book, ProgressData } from "../api";
import {
	cancelTranslate,
	listCategories,
	startAgenticTranslation,
	startStandardTranslation,
	translateProgress,
} from "../api";
import { MetadataReview } from "./MetadataReview";

interface TranslateViewProps {
	book: Book | null;
	apiKey: string;
	model: string;
	vendor: string;
}

export function TranslateView({ book, apiKey, model, vendor }: TranslateViewProps) {
	const [running, setRunning] = useState(false);
	const [progress, setProgress] = useState<ProgressData | null>(null);
	const [category, setCategory] = useState("general");
	const [categories, setCategories] = useState<Record<string, string>>({});
	const [chapterStart, setChapterStart] = useState(1);
	const [chapterEnd, setChapterEnd] = useState(99999);
	const [error, setError] = useState<string | null>(null);
	const [agentic, setAgentic] = useState(false);
	const [agentPhase, setAgentPhase] = useState("");
	const cancelRef = useRef<(() => void) | null>(null);
	const requiresApiKey = vendor !== "ollama";

	useEffect(() => {
		void listCategories().then(setCategories).catch((err) => setError(String(err)));
	}, []);

	useEffect(() => {
		if (book?.category) setCategory(book.category);
	}, [book?.id, book?.category]);

	const handleStart = useCallback(async () => {
		if (!book || (requiresApiKey && !apiKey)) return;
		setRunning(true);
		setError(null);
		setProgress(null);
		setAgentPhase(agentic ? "Starting Agentic translation" : "Starting Standard translation");

		try {
			const startCommand = agentic ? startAgenticTranslation : startStandardTranslation;
			const result = await startCommand(
				book.file_path,
				vendor,
				apiKey,
				model,
				category,
				chapterStart,
				chapterEnd,
			);
			setAgentPhase(agentic ? "Agentic translation running" : "Standard translation running");

			cancelRef.current = translateProgress(
				result.book_id,
				chapterStart,
				chapterEnd,
				(data) => {
					setProgress(data);
					if (data.status === "done") {
						setAgentPhase("Translation complete");
						setRunning(false);
					} else if (data.status === "failed") {
						setAgentPhase("Translation completed with failures");
						setRunning(false);
					}
				},
				() => setRunning(false),
				(message) => {
					setError(message);
					setRunning(false);
				},
			);
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
			setRunning(false);
		}
	}, [
		book,
		requiresApiKey,
		apiKey,
		vendor,
		model,
		category,
		chapterStart,
		chapterEnd,
		agentic,
	]);

	const handleCancel = useCallback(async () => {
		cancelRef.current?.();
		await cancelTranslate();
		setAgentPhase("Translation cancelled");
		setRunning(false);
	}, []);

	if (!book) return <p className="muted">Select a book to start the translation workflow.</p>;

	const startDisabled = running || (requiresApiKey && !apiKey);

	return (
		<div className="translate-view">
			<div className="book-info">
				<strong>{book.title || "Untitled"}</strong>
				{book.author && <span> · {book.author}</span>}
			</div>

			<MetadataReview book={book} apiKey={apiKey} model={model} vendor={vendor} />

			<div className="controls">
				<label>
					From chapter
					<input
						type="number"
						min={1}
						value={chapterStart}
						onChange={(event) => setChapterStart(Math.max(1, Number(event.target.value) || 1))}
					/>
				</label>
				<label>
					To chapter
					<input
						type="number"
						min={1}
						value={chapterEnd >= 99999 ? "" : chapterEnd}
						placeholder="end"
						onChange={(event) => setChapterEnd(event.target.value ? Number(event.target.value) : 99999)}
					/>
				</label>
				<label>
					Category
					<select value={category} onChange={(event) => setCategory(event.target.value)}>
						{Object.entries(categories).map(([key, label]) => (
							<option key={key} value={key}>{label}</option>
						))}
					</select>
				</label>
			</div>

			{error && <div className="error-banner">{error}</div>}
			{agentPhase && <p className="hint">{agentPhase}</p>}

			{progress && (
				<div className="progress-section">
					<div className="progress-bar-container">
						<div
							className="progress-bar-fill"
							style={{
								width: progress.total > 0
									? `${((progress.done + progress.failed) / progress.total) * 100}%`
									: "0%",
							}}
						/>
					</div>
					<p className="progress-text">
						{progress.done} done · {progress.failed} failed · {progress.total} total
					</p>
				</div>
			)}

			<div className="actions">
				{running ? (
					<button className="btn-danger" onClick={() => void handleCancel()}>Cancel translation</button>
				) : (
					<>
						<button className="btn-primary" onClick={() => void handleStart()} disabled={startDisabled}>
							Start {agentic ? "Agentic" : "Standard"}
						</button>
						<button onClick={() => setAgentic((value) => !value)}>
							Mode: {agentic ? "Agentic" : "Standard"}
						</button>
					</>
				)}
			</div>

			{requiresApiKey && !apiKey && (
				<p className="muted">Configure an API key in Settings before starting this provider.</p>
			)}
		</div>
	);
}
