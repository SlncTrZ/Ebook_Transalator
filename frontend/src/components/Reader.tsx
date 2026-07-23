import { useState, useEffect } from 'react';
import type { ReaderChunk } from '../api';
import { getReaderChunks } from '../api';

interface ReaderProps {
  bookId: number | null;
}

export function Reader({ bookId }: ReaderProps) {
  const [chunks, setChunks] = useState<ReaderChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [chapterStart, setChapterStart] = useState(1);
  const [chapterEnd, setChapterEnd] = useState(5);
  const [statusFilter, setStatusFilter] = useState('all');

  const load = async () => {
    if (!bookId) return;
    setLoading(true);
    try {
      const data = await getReaderChunks(bookId, chapterStart, chapterEnd, statusFilter);
      setChunks(data.chunks);
    } catch (e) {
      console.error('Reader load failed', e);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (bookId) load();
    else setChunks([]);
  }, [bookId]);

  // Group by chapter
  const byChapter: Record<number, ReaderChunk[]> = {};
  for (const c of chunks) {
    (byChapter[c.chapter_idx] ??= []).push(c);
  }
  const chapterIdxs = Object.keys(byChapter).map(Number).sort((a, b) => a - b);

  if (!bookId) {
    return (
      <div className="reader">
        <h2>📖 Reader</h2>
        <p className="muted">Chọn sách từ Library để đọc song ngữ.</p>
      </div>
    );
  }

  return (
    <div className="reader">
      <h2>📖 Reader</h2>

      <div className="reader-controls" style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <label style={{ fontSize: 13, color: '#8b949e' }}>
          Chapter:
          <input type="number" min={1} value={chapterStart} onChange={(e) => setChapterStart(Math.max(1, parseInt(e.target.value) || 1))} style={{ width: 50, marginLeft: 4 }} />
          →
          <input type="number" min={1} value={chapterEnd >= 99999 ? '' : chapterEnd} placeholder="end" onChange={(e) => setChapterEnd(e.target.value ? parseInt(e.target.value) : 99999)} style={{ width: 50 }} />
        </label>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">Tất cả</option>
          <option value="done">Đã dịch</option>
          <option value="pending">Chưa dịch</option>
          <option value="failed">Lỗi</option>
        </select>
        <button onClick={load} disabled={loading}>🔄 Load</button>
      </div>

      {loading ? (
        <p className="muted">Đang tải...</p>
      ) : chunks.length === 0 ? (
        <p className="muted">Không có dữ liệu. Chọn chapter range và bấm Load.</p>
      ) : (
        <div className="reader-content">
          {chapterIdxs.map((chIdx) => (
            <div key={chIdx} className="chapter-block">
              <h3 style={{ color: '#58a6ff', fontSize: 15, margin: '16px 0 8px', paddingBottom: 4, borderBottom: '1px solid #30363d' }}>
                Chapter {chIdx + 1}
              </h3>
              {byChapter[chIdx].map((chunk) => (
                <div key={chunk.id} className="bilingual-pair" style={{ marginBottom: 12, padding: 12, background: '#0d1117', borderRadius: 6, border: '1px solid #21262d' }}>
                  <div className="original-text" style={{ fontSize: 13, color: '#8b949e', lineHeight: 1.7, marginBottom: 8, padding: 8, background: '#161b22', borderRadius: 4 }}>
                    {chunk.original_text}
                  </div>
                  <div className="translated-text" style={{ fontSize: 14, color: chunk.translated_text ? '#e1e4e8' : '#f85149', lineHeight: 1.7 }}>
                    {chunk.translated_text || (
                      <span className="muted">
                        {chunk.status === 'pending' ? '⏳ Chưa dịch' : chunk.status === 'failed' ? '❌ Lỗi' : '—'}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
