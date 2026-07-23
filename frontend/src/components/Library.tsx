import { useState, useEffect } from 'react';
import type { Book } from '../api';
import { listBooks, createBook } from '../api';

interface LibraryProps {
  onSelectBook: (book: Book) => void;
  selectedBook: Book | null;
  onRefresh: () => void;
}

export function Library({ onSelectBook, selectedBook }: LibraryProps) {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [importPath, setImportPath] = useState('');

  const loadBooks = async () => {
    setLoading(true);
    try {
      const data = await listBooks();
      setBooks(data);
    } catch (e) {
      console.error('Failed to load books', e);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadBooks();
  }, []);

  const handleImport = async () => {
    if (!importPath.trim()) return;
    try {
      const result = await createBook(importPath.trim());
      await loadBooks();
      setImportPath('');
      console.log(`Imported: ${result.title} (${result.chunks} chunks)`);
    } catch (e) {
      console.error('Import failed', e);
      alert(`Import failed: ${e}`);
    }
  };

  return (
    <div className="library">
      <h2>📚 Book Library</h2>

      <div className="import-bar">
        <input
          type="text"
          placeholder="File path (.epub, .txt)..."
          value={importPath}
          onChange={(e) => setImportPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleImport()}
        />
        <button onClick={handleImport} disabled={!importPath.trim()}>
          + Import
        </button>
      </div>

      {loading ? (
        <p className="muted">Loading...</p>
      ) : books.length === 0 ? (
        <p className="muted">No books yet. Import an .epub or .txt file above.</p>
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
                className={selectedBook?.id === book.id ? 'selected' : ''}
              >
                <td>{book.title || '—'}</td>
                <td>{book.author || '—'}</td>
                <td>
                  <span className={`status-badge ${book.status}`}>
                    {book.status}
                  </span>
                </td>
                <td>
                  {book.total_chunks > 0
                    ? `${book.done_chunks}/${book.total_chunks}`
                    : '—'}
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
