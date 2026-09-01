import { useState } from "react";
import type { Book } from "../api";
import { exportBook } from "../api";

interface ExportTabProps {
	selectedBook: Book | null;
}

export function ExportTab({ selectedBook }: ExportTabProps) {
	const [mode, setMode] = useState<"translated" | "bilingual">("translated");
	const [format, setFormat] = useState<"txt" | "epub">("txt");
	const [chapterStart, setChapterStart] = useState(1);
	const [chapterEnd, setChapterEnd] = useState(99999);
	const [outputPath, setOutputPath] = useState("");
	const [exporting, setExporting] = useState(false);
	const [result, setResult] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	if (!selectedBook) return <p className="muted">Select a book before exporting.</p>;

	const handleExport = async () => {
		setExporting(true);
		setError(null);
		setResult(null);
		try {
			const response = await exportBook(selectedBook.id, {
				output_path: outputPath,
				mode,
				format,
				chapter_start: Math.max(1, chapterStart),
				chapter_end: Math.min(chapterEnd, 99999),
			});
			setResult(response.path);
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setExporting(false);
		}
	};

	return (
		<div className="export-tab">
			<div className="workspace-intro compact-intro">
				<div>
					<span className="section-index">OUT / ACTIVE</span>
					<strong>Delivery package</strong>
					<p>Export the active document with the selected range, format and source-preservation mode.</p>
				</div>
				<div className="mode-readout"><span>Format</span><strong>{format.toUpperCase()}</strong></div>
			</div>
			<div className="section-bar">
				<div><span className="section-index">01</span><strong>Output contract</strong></div>
				<span>EPUB source structure is preserved when the original EPUB is available.</span>
			</div>

			<div className="review-fields export-grid">
				<label>
					Mode
					<select value={mode} onChange={(event) => setMode(event.target.value as "translated" | "bilingual")}>
						<option value="translated">Translated only</option>
						<option value="bilingual">Bilingual source + translation</option>
					</select>
				</label>
				<label>
					Format
					<select value={format} onChange={(event) => setFormat(event.target.value as "txt" | "epub")}>
						<option value="txt">TXT</option>
						<option value="epub">EPUB</option>
					</select>
				</label>
				<label>
					From chapter
					<input type="number" min={1} value={chapterStart} onChange={(event) => setChapterStart(Number(event.target.value) || 1)} />
				</label>
				<label>
					To chapter
					<input
						type="number"
						min={1}
						value={chapterEnd >= 99999 ? "" : chapterEnd}
						placeholder="end"
						onChange={(event) => setChapterEnd(event.target.value ? Number(event.target.value) : 99999)}
					/>
				</label>
			</div>

			<div className="setting-group">
				<label>
					Output path or filename
					<input
						value={outputPath}
						onChange={(event) => setOutputPath(event.target.value)}
						placeholder={`Default: ${selectedBook.title || "untitled"} - ${selectedBook.author || "unknown"}.${format}`}
					/>
				</label>
				<p className="hint">Leave empty to use the backend generated name.</p>
			</div>

			<div className="dispatch-bar export-dispatch">
				<div>
					<span className="section-index">02 / Write</span>
					<p>{mode === "bilingual" ? "Source and translation will be delivered together." : "Only translated content will be delivered."}</p>
				</div>
				<button className="btn-primary" onClick={() => void handleExport()} disabled={exporting}>
					{exporting ? "Exporting…" : `Export ${format.toUpperCase()}`}
				</button>
			</div>

			{error && <div className="error-banner">{error}</div>}
			{result && <div className="success-banner"><span>Output written</span><code>{result}</code></div>}
		</div>
	);
}
