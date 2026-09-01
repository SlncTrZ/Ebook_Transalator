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

	const settled = progress ? progress.done + progress.failed : 0;
	const progressPercent = progress && progress.total > 0
		? Math.round((settled / progress.total) * 100)
		: 0;

	return (
		<div className="translate-view">
			<div className="workspace-intro">
				<div>
					<span className="section-index">TR / ACTIVE</span>
					<strong>{book.title || "Untitled"}</strong>
					<p>{book.author || "Unknown author"}</p>
				</div>
				<div className="mode-readout">
					<span>Mode</span>
					<strong>{agentic ? "Agentic" : "Standard"}</strong>
				</div>
			</div>

			<MetadataReview book={book} apiKey={apiKey} model={model} vendor={vendor} />

			<div className="section-bar">
				<div><span className="section-index">01</span><strong>Translation scope</strong></div>
				<span>Choose chapter range and category before dispatch.</span>
			</div>
			<div className="controls translation-controls">
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
			{agentPhase && (
				<div className="run-state-line">
					<span className={running ? "status-dot running" : "status-dot"} />
					<span>{agentPhase}</span>
				</div>
			)}

			{progress && (
				<div className="progress-section run-progress-panel">
					<div className="progress-readout">
						<div><span>Completed</span><strong>{progressPercent}%</strong></div>
						<div><span>Done</span><strong>{progress.done}</strong></div>
						<div><span>Failed</span><strong className={progress.failed > 0 ? "danger-text" : ""}>{progress.failed}</strong></div>
						<div><span>Total</span><strong>{progress.total}</strong></div>
					</div>
					<div className="progress-bar-container">
						<div className="progress-bar-fill" style={{ width: `${progressPercent}%` }} />
					</div>
				</div>
			)}

			<div className="dispatch-bar">
				<div>
					<span className="section-index">02 / Dispatch</span>
					<p>{agentic ? "Research-aware translation with validation." : "Fast deterministic translation through the configured gateway."}</p>
				</div>
				<div className="actions">
					{running ? (
						<button className="btn-danger" onClick={() => void handleCancel()}>Cancel translation</button>
					) : (
						<>
							<button onClick={() => setAgentic((value) => !value)}>
								Switch to {agentic ? "Standard" : "Agentic"}
							</button>
							<button className="btn-primary" onClick={() => void handleStart()} disabled={startDisabled}>
								Start {agentic ? "Agentic" : "Standard"}
							</button>
						</>
					)}
				</div>
			</div>

			{requiresApiKey && !apiKey && (
				<p className="muted">Configure an API key in Settings before starting this provider.</p>
			)}
		</div>
	);
}
