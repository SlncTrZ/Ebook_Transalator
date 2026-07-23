import { useState, useEffect, useCallback } from "react";
import type { GlossaryItem } from "../api";
import { getGlossary, createGlossary, deleteGlossary } from "../api";

interface GlossaryEditorProps {
	bookId: number | null;
}

export function GlossaryEditor({ bookId }: GlossaryEditorProps) {
	const [entries, setEntries] = useState<GlossaryItem[]>([]);
	const [source, setSource] = useState("");
	const [target, setTarget] = useState("");
	const [notes, setNotes] = useState("");

	const loadEntries = useCallback(async () => {
		if (!bookId) return;
		try {
			const data = await getGlossary(bookId);
			setEntries(data);
		} catch (e) {
			console.error("Failed to load glossary", e);
		}
	}, [bookId]);

	useEffect(() => {
		if (bookId) loadEntries();
		else setEntries([]);
	}, [bookId, loadEntries]);

	const handleAdd = async () => {
		if (!bookId || !source.trim() || !target.trim()) return;
		try {
			await createGlossary(bookId, source.trim(), target.trim(), notes.trim());
			setSource("");
			setTarget("");
			setNotes("");
			await loadEntries();
		} catch (e) {
			console.error("Failed to add glossary entry", e);
		}
	};

	const handleDelete = async (id: number) => {
		try {
			await deleteGlossary(id);
			await loadEntries();
		} catch (e) {
			console.error("Failed to delete entry", e);
		}
	};

	if (!bookId) {
		return (
			<div className="glossary-editor">
				<h2>📝 Glossary</h2>
				<p className="muted">
					Select a book from the Library tab to manage its glossary.
				</p>
			</div>
		);
	}

	return (
		<div className="glossary-editor">
			<h2>📝 Glossary</h2>
			<p className="muted">
				Book ID: {bookId} — Add term mappings for consistent translations.
			</p>

			<div className="glossary-form">
				<input
					placeholder="Source (e.g. Harry Potter)"
					value={source}
					onChange={(e) => setSource(e.target.value)}
				/>
				<input
					placeholder="Target (e.g. Harry Potter)"
					value={target}
					onChange={(e) => setTarget(e.target.value)}
				/>
				<input
					placeholder="Notes (optional)"
					value={notes}
					onChange={(e) => setNotes(e.target.value)}
				/>
				<button onClick={handleAdd} disabled={!source.trim() || !target.trim()}>
					+ Add
				</button>
			</div>

			{entries.length === 0 ? (
				<p className="muted">No glossary entries yet.</p>
			) : (
				<table className="glossary-table">
					<thead>
						<tr>
							<th>Source</th>
							<th>Target</th>
							<th>Notes</th>
							<th></th>
						</tr>
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
										onClick={() => handleDelete(entry.id)}
									>
										✕
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
