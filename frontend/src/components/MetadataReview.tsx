import { useState, useCallback } from "react";
import type { Book } from "../api";

interface MetadataResult {
	title: string;
	author: string;
	source_lang: string;
	target_lang: string;
	localized_title: string;
	category: string;
	description: string;
	confidence: number;
	sources: string[];
	from_knowledge: boolean;
}

interface MetadataReviewProps {
	book: Book;
	apiKey: string;
	model: string;
	vendor: string;
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
const CATS: Record<string, string> = {
	tien_hiep: "Tiên hiệp",
	vo_hiep: "Võ hiệp",
	khoa_hoc: "Khoa học viễn tưởng",
	ky_ao: "Kỳ ảo",
	kinh_di: "Kinh dị",
	ngon_tinh: "Ngôn tình",
	trinh_tham: "Trinh thám",
	hai_huoc: "Hài hước",
	van_hoc: "Văn học",
	lich_su: "Lịch sử",
	hien_dai: "Hiện đại",
	general: "Tổng hợp",
};

export function MetadataReview({
	book,
	apiKey,
	model,
	vendor,
}: MetadataReviewProps) {
	const confirmedKey = "et_confirmed_" + book.id;
	const [analyzing, setAnalyzing] = useState(false);
	const [metadata, setMetadata] = useState<MetadataResult | null>(null);
	const [analyzed, setAnalyzed] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [confirmed, setConfirmed] = useState(() => localStorage.getItem(confirmedKey) === "true");
	const [feedback, setFeedback] = useState("");
	const [chapterStart, setChapterStart] = useState(1);
	const [chapterEnd, setChapterEnd] = useState(99999);

	const [title, setTitle] = useState(book.title);
	const [author, setAuthor] = useState(book.author);
	const [category, setCategory] = useState(book.category || "general");
	const [sourceLang, setSourceLang] = useState(book.source_lang || "en");
	const [targetLang, setTargetLang] = useState("vi");
	const [webSearched, setWebSearched] = useState(false);
	const [fromKnowledge, setFromKnowledge] = useState(false);

	const handleAnalyze = useCallback(
		async (feedbackText = "") => {
			setAnalyzing(true);
			setError(null);
			try {
				const res = await fetch(
					"http://127.0.0.1:8080/api/books/" + book.id + "/research",
					{
						method: "POST",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({
							vendor,
							api_key: apiKey,
							model,
							user_feedback: feedbackText,
						}),
					},
				);
				if (!res.ok) throw new Error(await res.text());
				const data: MetadataResult = await res.json();
				setMetadata(data);
				setTitle(data.title || book.title);
				setAuthor(data.author || book.author);
				setCategory(data.category || "general");
				setSourceLang(data.source_lang || "en");
				setTargetLang(data.target_lang || "vi");
				setWebSearched(data.sources && data.sources.length > 0);
				setFromKnowledge(data.from_knowledge || false);
				setAnalyzed(true);
			} catch (e) {
				setError(String(e));
			}
			setAnalyzing(false);
		},
		[book.id, book.title, book.author, book.source_lang, apiKey, model, vendor],
	);

	const handleConfirm = useCallback(async () => {
		setError(null);
		try {
			const res = await fetch(
				"http://127.0.0.1:8080/api/books/" + book.id + "/confirm-metadata",
				{
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						title,
						author,
						category,
						source_lang: sourceLang,
						target_lang: targetLang,
					}),
				},
			);
			if (!res.ok) throw new Error(await res.text());
			setConfirmed(true);
			localStorage.setItem(confirmedKey, "true");
		} catch (e) {
			setError(String(e));
		}
	}, [book.id, title, author, category, sourceLang, targetLang]);

	if (confirmed) {
		return (
			<div className="metadata-review">
				<h3>🌐 Translate Options</h3>
				<div className="chapter-range">
					<label>
						From Chapter:{" "}
						<input
							type="number"
							min={1}
							value={chapterStart}
							onChange={(e) =>
								setChapterStart(Math.max(1, parseInt(e.target.value) || 1))
							}
						/>
					</label>
					<label>
						To Chapter:{" "}
						<input
							type="number"
							min={1}
							value={chapterEnd >= 99999 ? "" : chapterEnd}
							placeholder="Last"
							onChange={(e) =>
								setChapterEnd(e.target.value ? parseInt(e.target.value) : 99999)
							}
						/>
					</label>
				</div>
				<div className="review-actions" style={{ marginTop: 12 }}></div>
				<p className="hint" style={{ color: "#3fb950", fontWeight: 600 }}>
					✅ Metadata confirmed! Go to Translate tab and press Start.
				</p>
			</div>
		);
	}

	return (
		<div className="metadata-review">
			<h3>🔍 Metadata Review</h3>
			<p className="hint">
				AI sẽ phân tích nội dung sách và đề xuất thông tin.
				{!analyzed && <span> (AI có kiến thức nền về triệu cuốn sách)</span>}
				{analyzed && fromKnowledge && (
					<span style={{ color: "#3fb950" }}>
						{" "}
						✅ AI nhận ra sách từ kiến thức nền
					</span>
				)}
				{analyzed && !fromKnowledge && (
					<span style={{ color: "#f0883e" }}>
						{" "}
						🔍 AI không tự nhận ra, đã tìm DuckDuckGo
					</span>
				)}
				{webSearched && <span> (kết quả web trong Sources)</span>}
			</p>

			{error && <div className="error-banner">{error}</div>}

			{!analyzed ? (
				<>
					<div className="review-actions">
						<button
							onClick={() => handleAnalyze()}
							disabled={analyzing || !apiKey}
						>
							{analyzing ? "⏳ Analyzing..." : "🔍 Analyze Metadata"}
						</button>
					</div>
					<div style={{ marginTop: 10 }}>
						<textarea
							placeholder="Optional: provide additional info about this book (e.g. 'This is a xianxia novel about cultivation')"
							value={feedback}
							onChange={(e) => setFeedback(e.target.value)}
							style={{
								width: "100%",
								minHeight: 60,
								padding: 8,
								borderRadius: 6,
								border: "1px solid #30363d",
								background: "#0d1117",
								color: "#e1e4e8",
								fontSize: 13,
							}}
						/>
						<button
							onClick={() => handleAnalyze(feedback)}
							disabled={analyzing || !apiKey}
							style={{ marginTop: 6 }}
						>
							🔍 Analyze with Feedback
						</button>
					</div>
				</>
			) : (
				metadata && (
					<div className="review-card">
						{metadata.confidence > 0 && (
							<div className="confidence-bar">
								<div className="confidence-label">
									Confidence: {Math.round(metadata.confidence * 100)}%
								</div>
								<div className="confidence-fill-container">
									<div
										className="confidence-fill"
										style={{ width: `${metadata.confidence * 100}%` }}
									/>
								</div>
							</div>
						)}

						<div className="review-fields">
							<label>
								Title{" "}
								<input
									value={title}
									onChange={(e) => setTitle(e.target.value)}
								/>
							</label>
							{metadata.localized_title && (
								<div className="localized-hint">
									💡 Suggested: <strong>{metadata.localized_title}</strong>
								</div>
							)}
							<label>
								Author{" "}
								<input
									value={author}
									onChange={(e) => setAuthor(e.target.value)}
								/>
							</label>
							<label>
								Source Language{" "}
								<select
									value={sourceLang}
									onChange={(e) => setSourceLang(e.target.value)}
								>
									{Object.entries(LANG).map(([k, v]) => (
										<option key={k} value={k}>
											{v} ({k})
										</option>
									))}
								</select>
							</label>
							<label>
								Target Language{" "}
								<select
									value={targetLang}
									onChange={(e) => setTargetLang(e.target.value)}
								>
									<option value="vi">Tiếng Việt</option>
									<option value="en">English</option>
									<option value="zh">中文</option>
									<option value="ja">日本語</option>
									<option value="ko">한국어</option>
								</select>
							</label>
							<label>
								Category{" "}
								<select
									value={category}
									onChange={(e) => setCategory(e.target.value)}
								>
									{Object.entries(CATS).map(([k, v]) => (
										<option key={k} value={k}>
											{v}
										</option>
									))}
								</select>
							</label>
							{metadata.description && (
								<div className="desc-hint">📝 {metadata.description}</div>
							)}
						</div>

						{metadata.sources.length > 0 && (
							<details className="sources">
								<summary>
									Sources ({metadata.sources.filter(Boolean).length})
								</summary>
								<ul>
									{metadata.sources.filter(Boolean).map((url, i) => (
										<li key={i}>
											<a href={url} target="_blank" rel="noopener noreferrer">
												{url}
											</a>
										</li>
									))}
								</ul>
							</details>
						)}

						<div className="review-actions">
							<button className="btn-primary" onClick={handleConfirm}>
								✅ Confirm
							</button>
							<button
								onClick={() => {
									setAnalyzed(false);
									setMetadata(null);
								}}
							>
								🔄 Re-analyze
							</button>
						</div>

						<details style={{ marginTop: 10 }}>
							<summary
								style={{ fontSize: 13, color: "#8b949e", cursor: "pointer" }}
							>
								Feedback / Correct Info
							</summary>
							<textarea
								placeholder="Tell AI what's wrong or provide correct info..."
								value={feedback}
								onChange={(e) => setFeedback(e.target.value)}
								style={{
									width: "100%",
									minHeight: 60,
									marginTop: 6,
									padding: 8,
									borderRadius: 6,
									border: "1px solid #30363d",
									background: "#0d1117",
									color: "#e1e4e8",
									fontSize: 13,
								}}
							/>
							<button
								onClick={() => handleAnalyze(feedback)}
								disabled={analyzing}
								style={{ marginTop: 6 }}
							>
								🔄 Re-analyze with Feedback
							</button>
						</details>
					</div>
				)
			)}
		</div>
	);
}
