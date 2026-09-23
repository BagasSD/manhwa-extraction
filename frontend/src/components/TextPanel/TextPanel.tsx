import React from "react";
import type { SelectedRegion, TextRegion, TextRegionType } from "../../types/context";

interface TextPanelProps {
  texts: TextRegion[];
  onChange: (texts: TextRegion[]) => void;
  selectedRegion: SelectedRegion | null;
  onSelectRegion: (region: SelectedRegion | null) => void;
}

const REGION_TYPES: { value: TextRegionType; label: string }[] = [
  { value: "speech", label: "Speech (speech)" },
  { value: "thought", label: "Thought (thought)" },
  { value: "narration", label: "Narration (narration)" },
  { value: "caption", label: "Caption (caption)" },
  { value: "system", label: "System/UI (system)" },
  { value: "sfx", label: "SFX (sfx)" },
  { value: "sign", label: "Sign (sign)" },
  { value: "unknown", label: "Unknown (unknown)" },
];

export const TextPanel: React.FC<TextPanelProps> = ({
  texts,
  onChange,
  selectedRegion,
  onSelectRegion,
}) => {
  const handleUpdate = (index: number, field: keyof TextRegion, value: unknown) => {
    const updated = [...texts];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const handleAdd = () => {
    const nextIndex = texts.length + 1;
    onChange([
      ...texts,
      {
        id: `t${nextIndex}`,
        text: "",
        speaker: null,
        target: null,
        type: "speech",
        bbox: null,
        order: nextIndex,
        confidence: null,
      },
    ]);
  };

  const handleDelete = (index: number) => {
    onChange(texts.filter((_, i) => i !== index));
    if (selectedRegion?.kind === "text" && selectedRegion.index === index) {
      onSelectRegion(null);
    }
  };

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "#1e293b" }}>
          Dialogue & Text ({texts.length})
        </h4>
        <button
          type="button"
          onClick={handleAdd}
          style={{
            padding: "2px 8px",
            fontSize: "0.8rem",
            backgroundColor: "#d97706",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          + Add
        </button>
      </div>

      {texts.length === 0 && (
        <div style={{ fontSize: "0.85rem", color: "#94a3b8", fontStyle: "italic", padding: "0.5rem 0" }}>
          No text/dialogue regions detected on this page.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {texts.map((tx, idx) => {
          const isSelected = selectedRegion?.kind === "text" && selectedRegion.index === idx;

          return (
            <div
              key={`text-panel-${idx}`}
              onClick={() => onSelectRegion({ kind: "text", index: idx })}
              style={{
                border: isSelected ? "2px solid #d97706" : "1px solid #e2e8f0",
                borderRadius: "6px",
                padding: "0.75rem",
                backgroundColor: isSelected ? "#fffbeb" : "#ffffff",
                boxShadow: isSelected ? "0 0 0 1px #d97706" : "none",
                transition: "all 0.15s ease",
              }}
            >
              {/* Header row: ID, Order, Type, Delete */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  <input
                    type="text"
                    value={tx.id || `t${idx + 1}`}
                    placeholder="ID"
                    onChange={(e) => handleUpdate(idx, "id", e.target.value)}
                    style={{
                      width: "45px",
                      padding: "2px 4px",
                      borderRadius: "4px",
                      border: "1px solid #cbd5e1",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "#d97706",
                    }}
                  />
                  <div style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                    <span style={{ fontSize: "0.75rem", color: "#64748b" }}>#</span>
                    <input
                      type="number"
                      value={tx.order}
                      onChange={(e) => handleUpdate(idx, "order", parseInt(e.target.value, 10) || 1)}
                      style={{
                        width: "35px",
                        padding: "2px 4px",
                        borderRadius: "4px",
                        border: "1px solid #cbd5e1",
                        fontSize: "0.75rem",
                      }}
                    />
                  </div>
                  <select
                    value={tx.type}
                    onChange={(e) => handleUpdate(idx, "type", e.target.value)}
                    style={{
                      padding: "2px 4px",
                      borderRadius: "4px",
                      border: "1px solid #cbd5e1",
                      fontSize: "0.8rem",
                    }}
                  >
                    {REGION_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(idx);
                  }}
                  style={{
                    border: "none",
                    background: "none",
                    color: "#dc2626",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                    padding: "2px 6px",
                  }}
                  title="Remove Text"
                >
                  ✕
                </button>
              </div>

              {/* Text content textarea */}
              <div style={{ marginBottom: "0.4rem" }}>
                <textarea
                  rows={2}
                  value={tx.text}
                  placeholder="Transcribed dialogue or text..."
                  onChange={(e) => handleUpdate(idx, "text", e.target.value)}
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

              {/* Speaker, Target, Confidence */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.4rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Speaker</label>
                  <input
                    type="text"
                    value={tx.speaker || ""}
                    placeholder="e.g. c1"
                    onChange={(e) => handleUpdate(idx, "speaker", e.target.value || null)}
                    style={{
                      width: "100%",
                      padding: "3px 6px",
                      borderRadius: "4px",
                      border: "1px solid #cbd5e1",
                      fontSize: "0.85rem",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Target</label>
                  <input
                    type="text"
                    value={tx.target || ""}
                    placeholder="e.g. c2"
                    onChange={(e) => handleUpdate(idx, "target", e.target.value || null)}
                    style={{
                      width: "100%",
                      padding: "3px 6px",
                      borderRadius: "4px",
                      border: "1px solid #cbd5e1",
                      fontSize: "0.85rem",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Confidence</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={tx.confidence ?? ""}
                    placeholder="0.0 - 1.0"
                    onChange={(e) => {
                      const val = e.target.value === "" ? null : parseFloat(e.target.value);
                      handleUpdate(idx, "confidence", isNaN(val as number) ? null : val);
                    }}
                    style={{
                      width: "100%",
                      padding: "3px 6px",
                      borderRadius: "4px",
                      border: "1px solid #cbd5e1",
                      fontSize: "0.85rem",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
