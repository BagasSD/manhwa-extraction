import React from "react";
import type { Scene } from "../../types/context";

interface ScenePanelProps {
  scene: Scene;
  onChange: (scene: Scene) => void;
  visualSummary?: string | null;
  onVisualSummaryChange?: (visualSummary: string | null) => void;
}

export const ScenePanel: React.FC<ScenePanelProps> = ({
  scene,
  onChange,
  visualSummary,
  onVisualSummaryChange,
}) => {
  const handleFieldChange = (field: keyof Scene, value: unknown) => {
    onChange({
      ...scene,
      [field]: value,
    });
  };

  const handleActionChange = (index: number, text: string) => {
    const updated = [...scene.actions];
    updated[index] = text;
    onChange({
      ...scene,
      actions: updated,
    });
  };

  const handleAddAction = () => {
    onChange({
      ...scene,
      actions: [...scene.actions, ""],
    });
  };

  const handleRemoveAction = (index: number) => {
    onChange({
      ...scene,
      actions: scene.actions.filter((_, i) => i !== index),
    });
  };

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", fontWeight: 700, color: "#1e293b" }}>
        Scene & Visual Context
      </h4>

      <div
        style={{
          border: "1px solid #e2e8f0",
          borderRadius: "6px",
          padding: "0.75rem",
          backgroundColor: "#ffffff",
          display: "grid",
          gap: "0.5rem",
        }}
      >
        {/* Visual Summary */}
        {onVisualSummaryChange !== undefined && (
          <div>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b", fontWeight: 600 }}>
              Visual Summary
            </label>
            <textarea
              rows={2}
              value={visualSummary || ""}
              placeholder="Factual visual summary (e.g. A lone warrior stands among ruins...)"
              onChange={(e) => onVisualSummaryChange(e.target.value || null)}
              style={{
                width: "100%",
                padding: "4px 6px",
                borderRadius: "4px",
                border: "1px solid #cbd5e1",
                fontSize: "0.85rem",
                boxSizing: "border-box",
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Location</label>
            <input
              type="text"
              value={scene.location || ""}
              placeholder="e.g. ruined building"
              onChange={(e) => handleFieldChange("location", e.target.value || null)}
              style={{
                width: "100%",
                padding: "4px 6px",
                borderRadius: "4px",
                border: "1px solid #cbd5e1",
                fontSize: "0.85rem",
                boxSizing: "border-box",
              }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Mood</label>
            <input
              type="text"
              value={scene.mood || ""}
              placeholder="e.g. tense, comedic"
              onChange={(e) => handleFieldChange("mood", e.target.value || null)}
              style={{
                width: "100%",
                padding: "4px 6px",
                borderRadius: "4px",
                border: "1px solid #cbd5e1",
                fontSize: "0.85rem",
                boxSizing: "border-box",
              }}
            />
          </div>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Situation</label>
          <textarea
            rows={2}
            value={scene.situation || ""}
            placeholder="e.g. c1 tries to stop c2 from leaving"
            onChange={(e) => handleFieldChange("situation", e.target.value || null)}
            style={{
              width: "100%",
              padding: "4px 6px",
              borderRadius: "4px",
              border: "1px solid #cbd5e1",
              fontSize: "0.85rem",
              boxSizing: "border-box",
              fontFamily: "inherit",
              resize: "vertical",
            }}
          />
        </div>

        {/* Visible Actions */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
            <label style={{ fontSize: "0.75rem", color: "#64748b" }}>Key Visible Actions</label>
            <button
              type="button"
              onClick={handleAddAction}
              style={{
                padding: "1px 6px",
                fontSize: "0.75rem",
                backgroundColor: "#e2e8f0",
                color: "#334155",
                border: "none",
                borderRadius: "3px",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              + Add Action
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            {scene.actions.map((act, i) => (
              <div key={`act-${i}`} style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                <input
                  type="text"
                  value={act}
                  placeholder="e.g. c1 points at c2"
                  onChange={(e) => handleActionChange(i, e.target.value)}
                  style={{
                    flex: 1,
                    padding: "3px 6px",
                    borderRadius: "4px",
                    border: "1px solid #cbd5e1",
                    fontSize: "0.8rem",
                    boxSizing: "border-box",
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleRemoveAction(i)}
                  style={{
                    border: "none",
                    background: "none",
                    color: "#dc2626",
                    cursor: "pointer",
                    padding: "2px 4px",
                    fontSize: "0.8rem",
                  }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
