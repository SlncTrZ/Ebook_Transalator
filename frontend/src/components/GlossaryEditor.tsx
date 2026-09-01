import { useCallback, useEffect, useState } from "react";
import type { GlossaryItem } from "../api";
import { createGlossary, deleteGlossary, getGlossary } from "../api";

interface GlossaryEditorProps {
	bookId: number | null;
}

export function GlossaryEditor({ bookId }: GlossaryEditorProps) {
	const [entries, setEntries] = useState<GlossaryItem[]>([]);
	const [source, setSource] = useState("");
	const [target, setTarget] = useState("");
	const [notes, setNotes] = useState("");
	const [error, setError] = useState<string | null>(null);

	const loadEntries = useCallback(async () => {
		if (!bookId) return;
		setError(null);
		try {
			setEntries(await getGlossary(bookId));
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		}
	}, [bookId]);

	useEffect(() => {
		if (bookId) void loadEntries();
		else setEntries([]);
	}, [bookId, loadEntries]);

	const handleAdd = async () => {
		if (!bookId || !source.trim() || !target.trim()) return;
		setError(null);
		try {
			await createGlossary(bookId, source.trim(), target.trim(), notes.trim());
			setSource("");
			setTarget("");
			setNotes("");
			await loadEntries();
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		}
	};

	if (!bookId) return <p className="muted">Select a book to manage glossary terms.</p>;

	return (
		<div className="glossary-editor">
			<div className="workspace-intro compact-intro">
				<div>
					<span className="section-index">TERM / {String(entries.length).padStart(2, "0")}</span>
					<strong>Terminology control</strong>
					<p>Book-scoped mappings are injected exactly into translation prompts.</p>
				</div>
			</div>
			<div className="section-bar">
				<div><span className="section-index">01</span><strong>Add mapping</strong></div>
				<span>Source and target terms are case-sensitive on output.</span>
			</div>
			<div className="glossary-form">
				<input placeholder="Source term" value={source} onChange={(event) => setSource(event.target.value)} />
				<input placeholder="Target term" value={target} onChange={(event) => setTarget(event.target.value)} />
				<input placeholder="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
				<button onClick={() => void handleAdd()} disabled={!source.trim() || !target.trim()}>
					Add term
				</button>
			</div>

			{error && <div className="error-banner">{error}</div>}
			{entries.length === 0 ? (
				<div className="empty-state compact-empty">
					<span className="empty-state-index">TERM / 00</span>
					<strong>No terminology rules</strong>
					<p>Add names, technical terms, ranks, places or phrases that must remain consistent across the book.</p>
				</div>
			) : (
				<table className="glossary-table">
					<thead>
						<tr><th>Source</th><th>Target</th><th>Notes</th><th>Action</th></tr>
					</thead>
					<tbody>
						{entries.map((entry) => (
							<tr key={entry.id}>
								<td>{entry.source_term}</td>
								<td>{entry.target_term}</td>
								<td className="muted">{entry.notes || "—"}</td>
								<td>
									<button
										className="btn-small btn-danger"
										onClick={async () => {
											await deleteGlossary(entry.id);
											await loadEntries();
										}}
									>
										Delete
									</button>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			)}
		</div>
	);
}
