import { useEffect, useRef, useState } from "react";
import type { Book } from "../api";
import { createBook, deleteBook, listBooks, uploadBook } from "../api";

interface LibraryProps {
	onSelectBook: (book: Book) => void;
	selectedBook: Book | null;
	onRefresh: () => void;
}

export function Library({ onSelectBook, selectedBook }: LibraryProps) {
	const fileInputRef = useRef<HTMLInputElement>(null);
	const [books, setBooks] = useState<Book[]>([]);
	const [loading, setLoading] = useState(true);
	const [importPath, setImportPath] = useState("");
	const [importError, setImportError] = useState<string | null>(null);
	const [importing, setImporting] = useState(false);

	const loadBooks = async () => {
		setLoading(true);
		try {
			setBooks(await listBooks());
		} catch (error) {
			setImportError(`Could not load library: ${String(error)}`);
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void loadBooks();
	}, []);

	const doImport = async (path: string) => {
		if (!path.trim()) return;
		setImportError(null);
		setImporting(true);
		try {
			await createBook(path.trim());
			await loadBooks();
			setImportPath("");
		} catch (error) {
			setImportError(error instanceof Error ? error.message : String(error));
		} finally {
			setImporting(false);
		}
	};

	const handleUpload = async (file: File) => {
		setImportError(null);
		setImporting(true);
		try {
			await uploadBook(file);
			await loadBooks();
		} catch (error) {
			setImportError(error instanceof Error ? error.message : String(error));
		} finally {
			setImporting(false);
			if (fileInputRef.current) fileInputRef.current.value = "";
		}
	};

	return (
		<div className="library">
			<div className="import-bar">
				<input
					ref={fileInputRef}
					type="file"
					accept=".epub,.txt"
					hidden
					onChange={(event) => {
						const file = event.target.files?.[0];
						if (file) void handleUpload(file);
					}}
				/>
				<input
					type="text"
					aria-label="Book file path"
					placeholder="Paste a local .epub or .txt path"
					value={importPath}
					onChange={(event) => setImportPath(event.target.value)}
					onKeyDown={(event) => {
						if (event.key === "Enter") void doImport(importPath);
					}}
				/>
				<button
					onClick={() => void doImport(importPath)}
					disabled={!importPath.trim() || importing}
				>
					{importing ? "Importing…" : "Import path"}
				</button>
				<button onClick={() => fileInputRef.current?.click()} disabled={importing}>
					Browse file
				</button>
			</div>

			{importError && <div className="error-banner">{importError}</div>}

			{loading ? (
				<p className="muted">Loading library…</p>
			) : books.length === 0 ? (
				<p className="muted">No books yet. Import an EPUB or TXT file to begin.</p>
			) : (
				<table className="book-table">
					<thead>
						<tr>
							<th>Title</th>
							<th>Author</th>
							<th>Status</th>
							<th>Progress</th>
							<th>Actions</th>
						</tr>
					</thead>
					<tbody>
						{books.map((book) => (
							<tr key={book.id} className={selectedBook?.id === book.id ? "selected" : ""}>
								<td>{book.title || "Untitled"}</td>
								<td>{book.author || "Unknown"}</td>
								<td><span className={`status-badge ${book.status}`}>{book.status}</span></td>
								<td className="mono-value">
									{book.total_chunks > 0 ? `${book.done_chunks}/${book.total_chunks}` : "—"}
								</td>
								<td>
									<div className="actions">
										<button onClick={() => onSelectBook(book)}>Open</button>
										<button
											className="btn-small btn-danger"
											onClick={async () => {
												if (!confirm("Delete this book and all translations?")) return;
												await deleteBook(book.id);
												await loadBooks();
											}}
										>
											Delete
										</button>
									</div>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			)}
		</div>
	);
}
