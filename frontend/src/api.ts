/** API client for Ebook Translator backend. */
const API_BASE = "http://127.0.0.1:8080/api";

export interface Book {
	id: number;
	file_path: string;
	title: string;
	author: string;
	localized_title: string;
	source_lang: string;
	target_lang: string;
	category: string;
	status: string;
	total_chunks: number;
	done_chunks: number;
	failed_chunks: number;
}

export interface Chunk {
	id: number;
	chapter_idx: number;
	paragraph_idx: number;
	status: string;
	token_count: number;
	error_log: string | null;
}

export interface GlossaryItem {
	id: number;
	source_term: string;
	target_term: string;
	notes: string;
}

export interface ProgressData {
	total: number;
	done: number;
	failed: number;
	status: string;
}

export interface MetadataResult {
	title: string;
	author: string;
	source_lang: string;
	target_lang: string;
	localized_title: string;
	category: string;
	description: string;
	style_notes?: string;
	confidence: number;
	sources: string[];
	from_knowledge: boolean;
}

export interface CategoryInfo {
	[key: string]: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, {
		headers: { "Content-Type": "application/json" },
		...options,
	});
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`API error ${res.status}: ${text}`);
	}
	return res.json();
}

// Books
export const listBooks = () => request<Book[]>("/books");
export const getBook = (id: number) => request<Book>(`/books/${id}`);
export const createBook = (filePath: string) =>
	request<{ id: number; title: string; chunks: number; status: string }>(
		"/books",
		{ method: "POST", body: JSON.stringify({ file_path: filePath }) },
	);

export const uploadBook = (file: File) => {
	const formData = new FormData();
	formData.append("file", file);
	return fetch(`${API_BASE}/books/upload`, {
		method: "POST",
		body: formData,
	}).then(async (res) => {
		if (!res.ok) {
			const text = await res.text();
			throw new Error(text);
		}
		return res.json() as Promise<{
			id: number;
			title: string;
			chunks: number;
			status: string;
		}>;
	});
};
export const updateBook = (id: number, data: Partial<Book>) =>
	request<{ ok: boolean }>(`/books/${id}`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});

export const deleteBook = (id: number) =>
	request<{ ok: boolean }>(`/books/${id}`, { method: "DELETE" });

export const researchBook = (
	bookId: number,
	vendor: string,
	apiKey: string,
	model: string,
	userFeedback = "",
	forceSearch = false,
) =>
	request<MetadataResult>(`/books/${bookId}/research`, {
		method: "POST",
		body: JSON.stringify({
			vendor,
			api_key: apiKey,
			model,
			user_feedback: userFeedback,
			force_search: forceSearch,
		}),
	});

export const confirmMetadata = (
	bookId: number,
	data: {
		title: string;
		author: string;
		localized_title: string;
		source_lang: string;
		target_lang: string;
		category: string;
	},
) =>
	request<{ ok: boolean }>(`/books/${bookId}/confirm-metadata`, {
		method: "POST",
		body: JSON.stringify(data),
	});

// Chunks
export const listChunks = (bookId: number, status?: string) => {
	const qs = status ? `?status=${status}` : "";
	return request<Chunk[]>(`/books/${bookId}/chunks${qs}`);
};

// Glossary
export const getGlossary = (bookId: number) =>
	request<GlossaryItem[]>(`/books/${bookId}/glossary`);
export const createGlossary = (
	bookId: number,
	source: string,
	target: string,
	notes = "",
) =>
	request<{ id: number }>("/glossary", {
		method: "POST",
		body: JSON.stringify({
			book_id: bookId,
			source_term: source,
			target_term: target,
			notes,
		}),
	});
export const deleteGlossary = (id: number) =>
	request<{ ok: boolean }>(`/glossary/${id}`, { method: "DELETE" });

// Translation
export interface Vendor {
	id: string;
	name: string;
	base_url: string;
	default_model: string;
	models: string[];
	requires_api_key: boolean;
	docs_url: string;
}

export interface TranslationStartResponse {
	book_id: number;
	job_id: number;
	status: "started";
	mode: "standard" | "agentic";
}

function buildTranslationPayload(
	filePath: string,
	vendor: string,
	apiKey: string,
	model: string,
	category: string,
	chapterStart: number,
	chapterEnd: number,
) {
	return {
		file_path: filePath,
		vendor,
		api_key: apiKey,
		model,
		category,
		chapter_start: chapterStart,
		chapter_end: chapterEnd,
	};
}

