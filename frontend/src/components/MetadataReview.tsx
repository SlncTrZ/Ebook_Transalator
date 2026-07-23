import { useState, useCallback } from 'react';
import type { Book } from '../api';

interface MetadataResult {
  title: string;
  author: string;
  source_lang: string;
  localized_title: string;
  category: string;
  description: string;
  confidence: number;
  sources: string[];
}

interface MetadataReviewProps {
  book: Book;
  apiKey: string;
  model: string;
  onStartTranslate: (bookId: number) => void;
}

const LANG_LABELS: Record<string, string> = {
  en: 'English', vi: 'Tiếng Việt', zh: '中文', ja: '日本語',
  ko: '한국어', fr: 'Français', de: 'Deutsch', es: 'Español',
  ru: 'Русский', th: 'ไทย',
};

const CATEGORY_LABELS: Record<string, string> = {
  van_hoc: 'Văn học', lich_su: 'Lịch sử', hien_dai: 'Hiện đại',
  tien_hiep: 'Tiên hiệp', general: 'Tổng hợp',
};

export function MetadataReview({ book, apiKey, model, onStartTranslate }: MetadataReviewProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [metadata, setMetadata] = useState<MetadataResult | null>(null);
  const [analyzed, setAnalyzed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  // Editable fields
  const [title, setTitle] = useState(book.title);
  const [author, setAuthor] = useState(book.author);
  const [category, setCategory] = useState(book.category || 'general');
  const [sourceLang, setSourceLang] = useState(book.source_lang || 'en');

  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const res = await fetch('http://127.0.0.1:8080/api/books/' + book.id + '/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, model }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: MetadataResult = await res.json();
      setMetadata(data);
      setTitle(data.title || book.title);
      setAuthor(data.author || book.author);
      setCategory(data.category || 'general');
      setSourceLang(data.source_lang || 'en');
      setAnalyzed(true);
    } catch (e) {
      setError(String(e));
    }
    setAnalyzing(false);
  }, [book.id, book.title, book.author, book.source_lang, apiKey, model]);

  const handleConfirm = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch('http://127.0.0.1:8080/api/books/' + book.id + '/confirm-metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, author, category, source_lang: sourceLang }),
      });
      if (!res.ok) throw new Error(await res.text());
      setConfirmed(true);
      onStartTranslate(book.id);
    } catch (e) {
      setError(String(e));
    }
  }, [book.id, title, author, category, sourceLang, onStartTranslate]);

  const handleSkip = useCallback(async () => {
    setConfirmed(true);
    onStartTranslate(book.id);
  }, [book.id, onStartTranslate]);

  if (confirmed) return null;

  return (
    <div className="metadata-review">
      <h3>🔍 Metadata Review</h3>
      <p className="hint">
        AI sẽ phân tích nội dung sách và đề xuất thông tin. 
        Bạn có thể chỉnh sửa trước khi xác nhận.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {!analyzed ? (
        <div className="review-actions">
          <button onClick={handleAnalyze} disabled={analyzing || !apiKey}>
            {analyzing ? '⏳ Analyzing...' : '🔍 Analyze Metadata'}
          </button>
          <button onClick={handleSkip}>⏭ Skip (use original)</button>
        </div>
      ) : metadata && (
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
              Title
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            {metadata.localized_title && (
              <div className="localized-hint">
                💡 Suggested: <strong>{metadata.localized_title}</strong>
              </div>
            )}
            <label>
              Author
              <input value={author} onChange={(e) => setAuthor(e.target.value)} />
            </label>
            <label>
              Source Language
              <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)}>
                {Object.entries(LANG_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label} ({code})</option>
                ))}
              </select>
            </label>
            <label>
              Category
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
            {metadata.description && (
              <div className="desc-hint">
                📝 {metadata.description}
              </div>
            )}
          </div>

          {metadata.sources.length > 0 && (
            <details className="sources">
              <summary>Sources ({metadata.sources.filter(Boolean).length})</summary>
              <ul>
                {metadata.sources.filter(Boolean).map((url, i) => (
                  <li key={i}><a href={url} target="_blank" rel="noopener noreferrer">{url}</a></li>
                ))}
              </ul>
            </details>
          )}

          <div className="review-actions">
            <button className="btn-primary" onClick={handleConfirm}>
              ✅ Confirm & Translate
            </button>
            <button onClick={handleSkip}>⏭ Skip</button>
          </div>
        </div>
      )}
    </div>
  );
}
