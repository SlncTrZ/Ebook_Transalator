import { useState, useEffect, useRef } from "react";
import type { Book } from "../api";
import { listBooks, createBook, uploadBook } from "../api";

const TEST_FILES = [
	"H:\\Develop\\Ebook_Transalator\\tests\\[修真·仙侠] 《红尘魔道（第二部）》 作者：狗狗执行官.txt",
	"H:\\Develop\\Ebook_Transalator\\tests\\[修真·仙侠] 《仙福龙缘+番外》 作者：花羽容.txt",
];

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
			const data = await listBooks();
			setBooks(data);
		} catch (e) {
			console.error("Failed to load books", e);
		}
		setLoading(false);
	};

	useEffect(() => {
		loadBooks();
	}, []);

	const doImport = async (path: string) => {
		if (!path.trim()) return;
		setImportError(null);
		setImporting(true);
		try {
			await createBook(path.trim());
			await loadBooks();
			setImportPath("");
		} catch (e: any) {
			setImportError(e?.message || String(e));
		}
		setImporting(false);
	};

	return (
		<div className="library">
			<h2>📚 Book Library</h2>

			<div className="import-bar">
				<input
					ref={fileInputRef}
					type="file"
					accept=".epub,.txt"
					style={{ display: "none" }}
					onChange={async (e) => {
						const file = e.target.files?.[0];
						if (!file) return;
						setImportError(null);
						setImporting(true);
						try {
							await uploadBook(file);
							await loadBooks();
						} catch (e: any) {
							setImportError(e?.message || String(e));
						}
						setImporting(false);
						if (fileInputRef.current) fileInputRef.current.value = "";
					}}
				/>
				<input
					type="text"
					placeholder="Or paste file path..."
					value={importPath}
					onChange={(e) => setImportPath(e.target.value)}
					onKeyDown={(e) => e.key === "Enter" && doImport(importPath)}
				/>
				<button
					onClick={() => doImport(importPath)}
					disabled={!importPath.trim() || importing}
				>
					{importing ? "⏳..." : "+ Import"}
				</button>
				<button
					onClick={() => fileInputRef.current?.click()}
					disabled={importing}
					title="Browse and upload file"
				>
					📂 Browse
				</button>
			</div>

			<div
				className="import-presets"
				style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}
			>
				{TEST_FILES.map((f) => {
					const name = f.split("\\").pop() || "";
					return (
						<button
							key={f}
							className="btn-preset"
							onClick={() => doImport(f)}
							disabled={importing}
							style={{ fontSize: 12, padding: "4px 10px" }}
							title={f}
						>
							📄 {name.length > 45 ? name.slice(0, 45) + "..." : name}
						</button>
					);
				})}
			</div>

			{importError && <div className="error-banner">{importError}</div>}

			{loading ? (
				<p className="muted">Loading...</p>
			) : books.length === 0 ? (
				<p className="muted">
					No books yet. Import an .epub or .txt file above.
				</p>
			) : (
				<table className="book-table">
					<thead>
						<tr>
							<th>Title</th>
							<th>Author</th>
							<th>Status</th>
							<th>Progress</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{books.map((book) => (
							<tr
								key={book.id}
								className={selectedBook?.id === book.id ? "selected" : ""}
							>
								<td>{book.title || "—"}</td>
								<td>{book.author || "—"}</td>
								<td>
									<span className={`status-badge ${book.status}`}>
										{book.status}
									</span>
								</td>
								<td>
									{book.total_chunks > 0
										? `${book.done_chunks}/${book.total_chunks}`
										: "—"}
								</td>
								<td>
									<button onClick={() => onSelectBook(book)}>Translate</button>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			)}
		</div>
	);
}
