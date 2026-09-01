import { useEffect, useState } from "react";
import type { ReaderChunk } from "../api";
import {
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

	const load = async () => {
		if (!bookId) return;
		setLoading(true);
		setError(null);
		try {
			const data = await getReaderChunks(bookId, chapterStart, chapterEnd, statusFilter);
			setChunks(data.chunks);
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
		else setChunks([]);
	}, [bookId]);

	const byChapter: Record<number, ReaderChunk[]> = {};
	for (const chunk of chunks) (byChapter[chunk.chapter_idx] ??= []).push(chunk);
	const chapterIndexes = Object.keys(byChapter).map(Number).sort((a, b) => a - b);

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
			{!loading && chunks.length === 0 && (
				<p className="muted">No chunks match this chapter range and status filter.</p>
			)}

			<div className="reader-content">
				{chapterIndexes.map((chapterIndex) => (
					<section key={chapterIndex} className="chapter-block">
						<h3>Chapter {chapterIndex + 1}</h3>
						{byChapter[chapterIndex].map((chunk) => (
							<div key={chunk.id} className="bilingual-pair">
								<div className="original-text">{chunk.original_text}</div>
								<div className="translated-text">
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
						))}
					</section>
				))}
			</div>
		</div>
	);
}
