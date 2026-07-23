import { useState, useEffect } from 'react';
import type { Book } from '../api';
import { listBooks } from '../api';

interface ExportTabProps {
  selectedBook: Book | null;
}

export function ExportTab({ selectedBook }: ExportTabProps) {
  const [books, setBooks] = useState<Book[]>([]);
  const [bookId, setBookId] = useState(selectedBook?.id || 0);
  const [mode, setMode] = useState('translated');
  const [format, setFormat] = useState('txt');
  const [chapterStart, setChapterStart] = useState(1);
  const [chapterEnd, setChapterEnd] = useState(99999);
  const [outputPath, setOutputPath] = useState('');
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBooks().then(setBooks).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedBook) setBookId(selectedBook.id);
  }, [selectedBook]);

  const handleExport = async () => {
    if (!bookId) return;
    setExporting(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('http://127.0.0.1:8080/api/export/' + bookId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_path: outputPath,
          mode,
          format,
          chapter_start: Math.max(1, chapterStart),
          chapter_end: Math.min(chapterEnd, 99999),
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
      }
      const data = await res.json();
      setResult(data.path);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
    setExporting(false);
  };

  const currentBook = books.find((b) => b.id === bookId);

  return (
    <div className="export-tab">
      <h2>📦 Export</h2>

      <div className="setting-group">
        <label>Book</label>
        <select value={bookId} onChange={(e) => setBookId(parseInt(e.target.value))}>
          <option value={0}>— Select —</option>
          {books.map((b) => (
            <option key={b.id} value={b.id}>
              {b.title || 'Untitled'} ({b.done_chunks}/{b.total_chunks} done)
            </option>
          ))}
        </select>
      </div>

      {currentBook && (
        <>
          <div className="setting-group">
            <label>Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="translated">📄 Chỉ bản dịch</option>
              <option value="bilingual">🌐 Song ngữ (gốc + dịch)</option>
            </select>
          </div>

          <div className="setting-group">
            <label>Format</label>
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="txt">📃 .txt</option>
              <option value="epub">📚 .epub</option>
            </select>
          </div>

          <div className="setting-group" style={{ display: 'flex', gap: 12 }}>
            <label>
              From Chapter:
              <input type="number" min={1} value={chapterStart} onChange={(e) => setChapterStart(parseInt(e.target.value) || 1)} style={{ width: 60, marginLeft: 4 }} />
            </label>
            <label>
              To Chapter:
              <input type="number" min={1} value={chapterEnd >= 99999 ? '' : chapterEnd} placeholder="End"
                onChange={(e) => setChapterEnd(e.target.value ? parseInt(e.target.value) : 99999)} style={{ width: 60 }} />
            </label>
          </div>

          <div className="setting-group">
            <label>Output filename (optional)</label>
            <input
              type="text"
              placeholder={`Default: ${(currentBook.title || 'untitled')} - ${(currentBook.author || 'unknown')}.${format}`}
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
            />
            <p className="hint">Leave empty for auto-generated name.</p>
          </div>

          <button className="btn-primary" onClick={handleExport} disabled={exporting}>
            {exporting ? '⏳ Exporting...' : '📦 Export'}
          </button>

          {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
          {result && (
            <div className="success-banner" style={{ marginTop: 12 }}>
              ✅ Exported: {result}
            </div>
          )}
        </>
      )}
    </div>
  );
}
