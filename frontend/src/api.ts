/** API client for Ebook Translator backend. */
const API_BASE = "http://127.0.0.1:8080/api";

export interface Book {
	id: number;
	file_path: string;
	title: string;
	author: string;
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

export const startTranslate = (
	filePath: string,
	vendor: string,
	apiKey: string,
	model: string,
	category: string,
	chapterStart = 0,
	chapterEnd = 99999,
	agentic = false,
) =>
	request<{ book_id: number; status: string }>("/translate/start", {
		method: "POST",
		body: JSON.stringify({
			file_path: filePath,
			vendor,
			api_key: apiKey,
			model,
			category,
			chapter_start: chapterStart,
			chapter_end: chapterEnd,
			agentic,
		}),
	});

export const cancelTranslate = () =>
	request<{ status: string }>("/translate/cancel", { method: "POST" });

export const translateProgress = (
	bookId: number,
	onProgress: (data: ProgressData) => void,
	onComplete: () => void,
	onError: (err: string) => void,
) => {
	// Polling thay vi SSE (tranh loi Connection lost)
	let cancelled = false;
	const poll = async () => {
		if (cancelled) return;
		try {
			const data = await request<ProgressData>(`/translate/status/${bookId}`);
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
export const exportBook = (bookId: number) =>
	request<{ path: string }>(`/export/${bookId}`, { method: "POST" });

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
export const promptPreview = (category: string) =>
	request<{ category: string; prompt: string }>(`/prompt-preview/${category}`);
