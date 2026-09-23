import React, { useEffect, useState } from "react";
import type { ChapterContext } from "../../types/context";
import { generateChapterContext, getChapterContext, saveChapterContext } from "../../services/api";

interface ChapterContextModalProps {
  chapterId: string;
  chapterTitle: string;
  onClose: () => void;
}

export const ChapterContextModal: React.FC<ChapterContextModalProps> = ({
  chapterId,
  chapterTitle,
  onClose,
}) => {
  const [context, setContext] = useState<ChapterContext | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setErrorMessage(null);

    getChapterContext(chapterId)
      .then((data) => {
        if (isMounted) setContext(data);
      })
      .catch(() => {
        // Not generated yet, that's fine
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [chapterId]);

  const handleGenerate = async (force = false) => {
    setGenerating(true);
    setErrorMessage(null);
    try {
      const data = await generateChapterContext(chapterId, force);
      setContext(data);
    } catch (err) {
      setErrorMessage((err as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!context) return;
    setSaving(true);
    setSaveMessage(null);
    setErrorMessage(null);
    try {
      const updated = await saveChapterContext(chapterId, context);
      setContext(updated);
      setSaveMessage("✓ Chapter context saved successfully!");
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (err) {
      setErrorMessage((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          backgroundColor: "#ffffff",
          borderRadius: "8px",
          width: "800px",
          maxWidth: "92vw",
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
          border: "1px solid #cbd5e1",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "1rem 1.5rem",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            backgroundColor: "#f8fafc",
            borderTopLeftRadius: "8px",
            borderTopRightRadius: "8px",
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: "1.15rem", color: "#0f172a" }}>
              📖 Chapter Context: {chapterTitle}
            </h3>
            <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
              Multi-page synthesis containing major characters, events, transitions, and key dialogue.
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: "1.25rem",
              cursor: "pointer",
              color: "#64748b",
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Content */}
        <div style={{ padding: "1.5rem", overflowY: "auto", flex: 1 }}>
          {errorMessage && (
            <div
              style={{
                backgroundColor: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#b91c1c",
                borderRadius: "6px",
                padding: "0.75rem",
                marginBottom: "1rem",
                fontSize: "0.85rem",
              }}
            >
              {errorMessage}
            </div>
          )}

          {saveMessage && (
            <div
              style={{
                backgroundColor: "#f0fdf4",
                border: "1px solid #bbf7d0",
                color: "#15803d",
                borderRadius: "6px",
                padding: "0.75rem",
                marginBottom: "1rem",
                fontSize: "0.85rem",
              }}
            >
              {saveMessage}
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "#64748b" }}>
              Loading chapter context...
            </div>
          ) : !context ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem" }}>
              <p style={{ color: "#475569", marginBottom: "1.5rem", fontSize: "0.95rem" }}>
                Chapter context has not been synthesized yet. Generate it now by aggregating all extracted pages with Gemma.
              </p>
              <button
                type="button"
                onClick={() => handleGenerate(false)}
                disabled={generating}
                style={{
                  padding: "0.6rem 1.5rem",
                  backgroundColor: "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  fontWeight: 600,
                  fontSize: "0.95rem",
                  cursor: generating ? "not-allowed" : "pointer",
                  opacity: generating ? 0.7 : 1,
                }}
              >
                {generating ? "Synthesizing with Gemma..." : "⚡ Generate Chapter Context"}
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {/* Summary Section */}
              <div>
                <label style={{ display: "block", fontWeight: 600, fontSize: "0.85rem", color: "#334155", marginBottom: "0.35rem" }}>
                  Chapter Overview / Summary
                </label>
                <textarea
                  value={context.summary || ""}
                  onChange={(e) => setContext({ ...context, summary: e.target.value })}
                  rows={3}
                  placeholder="Concise overview of chapter events..."
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    fontSize: "0.9rem",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              {/* Characters Involved */}
              <div>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", color: "#0f172a" }}>
                  Characters & Roles ({context.characters.length})
                </h4>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {context.characters.map((ch, idx) => (
                    <div
                      key={ch.id || idx}
                      style={{
                        backgroundColor: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: "6px",
                        padding: "0.6rem 0.75rem",
                      }}
                    >
                      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.35rem" }}>
                        <span style={{ fontWeight: 700, color: "#2563eb", fontSize: "0.85rem" }}>
                          {ch.id} {ch.name ? `(${ch.name})` : ""}
                        </span>
                        {ch.role && (
                          <span style={{ backgroundColor: "#e2e8f0", padding: "1px 6px", borderRadius: "4px", fontSize: "0.75rem", color: "#475569" }}>
                            {ch.role}
                          </span>
                        )}
                        <span style={{ color: "#64748b", fontSize: "0.85rem" }}>
                          {ch.description}
                        </span>
                      </div>
                      {ch.actions && ch.actions.length > 0 && (
                        <div style={{ fontSize: "0.8rem", color: "#334155" }}>
                          <strong>Actions:</strong> {ch.actions.join("; ")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Major Events */}
              <div>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", color: "#0f172a" }}>
                  Chronological Events ({context.events.length})
                </h4>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {context.events.map((ev, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: "6px",
                        padding: "0.6rem 0.75rem",
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "0.75rem",
                      }}
                    >
                      <span
                        style={{
                          backgroundColor: "#dbeafe",
                          color: "#1e40af",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {ev.pages && ev.pages.length > 0
                          ? `Pages ${ev.pages.join("-")}`
                          : "Chapter"}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "0.85rem", color: "#1e293b", fontWeight: 500 }}>
                          {ev.event}
                        </div>
                        {ev.characters_involved && ev.characters_involved.length > 0 && (
                          <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "2px" }}>
                            Involved: {ev.characters_involved.join(", ")}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Scene Transitions */}
              {context.transitions && context.transitions.length > 0 && (
                <div>
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", color: "#0f172a" }}>
                    Scene & Location Transitions ({context.transitions.length})
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {context.transitions.map((tr, idx) => (
                      <div
                        key={idx}
                        style={{
                          backgroundColor: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "6px",
                          padding: "0.5rem 0.75rem",
                          fontSize: "0.85rem",
                        }}
                      >
                        <span style={{ color: "#0284c7", fontWeight: 600, marginRight: "0.5rem" }}>
                          [Pages {tr.pages.join("-")}]:
                        </span>
                        <span>{tr.description}</span>
                        {(tr.from_location || tr.to_location) && (
                          <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "2px" }}>
                            {tr.from_location || "Unknown"} → {tr.to_location || "Unknown"}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Important Dialogue */}
              {context.important_dialogue && context.important_dialogue.length > 0 && (
                <div>
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", color: "#0f172a" }}>
                    Important Dialogue ({context.important_dialogue.length})
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {context.important_dialogue.map((dl, idx) => (
                      <div
                        key={idx}
                        style={{
                          backgroundColor: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "6px",
                          padding: "0.5rem 0.75rem",
                          fontSize: "0.85rem",
                        }}
                      >
                        <span style={{ color: "#64748b", fontSize: "0.75rem", marginRight: "0.5rem" }}>
                          [P.{dl.page}]
                        </span>
                        <strong style={{ color: "#2563eb" }}>{dl.speaker || "Unknown"}: </strong>
                        <span style={{ fontStyle: "italic", color: "#1e293b" }}>"{dl.text}"</span>
                        {dl.target && (
                          <span style={{ fontSize: "0.75rem", color: "#94a3b8", marginLeft: "0.5rem" }}>
                            (to {dl.target})
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div
          style={{
            padding: "0.75rem 1.5rem",
            borderTop: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            backgroundColor: "#f8fafc",
            borderBottomLeftRadius: "8px",
            borderBottomRightRadius: "8px",
          }}
        >
          <button
            type="button"
            onClick={() => handleGenerate(true)}
            disabled={generating}
            style={{
              padding: "0.4rem 0.85rem",
              backgroundColor: "#f1f5f9",
              color: "#334155",
              border: "1px solid #cbd5e1",
              borderRadius: "4px",
              fontWeight: 600,
              fontSize: "0.85rem",
              cursor: generating ? "not-allowed" : "pointer",
            }}
          >
            {generating ? "Re-synthesizing..." : "🔄 Re-generate with Gemma"}
          </button>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "0.4rem 0.85rem",
                backgroundColor: "#fff",
                color: "#475569",
                border: "1px solid #cbd5e1",
                borderRadius: "4px",
                fontSize: "0.85rem",
                cursor: "pointer",
              }}
            >
              Close
            </button>
            {context && (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: "0.4rem 1.2rem",
                  backgroundColor: "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  fontWeight: 600,
                  fontSize: "0.85rem",
                  cursor: saving ? "not-allowed" : "pointer",
                }}
              >
                {saving ? "Saving..." : "Save Corrections"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
