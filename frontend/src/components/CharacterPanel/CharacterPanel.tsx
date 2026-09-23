import React from "react";
import type { Character, SelectedRegion } from "../../types/context";

interface CharacterPanelProps {
  characters: Character[];
  onChange: (characters: Character[]) => void;
  selectedRegion: SelectedRegion | null;
  onSelectRegion: (region: SelectedRegion | null) => void;
}

export const CharacterPanel: React.FC<CharacterPanelProps> = ({
  characters,
  onChange,
  selectedRegion,
  onSelectRegion,
}) => {
  const handleUpdate = (index: number, field: keyof Character, value: unknown) => {
    const updated = [...characters];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const handleAdd = () => {
    const nextId = `c${characters.length + 1}`;
    onChange([
      ...characters,
      {
        id: nextId,
        description: "",
        bbox: null,
        expression: null,
        emotion: null,
        action: null,
      },
    ]);
  };

  const handleDelete = (index: number) => {
    onChange(characters.filter((_, i) => i !== index));
    if (selectedRegion?.kind === "character" && selectedRegion.index === index) {
      onSelectRegion(null);
    }
  };

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "#1e293b" }}>
          Characters ({characters.length})
        </h4>
        <button
          type="button"
          onClick={handleAdd}
          style={{
            padding: "2px 8px",
            fontSize: "0.8rem",
            backgroundColor: "#0284c7",
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

      {characters.length === 0 && (
        <div style={{ fontSize: "0.85rem", color: "#94a3b8", fontStyle: "italic", padding: "0.5rem 0" }}>
          No characters detected on this page.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {characters.map((ch, idx) => {
          const isSelected = selectedRegion?.kind === "character" && selectedRegion.index === idx;

          return (
            <div
              key={`char-panel-${idx}`}
              onClick={() => onSelectRegion({ kind: "character", index: idx })}
              style={{
                border: isSelected ? "2px solid #0284c7" : "1px solid #e2e8f0",
                borderRadius: "6px",
                padding: "0.75rem",
                backgroundColor: isSelected ? "#f0f9ff" : "#ffffff",
                boxShadow: isSelected ? "0 0 0 1px #0284c7" : "none",
                transition: "all 0.15s ease",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <input
                  type="text"
                  value={ch.id}
                  placeholder="ID (e.g. c1)"
                  onChange={(e) => handleUpdate(idx, "id", e.target.value)}
                  style={{
                    fontWeight: "bold",
                    width: "70px",
                    padding: "3px 6px",
                    borderRadius: "4px",
                    border: "1px solid #cbd5e1",
                    fontSize: "0.85rem",
                  }}
                />
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
                  title="Remove Character"
                >
                  ✕
                </button>
              </div>

              <div style={{ display: "grid", gap: "0.4rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Description</label>
                  <input
                    type="text"
                    value={ch.description || ""}
                    placeholder="e.g. black-haired young man"
                    onChange={(e) => handleUpdate(idx, "description", e.target.value || null)}
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

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Expression</label>
                    <input
                      type="text"
                      value={ch.expression || ""}
                      placeholder="e.g. angry"
                      onChange={(e) => handleUpdate(idx, "expression", e.target.value || null)}
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
                    <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Emotion</label>
                    <input
                      type="text"
                      value={ch.emotion || ""}
                      placeholder="e.g. anger"
                      onChange={(e) => handleUpdate(idx, "emotion", e.target.value || null)}
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

                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", color: "#64748b" }}>Action</label>
                  <input
                    type="text"
                    value={ch.action || ""}
                    placeholder="e.g. pointing at c2"
                    onChange={(e) => handleUpdate(idx, "action", e.target.value || null)}
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
            </div>
          );
        })}
      </div>
    </div>
  );
};
