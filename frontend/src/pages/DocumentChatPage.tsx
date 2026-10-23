import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import {
  UploadCloud,
  FileText,
  Send,
  Trash2,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  FileUp,
  FileCode,
  BookOpen,
  Info,
  Layers,
  Database,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Paperclip,
  Sparkles,
  Bot,
  User,
  PanelLeftClose,
  PanelLeftOpen,
  HelpCircle,
} from "lucide-react";
import { api } from "../services/api";
import { ChunkMetadata, IndexedDocument } from "../types/api";

interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  sources?: ChunkMetadata[];
  requestId?: string;
  isError?: boolean;
  failedQuery?: string;
}

type FileUploadStatus = "idle" | "uploading" | "indexing" | "ready" | "failed";

export const DocumentChatPage: React.FC = () => {
  // Document panel state
  const [showDocPanel, setShowDocPanel] = useState<boolean>(true);
  const [documents, setDocuments] = useState<IndexedDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState<boolean>(true);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileStatus, setFileStatus] = useState<FileUploadStatus>("idle");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Chat conversation state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const fetchDocuments = async () => {
    setLoadingDocs(true);
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (err: any) {
      console.error("Failed to load documents", err);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file: File) => {
    setStatusMessage(null);
    const validExts = [".txt", ".pdf"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!validExts.includes(ext)) {
      setFileStatus("failed");
      setStatusMessage("Invalid format. Only .txt and .pdf documents are supported.");
      setSelectedFile(null);
      return;
    }
    if (file.size === 0) {
      setFileStatus("failed");
      setStatusMessage("The selected file is empty (0 bytes).");
      setSelectedFile(null);
      return;
    }
    setFileStatus("idle");
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setFileStatus("uploading");
    setStatusMessage("Extracting text and preparing chunks...");

    try {
      setFileStatus("indexing");
      setStatusMessage("Generating Gemini embeddings & persisting to ChromaDB...");
      const res = await api.uploadDocument(selectedFile);
      setFileStatus("ready");
      setStatusMessage(`Indexed "${res.filename}" into vector store (${res.total_chunks} chunks).`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await fetchDocuments();
    } catch (err: any) {
      setFileStatus("failed");
      setStatusMessage(err.message || "Failed to process and index document.");
    }
  };

  const submitQuery = async (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed || isSending) return;

    if (documents.length === 0) {
      const warningMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: "ai",
        text: "Please upload and index a document in the left panel before querying the RAG pipeline.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        isError: true,
      };
      setMessages((prev) => [...prev, warningMsg]);
      return;
    }

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      sender: "user",
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setIsSending(true);

    try {
      const response = await api.queryRag({ query: trimmed });
      const aiMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: "ai",
        text: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        sources: response.sources,
        requestId: response.request_id,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: "ai",
        text: `Error: ${err.message || "Failed to process query through the RAG pipeline."}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        isError: true,
        failedQuery: trimmed,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuery(inputText);
    }
  };

  const toggleSourceExpansion = (messageId: string) => {
    setExpandedSources((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  };

  const handleClearChat = () => {
    if (messages.length === 0) return;
    if (window.confirm("Are you sure you want to clear this conversation?")) {
      setMessages([]);
      setExpandedSources({});
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="flex-1 flex overflow-hidden relative">
      {/* Document Ingestion & Storage Sidebar */}
      <section
        className={`${
          showDocPanel ? "w-80 border-r border-slate-800/80" : "w-0 border-none overflow-hidden"
        } transition-all duration-300 bg-[#0c1424] flex flex-col justify-between shrink-0 z-10`}
      >
        <div className="p-5 flex-1 overflow-y-auto">
          {/* Panel Header */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-400" />
              Document Knowledge
            </h2>
            <div className="flex items-center gap-1">
              <button
                onClick={fetchDocuments}
                className="text-slate-400 hover:text-slate-200 p-1 transition-colors rounded hover:bg-slate-800/60"
                title="Refresh documents"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingDocs ? "animate-spin" : ""}`} />
              </button>
              <button
                onClick={() => setShowDocPanel(false)}
                className="text-slate-400 hover:text-slate-200 p-1 transition-colors rounded hover:bg-slate-800/60 md:hidden"
                title="Collapse sidebar"
              >
                <PanelLeftClose className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Drag & Drop Upload Container */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all ${
              isDragging
                ? "border-blue-500 bg-blue-950/40 scale-[0.99]"
                : "border-slate-700/70 hover:border-blue-500/50 bg-[#090f1d]/80"
            }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".txt,.pdf"
              className="hidden"
            />
            <div className="w-10 h-10 mx-auto rounded-xl bg-blue-950 border border-blue-800/40 flex items-center justify-center mb-2.5 text-blue-400">
              <UploadCloud className="w-5 h-5" />
            </div>
            <p className="text-xs font-medium text-slate-200 mb-0.5 truncate px-2">
              {selectedFile ? selectedFile.name : "Drag & drop PDF or TXT"}
            </p>
            <p className="text-[11px] text-slate-400">
              {selectedFile ? formatFileSize(selectedFile.size) : "or click to browse files"}
            </p>
          </div>

          {/* Action Button & Status Pill */}
          {selectedFile && (
            <div className="mt-3">
              <button
                onClick={handleUpload}
                disabled={fileStatus === "uploading" || fileStatus === "indexing"}
                className="w-full py-2.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all shadow-md shadow-blue-600/25 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {fileStatus === "uploading" || fileStatus === "indexing" ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>{fileStatus === "uploading" ? "Uploading & Extracting..." : "Embedding Chunks..."}</span>
                  </>
                ) : (
                  <>
                    <FileUp className="w-3.5 h-3.5" />
                    <span>Index into ChromaDB</span>
                  </>
                )}
              </button>
            </div>
          )}

          {/* Explicit Status Banners */}
          {statusMessage && (
            <div
              className={`mt-3 p-2.5 rounded-lg text-xs flex items-start gap-2 border ${
                fileStatus === "failed"
                  ? "bg-rose-950/40 border-rose-800/50 text-rose-300"
                  : fileStatus === "ready"
                  ? "bg-emerald-950/40 border-emerald-800/50 text-emerald-300"
                  : "bg-blue-950/40 border-blue-800/50 text-blue-300"
              }`}
            >
              {fileStatus === "failed" ? (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              ) : fileStatus === "ready" ? (
                <CheckCircle className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
              ) : (
                <RefreshCw className="w-4 h-4 shrink-0 mt-0.5 animate-spin text-blue-400" />
              )}
              <span className="leading-tight">{statusMessage}</span>
            </div>
          )}

          {/* Indexed Knowledge List */}
          <div className="mt-6">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center justify-between">
              <span>Indexed Documents ({documents.length})</span>
            </div>

            {loadingDocs ? (
              <div className="py-6 text-center text-xs text-slate-400">Loading documents...</div>
            ) : documents.length === 0 ? (
              <div className="p-4 rounded-xl bg-[#090f1d]/50 border border-slate-800/60 text-center">
                <BookOpen className="w-6 h-6 mx-auto text-slate-600 mb-1.5" />
                <p className="text-xs text-slate-400 font-medium">No documents indexed</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Upload a PDF or TXT above to begin querying.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {documents.map((doc) => (
                  <div
                    key={doc.filename}
                    className="p-2.5 rounded-lg bg-[#0e172a] border border-slate-800/90 hover:border-slate-700 transition-all flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2.5 overflow-hidden">
                      <div className="w-7 h-7 rounded bg-blue-950/80 border border-blue-900/50 flex items-center justify-center shrink-0 text-blue-400">
                        {doc.filename.endsWith(".pdf") ? (
                          <FileText className="w-3.5 h-3.5" />
                        ) : (
                          <FileCode className="w-3.5 h-3.5" />
                        )}
                      </div>
                      <div className="truncate">
                        <p className="text-xs text-slate-200 font-medium truncate" title={doc.filename}>
                          {doc.filename}
                        </p>
                        <p className="text-[10px] text-slate-400">{formatFileSize(doc.size_bytes)}</p>
                      </div>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" title="Ready & Indexed"></span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Panel Footer Specs */}
        <div className="p-4 border-t border-slate-800/80 bg-[#090f1d]">
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <Info className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <span>Chunk size: 500 chars • Overlap: 50 chars</span>
          </div>
        </div>
      </section>

      {/* Main Conversation Stream */}
      <section className="flex-1 flex flex-col bg-[#0a0f1d] overflow-hidden">
        {/* Chat Control Toolbar */}
        <div className="h-12 px-6 border-b border-slate-800/80 bg-[#0c1424]/70 backdrop-blur-md flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowDocPanel(!showDocPanel)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
              title={showDocPanel ? "Collapse document panel" : "Expand document panel"}
            >
              {showDocPanel ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
            </button>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="font-medium text-slate-300">Model:</span>
              <span className="font-mono text-[11px] text-slate-400">
                gemini-3.8-flash • chroma-top-4
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setMessages([]);
                setExpandedSources({});
              }}
              className="text-xs px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 transition-all"
            >
              New Chat
            </button>
            <button
              onClick={handleClearChat}
              disabled={messages.length === 0}
              className="text-xs px-2.5 py-1 rounded-lg border border-slate-700/60 hover:bg-rose-950/30 hover:border-rose-800/60 text-slate-400 hover:text-rose-300 transition-all disabled:opacity-40 flex items-center gap-1.5"
            >
              <Trash2 className="w-3 h-3" />
              Clear
            </button>
          </div>
        </div>

        {/* Message Stream or Centered Welcome Screen */}
        <div className="flex-1 p-6 md:p-8 overflow-y-auto space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto py-8">
              <div className="w-16 h-16 rounded-2xl bg-[#2f8f83]/15 border border-[#2f8f83]/40 flex items-center justify-center mb-4 text-[#5bb7aa] shadow-xl shadow-teal-900/10">
                <Sparkles className="w-8 h-8" />
              </div>
              <h2 className="text-xl font-bold text-slate-100 tracking-tight mb-2">
                Ask Questions Grounded in Your Knowledge Base
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed max-w-md mb-8">
                RAGOps pairs persistent Chroma vector retrieval with Gemini LLMs to synthesize accurate, fact-grounded
                answers without hallucinations.
              </p>

            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 max-w-4xl ${
                  msg.sender === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                }`}
              >
                {/* Avatar */}
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-semibold ${
                    msg.sender === "user"
                      ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                      : "bg-[#131d33] border border-blue-900/50 text-blue-400 shadow-md"
                  }`}
                >
                  {msg.sender === "user" ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                {/* Message Body */}
                <div className={`space-y-1.5 max-w-[85%] ${msg.sender === "user" ? "items-end" : "items-start"}`}>
                  <div className="flex items-center gap-2 px-1">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                      {msg.sender === "user" ? "You" : "RAGOps Assistant"}
                    </span>
                    <span className="text-[10px] text-slate-400">{msg.timestamp}</span>
                  </div>

                  <div
                    className={`rounded-2xl p-4.5 text-sm leading-relaxed ${
                      msg.sender === "user"
                        ? "bg-blue-600 text-white rounded-tr-none shadow-md shadow-blue-600/10"
                        : msg.isError
                        ? "bg-rose-950/40 border border-rose-800/60 text-rose-200 rounded-tl-none shadow-md"
                        : "bg-[#11192e] text-slate-100 border border-slate-800 rounded-tl-none shadow-md"
                    }`}
                  >
                    {msg.sender === "user" ? (
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                    ) : (
                      <div className="prose prose-invert prose-sm max-w-none space-y-2">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                            code: ({ children }) => (
                              <code className="bg-[#090f1d] px-1.5 py-0.5 rounded text-blue-300 font-mono text-xs border border-slate-800">
                                {children}
                              </code>
                            ),
                            pre: ({ children }) => (
                              <pre className="bg-[#090f1d] p-3 rounded-lg overflow-x-auto text-xs font-mono border border-slate-800 my-2">
                                {children}
                              </pre>
                            ),
                          }}
                        >
                          {msg.text}
                        </ReactMarkdown>
                      </div>
                    )}

                    {/* Retry control for error messages */}
                    {msg.isError && msg.failedQuery && (
                      <div className="mt-3 pt-2.5 border-t border-rose-800/40 flex items-center justify-between">
                        <span className="text-xs text-rose-300">Request failed to complete.</span>
                        <button
                          onClick={() => submitQuery(msg.failedQuery!)}
                          disabled={isSending}
                          className="px-2.5 py-1 rounded bg-rose-900/60 hover:bg-rose-800 text-rose-200 text-xs font-medium transition-all flex items-center gap-1.5"
                        >
                          <RotateCcw className="w-3 h-3" />
                          Retry Query
                        </button>
                      </div>
                    )}

                    {/* Expandable Sources & Citations */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-4 pt-3 border-t border-slate-700/60">
                        <button
                          onClick={() => toggleSourceExpansion(msg.id)}
                          className="w-full flex items-center justify-between text-xs font-medium text-slate-300 hover:text-white transition-colors"
                        >
                          <span className="flex items-center gap-1.5">
                            <BookOpen className="w-3.5 h-3.5 text-blue-400" />
                            Grounded Citations ({msg.sources.length})
                          </span>
                          {expandedSources[msg.id] ? (
                            <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </button>

                        {expandedSources[msg.id] && (
                          <div className="mt-3 space-y-2 transition-all">
                            {msg.sources.map((src, idx) => (
                              <div
                                key={idx}
                                className="p-3 rounded-xl bg-[#090f1d] border border-slate-800 text-xs space-y-1.5"
                              >
                                <div className="flex items-center justify-between font-mono text-[11px] text-blue-300">
                                  <span className="truncate max-w-[200px]" title={src.source}>
                                    📄 {src.source}
                                  </span>
                                  <span className="text-slate-400 text-[10px]">
                                    Chunk {src.chunk_index + 1} of {src.total_chunks}
                                  </span>
                                </div>
                                <p className="text-slate-300 text-[11px] leading-relaxed italic bg-slate-900/40 p-2 rounded-lg border border-slate-800/60">
                                  "{src.content_preview}"
                                </p>
                              </div>
                            ))}
                            {msg.requestId && (
                              <p className="text-[10px] text-slate-400 font-mono text-right pt-1">
                                Trace ID: {msg.requestId}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}

          {/* Loading Animation Pill */}
          {isSending && (
            <div className="flex gap-3 max-w-4xl mr-auto">
              <div className="w-8 h-8 rounded-lg bg-[#131d33] border border-blue-900/50 flex items-center justify-center text-blue-400 shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-[#11192e] border border-slate-800 rounded-2xl rounded-tl-none p-4 text-xs text-slate-300 flex items-center gap-3 shadow-md">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 rounded-full bg-blue-500 animate-bounce"></div>
                  <div
                    className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce"
                    style={{ animationDelay: "0.2s" }}
                  ></div>
                  <div
                    className="w-2 h-2 rounded-full bg-blue-400 animate-bounce"
                    style={{ animationDelay: "0.4s" }}
                  ></div>
                </div>
                <span>Retrieving relevant chunks & synthesizing grounded answer...</span>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Multiline Chat Input Bar */}
        <div className="p-4 md:p-6 border-t border-slate-800/80 bg-[#0c1424]">
          <div className="max-w-4xl mx-auto">
            <div className="relative rounded-2xl border border-slate-700/80 bg-[#090f1d] focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all shadow-lg flex flex-col">
              <textarea
                ref={textareaRef}
                rows={2}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about the uploaded documents... (Enter to send, Shift+Enter for new line)"
                className="w-full bg-transparent p-3.5 pr-20 text-sm text-slate-100 placeholder-slate-400 resize-none focus:outline-none"
              />

              <div className="px-3 pb-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setShowDocPanel(true);
                      fileInputRef.current?.click();
                    }}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                    title="Attach & upload document"
                  >
                    <Paperclip className="w-4 h-4" />
                  </button>
                  <span className="text-[11px] text-slate-400 hidden sm:inline">
                    Grounded in ChromaDB • Hallucination Suppressed
                  </span>
                </div>

                <button
                  onClick={() => submitQuery(inputText)}
                  disabled={!inputText.trim() || isSending}
                  className="px-4 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-all disabled:opacity-30 disabled:hover:bg-blue-600 shadow-md shadow-blue-600/30 flex items-center gap-1.5"
                >
                  <span>Send</span>
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="mt-2 text-[11px] text-slate-400 text-center flex items-center justify-center gap-4">
              <span>Enter to send • Shift + Enter for new line</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
