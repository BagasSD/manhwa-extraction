import React from "react";
import type { Character, SelectedRegion, TextRegion } from "../../types/context";

interface RegionOverlayProps {
  characters: Character[];
  texts: TextRegion[];
  imageNaturalWidth: number;
  imageNaturalHeight: number;
  selectedRegion: SelectedRegion | null;
  onSelectRegion: (region: SelectedRegion | null) => void;
}

export const RegionOverlay: React.FC<RegionOverlayProps> = ({
  characters,
  texts,
  imageNaturalWidth,
  imageNaturalHeight,
  selectedRegion,
  onSelectRegion,
}) => {
  // Helper to convert bbox [ymin, xmin, ymax, xmax] or [x, y, w, h] to CSS % positions
  const getBboxStyle = (bbox: number[] | null): React.CSSProperties | null => {
    if (!bbox || bbox.length !== 4) return null;

    let [y1, x1, y2, x2] = bbox;

    // Check if format is 0-1000 normalized (standard Gemma / vision token format)
    const isNormalized1000 = Math.max(...bbox) <= 1000;

    let topPct = 0;
    let leftPct = 0;
    let widthPct = 0;
    let heightPct = 0;

    if (isNormalized1000) {
      topPct = (y1 / 1000) * 100;
      leftPct = (x1 / 1000) * 100;
      widthPct = ((x2 - x1) / 1000) * 100;
      heightPct = ((y2 - y1) / 1000) * 100;
    } else if (imageNaturalWidth > 0 && imageNaturalHeight > 0) {
      // Pixel coordinates [ymin, xmin, ymax, xmax]
      topPct = (y1 / imageNaturalHeight) * 100;
      leftPct = (x1 / imageNaturalWidth) * 100;
      widthPct = ((x2 - x1) / imageNaturalWidth) * 100;
      heightPct = ((y2 - y1) / imageNaturalHeight) * 100;
    } else {
      return null;
    }

    return {
      position: "absolute",
      top: `${Math.max(0, topPct)}%`,
      left: `${Math.max(0, leftPct)}%`,
      width: `${Math.max(2, widthPct)}%`,
      height: `${Math.max(2, heightPct)}%`,
      boxSizing: "border-box",
    };
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: "none",
      }}
    >
      {/* Character bounding boxes */}
      {characters.map((ch, idx) => {
        const style = getBboxStyle(ch.bbox);
        if (!style) return null;
        const isSelected =
          selectedRegion?.kind === "character" && selectedRegion.index === idx;

        return (
          <div
            key={`char-${ch.id}-${idx}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelectRegion({ kind: "character", index: idx });
            }}
            style={{
              ...style,
              pointerEvents: "auto",
              cursor: "pointer",
              border: isSelected ? "3px solid #0284c7" : "2px solid rgba(2, 132, 199, 0.75)",
              backgroundColor: isSelected ? "rgba(2, 132, 199, 0.2)" : "rgba(2, 132, 199, 0.08)",
              zIndex: isSelected ? 20 : 10,
              transition: "all 0.15s ease",
            }}
          >
            <span
              style={{
                position: "absolute",
                top: "-20px",
                left: "-2px",
                backgroundColor: "#0284c7",
                color: "#fff",
                fontSize: "11px",
                fontWeight: 700,
                padding: "2px 6px",
                borderRadius: "3px",
                whiteSpace: "nowrap",
              }}
            >
              {ch.id} {ch.expression ? `(${ch.expression})` : ""}
            </span>
          </div>
        );
      })}

      {/* Text region bounding boxes */}
      {texts.map((tx, idx) => {
        const style = getBboxStyle(tx.bbox);
        if (!style) return null;
        const isSelected =
          selectedRegion?.kind === "text" && selectedRegion.index === idx;

        return (
          <div
            key={`text-${idx}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelectRegion({ kind: "text", index: idx });
            }}
            style={{
              ...style,
              pointerEvents: "auto",
              cursor: "pointer",
              border: isSelected ? "3px solid #d97706" : "2px solid rgba(217, 119, 6, 0.8)",
              backgroundColor: isSelected ? "rgba(217, 119, 6, 0.25)" : "rgba(217, 119, 6, 0.1)",
              zIndex: isSelected ? 20 : 10,
              transition: "all 0.15s ease",
            }}
          >
            <span
              style={{
                position: "absolute",
                bottom: "-20px",
                left: "-2px",
                backgroundColor: "#d97706",
                color: "#fff",
                fontSize: "10px",
                fontWeight: 700,
                padding: "2px 5px",
                borderRadius: "3px",
                whiteSpace: "nowrap",
              }}
            >
              {tx.id ? `${tx.id} (#${tx.order})` : `#${tx.order}`} [{tx.type}] {tx.speaker ? `(${tx.speaker})` : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
};
