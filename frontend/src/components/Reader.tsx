import { useEffect, useState } from "react";
import type { BookQAResult, QAChunkResult, ReaderChunk } from "../api";
import {
	getBookQA,
	getReaderChunks,
	rememberChunkTranslation,
	requeueChunk,
	updateChunkTranslation,
} from "../api";

interface ReaderProps {
	bookId: number | null;
}

export function Reader({ bookId }: ReaderProps) {
	const [chunks, setChunks] = useState<ReaderChunk[]>([]);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [chapterStart, setChapterStart] = useState(1);
	const [chapterEnd, setChapterEnd] = useState(5);
	const [statusFilter, setStatusFilter] = useState("all");
	const [drafts, setDrafts] = useState<Record<number, string>>({});
	const [qa, setQa] = useState<BookQAResult | null>(null);

	const load = async () => {
		if (!bookId) return;
		setLoading(true);
		setError(null);
		try {
			const [data, qaData] = await Promise.all([
				getReaderChunks(bookId, chapterStart, chapterEnd, statusFilter),
				getBookQA(bookId, chapterStart, chapterEnd),
			]);
			setChunks(data.chunks);
			setQa(qaData);
			setDrafts(
				Object.fromEntries(
					data.chunks.map((chunk) => [chunk.id, chunk.translated_text ?? ""]),
				),
			);
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		if (bookId) void load();
		else {
			setChunks([]);
			setQa(null);
		}
	}, [bookId]);

	const byChapter: Record<number, ReaderChunk[]> = {};
	for (const chunk of chunks) (byChapter[chunk.chapter_idx] ??= []).push(chunk);
	const chapterIndexes = Object.keys(byChapter).map(Number).sort((a, b) => a - b);
	const qaByChunk = new Map<number, QAChunkResult>(
		(qa?.chunks ?? []).map((item) => [item.chunk_id, item]),
	);

	if (!bookId) {
		return <p className="muted">Select a book in Library to inspect its translation.</p>;
	}

	return (
		<div className="reader">
			<div className="reader-controls">
				<label>
					From
					<input
						type="number"
						min={1}
						value={chapterStart}
						onChange={(event) => setChapterStart(Math.max(1, Number(event.target.value) || 1))}
					/>
				</label>
				<label>
					To
					<input
						type="number"
						min={1}
						value={chapterEnd >= 99999 ? "" : chapterEnd}
						placeholder="end"
						onChange={(event) => setChapterEnd(event.target.value ? Number(event.target.value) : 99999)}
					/>
				</label>
				<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
					<option value="all">All states</option>
					<option value="done">Translated</option>
					<option value="pending">Pending</option>
					<option value="failed">Failed</option>
				</select>
				<button onClick={() => void load()} disabled={loading}>
					{loading ? "Loading…" : "Refresh"}
				</button>
			</div>

			{error && <div className="error-banner">{error}</div>}
			{qa && (
				<div className="qa-summary" aria-label="Translation quality summary">
					<span>{qa.checked_chunks} checked</span>
					<strong>{qa.errors} errors</strong>
					<span>{qa.warnings} warnings</span>
					<span>{qa.issue_chunks} affected chunks</span>
				</div>
			)}
			{!loading && chunks.length === 0 && (
				<p className="muted">No chunks match this chapter range and status filter.</p>
			)}

			<div className="reader-content">
				{chapterIndexes.map((chapterIndex) => (
					<section key={chapterIndex} className="chapter-block">
						<h3>Chapter {chapterIndex + 1}</h3>
						{byChapter[chapterIndex].map((chunk) => {
							const chunkQa = qaByChunk.get(chunk.id);
							return (
							<div key={chunk.id} className={`bilingual-pair${chunkQa ? " has-qa-issues" : ""}`}>
								<div className="original-text">{chunk.original_text}</div>
								<div className="translated-text">
									{chunkQa && (
										<div className="qa-issues">
											{chunkQa.issues.map((issue, index) => (
												<div key={`${issue.code}-${index}`} className={`qa-issue ${issue.severity}`}>
													<strong>{issue.code.replaceAll("_", " ")}</strong>
													<span>{issue.message}</span>
													{issue.expected && <small>Expected: {issue.expected}</small>}
													{issue.actual && <small>Actual: {issue.actual}</small>}
												</div>
											))}
										</div>
									)}
									<textarea
										className="translation-editor"
										value={drafts[chunk.id] ?? ""}
										placeholder={chunk.status === "failed" ? "Translation failed" : "Pending translation"}
										onChange={(event) =>
											setDrafts((current) => ({ ...current, [chunk.id]: event.target.value }))
										}
									/>
									<div className="chunk-actions">
										<button
											className="btn-small"
											disabled={!(drafts[chunk.id] ?? "").trim()}
											onClick={async () => {
												await updateChunkTranslation(chunk.id, drafts[chunk.id] ?? "");
												await load();
											}}
										>
											Save correction
										</button>
										<button
											className="btn-small"
											disabled={!(drafts[chunk.id] ?? "").trim()}
											onClick={async () => {
												await rememberChunkTranslation(chunk.id, drafts[chunk.id] ?? "");
											}}
										>
											Save to memory
										</button>
										<button
											className="btn-small"
											onClick={async () => {
												await requeueChunk(chunk.id);
												await load();
											}}
										>
											Requeue
										</button>
									</div>
								</div>
							</div>
							);
						})}
					</section>
				))}
			</div>
		</div>
	);
}
