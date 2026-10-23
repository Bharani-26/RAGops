import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentChatPage } from "./pages/DocumentChatPage";
import { TracesPage } from "./pages/TracesPage";
import { EvaluationsPage } from "./pages/EvaluationsPage";
import { CostAnalyticsPage } from "./pages/CostAnalyticsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { DocumentExplorerPage } from "./pages/DocumentExplorerPage";
import { api } from "./services/api";

const Layout: React.FC<{ children: React.ReactNode; apiStatus: "online" | "offline" | "checking" }> = ({
  children,
  apiStatus,
}) => {
  const location = useLocation();

  const getPageMeta = () => {
    switch (location.pathname) {
      case "/":
        return { title: "Observability Dashboard", subtitle: "Real-time pipeline metrics and telemetry" };
      case "/chat":
        return { title: "Document Chat & Playground", subtitle: "Ingest documents and test grounded Q&A with citations" };
      case "/documents":
        return { title: "Document Explorer", subtitle: "Inspect chunks and metadata persisted in ChromaDB" };
      case "/traces":
        return { title: "Request Traces", subtitle: "Inspect retrieval latency, waterfalls, and execution stages" };
      case "/evaluations":
        return { title: "RAG Evaluations", subtitle: "Benchmark context relevance, faithfulness, and answer accuracy" };
      case "/costs":
        return { title: "Cost Analytics", subtitle: "Monitor model usage and estimated token spending" };
      case "/settings":
        return { title: "Platform Settings", subtitle: "Application configurations, vector parameters, and model status" };
      default:
        return { title: "RAGOps", subtitle: "AI Observability Platform" };
    }
  };

  const meta = getPageMeta();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0a0f1d] text-slate-100">
      <Sidebar apiStatus={apiStatus} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title={meta.title} subtitle={meta.subtitle} />
        <main className="flex-1 flex overflow-hidden">{children}</main>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

  useEffect(() => {
    const checkApi = async () => {
      try {
        await api.checkHealth();
        setApiStatus("online");
      } catch {
        setApiStatus("offline");
      }
    };
    checkApi();
    const interval = setInterval(checkApi, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <BrowserRouter>
      <Layout apiStatus={apiStatus}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/chat" element={<DocumentChatPage />} />
          <Route path="/documents" element={<DocumentExplorerPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/costs" element={<CostAnalyticsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
};

export default App;
