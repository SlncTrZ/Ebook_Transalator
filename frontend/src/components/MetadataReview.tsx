import { useCallback, useEffect, useState } from "react";
import type { Book, MetadataResult } from "../api";
import { confirmMetadata, listCategories, researchBook } from "../api";

interface MetadataReviewProps {
	book: Book;
	apiKey: string;
	model: string;
	vendor: string;
	baseUrl: string;
}

const LANG: Record<string, string> = {
	en: "English",
	vi: "Tiếng Việt",
	zh: "中文",
	ja: "日本語",
	ko: "한국어",
	fr: "Français",
	de: "Deutsch",
	es: "Español",
	ru: "Русский",
	th: "ไทย",
};

export function MetadataReview({ book, apiKey, model, vendor, baseUrl }: MetadataReviewProps) {
	const confirmedKey = `et_confirmed_${book.id}`;
	const [analyzing, setAnalyzing] = useState(false);
	const [metadata, setMetadata] = useState<MetadataResult | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [confirmed, setConfirmed] = useState(() => localStorage.getItem(confirmedKey) === "true");
	const [feedback, setFeedback] = useState("");
	const [forceSearch, setForceSearch] = useState(false);
	const [categories, setCategories] = useState<Record<string, string>>({});
	const [title, setTitle] = useState(book.title);
	const [localizedTitle, setLocalizedTitle] = useState(book.localized_title || "");
	const [author, setAuthor] = useState(book.author);
	const [category, setCategory] = useState(book.category || "general");
	const [sourceLang, setSourceLang] = useState(book.source_lang || "en");
	const [targetLang, setTargetLang] = useState(book.target_lang || "vi");
	const requiresApiKey = vendor !== "ollama";

	useEffect(() => {
		void listCategories().then(setCategories).catch((err) => setError(String(err)));
	}, []);

	useEffect(() => {
		setTitle(book.title);
		setLocalizedTitle(book.localized_title || "");
		setAuthor(book.author);
		setCategory(book.category || "general");
		setSourceLang(book.source_lang || "en");
		setTargetLang(book.target_lang || "vi");
	}, [book.id]);

	const handleAnalyze = useCallback(async () => {
		setAnalyzing(true);
		setError(null);
		try {
			const data = await researchBook(book.id, vendor, apiKey, model, baseUrl, feedback, forceSearch);
			setMetadata(data);
			setTitle(data.title || book.title);
			setLocalizedTitle(data.localized_title || book.localized_title || "");
			setAuthor(data.author || book.author);
			setCategory(data.category || book.category || "general");
			setSourceLang(data.source_lang || book.source_lang || "en");
			setTargetLang(data.target_lang || book.target_lang || "vi");
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setAnalyzing(false);
		}
	}, [book, vendor, apiKey, model, baseUrl, feedback, forceSearch]);

	const handleConfirm = useCallback(async () => {
		setError(null);
		try {
			await confirmMetadata(book.id, {
				title,
				author,
				localized_title: localizedTitle,
				source_lang: sourceLang,
				target_lang: targetLang,
				category,
			});
			setConfirmed(true);
			localStorage.setItem(confirmedKey, "true");
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		}
	}, [book.id, confirmedKey, title, author, localizedTitle, sourceLang, targetLang, category]);

	if (confirmed) {
		return (
			<div className="metadata-review">
				<div className="review-summary-row">
					<div><span className="eyebrow">Metadata</span><strong>Confirmed</strong></div>
					<button
						className="btn-small"
						onClick={() => {
							setConfirmed(false);
							localStorage.removeItem(confirmedKey);
						}}
					>
						Review again
					</button>
				</div>
			</div>
		);
	}

	return (
		<div className="metadata-review">
			<div className="review-summary-row">
				<div>
					<span className="eyebrow">Research & HITL</span>
					<strong>{metadata ? "Review suggested metadata" : "Analyze this book before translation"}</strong>
				</div>
				{metadata && (
					<span className="mono-value">confidence {Math.round((metadata.confidence || 0) * 100)}%</span>
				)}
			</div>

			{error && <div className="error-banner">{error}</div>}

			<div className="feedback-panel">
				<label>
					User context
					<textarea
						value={feedback}
						onChange={(event) => setFeedback(event.target.value)}
						placeholder="Optional context, corrections, known title, genre, terminology, or author details"
					/>
				</label>
				<label className="inline-check">
					<input
						type="checkbox"
						checked={forceSearch}
						onChange={(event) => setForceSearch(event.target.checked)}
					/>
					Verify with web search
				</label>
				<button
					onClick={() => void handleAnalyze()}
					disabled={analyzing || !model || !baseUrl.trim() || (requiresApiKey && !apiKey)}
				>
					{analyzing ? "Analyzing…" : metadata ? "Re-analyze" : "Analyze metadata"}
				</button>
			</div>

			{metadata && (
				<div className="review-card">
					<div className="review-fields">
						<label>Original title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
						<label>Localized title<input value={localizedTitle} onChange={(event) => setLocalizedTitle(event.target.value)} /></label>
						<label>Author<input value={author} onChange={(event) => setAuthor(event.target.value)} /></label>
						<label>
							Category
							<select value={category} onChange={(event) => setCategory(event.target.value)}>
								{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
							</select>
						</label>
						<label>
							Source language
							<select value={sourceLang} onChange={(event) => setSourceLang(event.target.value)}>
								{Object.entries(LANG).map(([key, label]) => <option key={key} value={key}>{label} ({key})</option>)}
							</select>
						</label>
						<label>
							Target language
							<select value={targetLang} onChange={(event) => setTargetLang(event.target.value)}>
								{Object.entries(LANG).map(([key, label]) => <option key={key} value={key}>{label} ({key})</option>)}
							</select>
						</label>
					</div>

					{metadata.description && <p className="desc-hint">{metadata.description}</p>}
					{metadata.style_notes && <p className="desc-hint">Style: {metadata.style_notes}</p>}
					{metadata.sources.length > 0 && (
						<details className="sources">
							<summary>Research sources ({metadata.sources.filter(Boolean).length})</summary>
							<ul>
								{metadata.sources.filter(Boolean).map((url) => (
									<li key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></li>
								))}
							</ul>
						</details>
					)}
					<div className="review-actions">
						<button className="btn-primary" onClick={() => void handleConfirm()}>Confirm metadata</button>
					</div>
				</div>
			)}
		</div>
	);
}
