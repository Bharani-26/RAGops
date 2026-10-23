import React, { useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "../services/api";

type ClearScope = "documents" | "telemetry" | "evaluations" | "all";

interface ClearDataButtonProps {
  scope: ClearScope;
  label?: string;
  onCleared?: () => void;
}

export const ClearDataButton: React.FC<ClearDataButtonProps> = ({
  scope,
  label = "Clear data",
  onCleared,
}) => {
  const [clearing, setClearing] = useState(false);

  const clear = async () => {
    const confirmed = window.confirm(
      scope === "all"
        ? "Clear all runtime data? Uploaded documents, telemetry, and saved evaluation runs will be deleted. Version-controlled evaluation fixtures will remain."
        : `Clear all ${scope} data? This cannot be undone.`
    );
    if (!confirmed) return;

    setClearing(true);
    try {
      await api.clearData(scope);
      onCleared?.();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Failed to clear data.");
    } finally {
      setClearing(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void clear()}
      disabled={clearing}
      className="flex items-center gap-2 rounded-lg border border-rose-800/60 bg-rose-950/30 px-3 py-2 text-xs text-rose-300 hover:bg-rose-900/40 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Trash2 className="h-3.5 w-3.5" />
      {clearing ? "Clearing..." : label}
    </button>
  );
};