export const startStandardTranslation = (
	filePath: string,
	vendor: string,
	apiKey: string,
	model: string,
	category: string,
	chapterStart = 0,
	chapterEnd = 99999,
) =>
	request<TranslationStartResponse>("/translate/start", {
		method: "POST",
		body: JSON.stringify(
			buildTranslationPayload(
				filePath,
				vendor,
				apiKey,
				model,
				category,
				chapterStart,
				chapterEnd,
			),
		),
	});

export const startAgenticTranslation = (
	filePath: string,
	vendor: string,
	apiKey: string,
	model: string,
	category: string,
	chapterStart = 0,
	chapterEnd = 99999,
) =>
	request<TranslationStartResponse>("/translate/agentic", {
		method: "POST",
		body: JSON.stringify(
			buildTranslationPayload(
				filePath,
				vendor,
				apiKey,
				model,
				category,
				chapterStart,
				chapterEnd,
			),
		),
	});

export const cancelTranslate = () =>
	request<{ status: string }>("/translate/cancel", { method: "POST" });

export const translateProgress = (
	bookId: number,
	chapterStart: number,
	chapterEnd: number,
	onProgress: (data: ProgressData) => void,
	onComplete: () => void,
	onError: (err: string) => void,
) => {
	// Polling thay vi SSE (tranh loi Connection lost)
	let cancelled = false;
	const poll = async () => {
		if (cancelled) return;
		try {
			const data = await request<ProgressData>(
				`/translate/status/${bookId}?chapter_start=${chapterStart}&chapter_end=${chapterEnd}`,
			);
			onProgress(data);
			if (data.status === "done" || data.status === "failed") {
				onComplete();
				return;
			}
		} catch (e) {
			onError("Connection lost");
			return;
		}
		if (!cancelled) setTimeout(poll, 1500);
	};
	setTimeout(poll, 500);
	return () => {
		cancelled = true;
	};
};

// Export
export const exportBook = (
	bookId: number,
	options: {
		output_path?: string;
		mode?: "translated" | "bilingual";
		format?: "txt" | "epub";
		chapter_start?: number;
		chapter_end?: number;
	} = {},
) =>
	request<{ path: string; mode: string; format: string }>(`/export/${bookId}`, {
		method: "POST",
		body: JSON.stringify({
			output_path: options.output_path ?? "",
			mode: options.mode ?? "translated",
			format: options.format ?? "txt",
			chapter_start: options.chapter_start ?? 1,
			chapter_end: options.chapter_end ?? 99999,
		}),
	});

// Connection test
export const testConnection = (vendor: string, apiKey: string, model: string) =>
	request<{ status: string; reply?: string; detail?: string }>(
		"/test-connection",
		{
			method: "POST",
			body: JSON.stringify({ vendor, api_key: apiKey, model }),
		},
	);

// Fetch models from vendor API
export const fetchVendorModels = (vendorId: string, apiKey: string) =>
	request<string[]>("/vendors/" + vendorId + "/models", {
		method: "POST",
		body: JSON.stringify({ vendor: vendorId, api_key: apiKey }),
	});

// Config
export const listCategories = () => request<CategoryInfo>("/categories");
export const listVendors = () => request<Vendor[]>("/vendors");

// Reader
export interface ReaderChunk {
	id: number;
	chapter_idx: number;
	paragraph_idx: number;
	original_text: string;
	translated_text: string | null;
	status: string;
}
export const getReaderChunks = (
	bookId: number,
	chapterStart = 1,
	chapterEnd = 99999,
	statusFilter = "all",
) =>
	request<{ total: number; chapters: number[]; chunks: ReaderChunk[] }>(
		`/books/${bookId}/reader?chapter_start=${chapterStart}&chapter_end=${chapterEnd}&status_filter=${statusFilter}`,
	);
export const updateChunkTranslation = (chunkId: number, translatedText: string) =>
	request<{ ok: boolean; chunk_id: number }>(`/chunks/${chunkId}`, {
		method: "PATCH",
		body: JSON.stringify({ translated_text: translatedText }),
	});

export const rememberChunkTranslation = (chunkId: number, translatedText: string) =>
	request<{ ok: boolean; chunk_id: number; stored: string }>(
		`/chunks/${chunkId}/translation-memory`,
		{
			method: "POST",
			body: JSON.stringify({ translated_text: translatedText }),
		},
	);

export const requeueChunk = (chunkId: number) =>
	request<{ ok: boolean; chunk_id: number; status: string }>(
		`/chunks/${chunkId}/requeue`,
		{ method: "POST" },
	);

export const promptPreview = (category: string) =>
	request<{ category: string; prompt: string }>(`/prompt-preview/${category}`);
