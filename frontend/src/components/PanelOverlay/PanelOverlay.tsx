import React from "react";
import { Rnd } from "react-rnd";

/** A panel box being edited; `key` stays stable while the box moves or is renumbered. */
export interface EditablePanel {
  key: string;
  /** [ymin, xmin, ymax, xmax] in original-image pixels. */
  bbox: number[];
}

interface PanelOverlayProps {
  panels: EditablePanel[];
  /** Displayed pixels per original-image pixel. */
  scale: number;
  imageWidth: number;
  imageHeight: number;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  onChange: (key: string, bbox: number[]) => void;
  onDelete: (key: string) => void;
}

const COLORS = ["#ef4444", "#22c55e", "#3b82f6", "#f59e0b", "#d946ef", "#06b6d4"];

/**
 * Interactive panel boxes over a page image (drag to move, drag the edges or
 * corners to resize). Coordinates are converted to original-image pixels on
 * every change, so the stored bbox never depends on the on-screen size.
 */
export const PanelOverlay: React.FC<PanelOverlayProps> = ({
  panels,
  scale,
  imageWidth,
  imageHeight,
  selectedKey,
  onSelect,
  onChange,
  onDelete,
}) => {
  const toBbox = (x: number, y: number, width: number, height: number): number[] => {
    const xmin = Math.max(0, Math.round(x / scale));
    const ymin = Math.max(0, Math.round(y / scale));
    const xmax = Math.min(imageWidth, Math.round((x + width) / scale));
    const ymax = Math.min(imageHeight, Math.round((y + height) / scale));
    return [ymin, xmin, Math.max(ymin + 1, ymax), Math.max(xmin + 1, xmax)];
  };

  return (
    <>
      {panels.map((panel, idx) => {
        const [ymin, xmin, ymax, xmax] = panel.bbox;
        const color = COLORS[idx % COLORS.length];
        const selected = panel.key === selectedKey;
        return (
          <Rnd
            key={panel.key}
            bounds="parent"
            position={{ x: xmin * scale, y: ymin * scale }}
            size={{ width: (xmax - xmin) * scale, height: (ymax - ymin) * scale }}
            minWidth={12}
            minHeight={12}
            onMouseDown={(e) => {
              e.stopPropagation();
              onSelect(panel.key);
            }}
            onDragStop={(_e, d) => onChange(panel.key, toBbox(d.x, d.y, (xmax - xmin) * scale, (ymax - ymin) * scale))}
            onResizeStop={(_e, _dir, ref, _delta, pos) =>
              onChange(panel.key, toBbox(pos.x, pos.y, ref.offsetWidth, ref.offsetHeight))
            }
            style={{
              border: `${selected ? 3 : 2}px solid ${color}`,
              backgroundColor: selected ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.04)",
              boxShadow: selected ? `0 0 0 2px rgba(0,0,0,0.6), 0 0 12px ${color}` : "0 0 0 1px rgba(0,0,0,0.5)",
              zIndex: selected ? 20 : 10,
            }}
            resizeHandleStyles={
              selected
                ? {
                    topLeft: handleStyle(color),
                    topRight: handleStyle(color),
                    bottomLeft: handleStyle(color),
                    bottomRight: handleStyle(color),
                  }
                : undefined
            }
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                backgroundColor: color,
                color: "#fff",
                fontWeight: 700,
                fontSize: "0.85rem",
                padding: "1px 7px",
                borderBottomRightRadius: "4px",
                userSelect: "none",
              }}
            >
              {idx + 1}
            </div>
            {selected && (
              <button
                type="button"
                title="Delete this panel (Del)"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(panel.key);
                }}
                style={{
                  position: "absolute",
                  top: 4,
                  right: 4,
                  border: "none",
                  borderRadius: "4px",
                  backgroundColor: "#dc2626",
                  color: "#fff",
                  fontWeight: 700,
                  cursor: "pointer",
                  padding: "2px 7px",
                }}
              >
                ✕
              </button>
            )}
          </Rnd>
        );
      })}
    </>
  );
};

function handleStyle(color: string): React.CSSProperties {
  return {
    width: 14,
    height: 14,
    backgroundColor: "#fff",
    border: `2px solid ${color}`,
    borderRadius: "3px",
  };
}
