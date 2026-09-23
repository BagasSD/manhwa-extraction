import React, { useRef, useState } from "react";
import type { Character, SelectedRegion, TextRegion } from "../../types/context";
import { RegionOverlay } from "../RegionOverlay/RegionOverlay";

interface ImageViewerProps {
  imageUrl: string;
  characters: Character[];
  texts: TextRegion[];
  selectedRegion: SelectedRegion | null;
  onSelectRegion: (region: SelectedRegion | null) => void;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({
  imageUrl,
  characters,
  texts,
  selectedRegion,
  onSelectRegion,
}) => {
  const [naturalWidth, setNaturalWidth] = useState(0);
  const [naturalHeight, setNaturalHeight] = useState(0);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setNaturalWidth(img.naturalWidth);
    setNaturalHeight(img.naturalHeight);
    setLoading(false);
  };

  const handleZoomIn = () => setZoomLevel((z) => Math.min(z + 0.25, 3.0));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(z - 0.25, 0.5));
  const handleResetZoom = () => setZoomLevel(1.0);

  return (
    <div
      style={{
        flex: 1,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#0f172a",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Zoom Toolbar */}
      <div
        style={{
          position: "absolute",
          top: "1rem",
          left: "1rem",
          zIndex: 50,
          display: "flex",
          gap: "0.5rem",
          backgroundColor: "rgba(15, 23, 42, 0.85)",
          padding: "0.35rem 0.6rem",
          borderRadius: "6px",
          backdropFilter: "blur(4px)",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <button
          type="button"
          onClick={handleZoomOut}
          style={{
            background: "none",
            border: "1px solid #475569",
            color: "#fff",
            borderRadius: "4px",
            padding: "2px 8px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
          title="Zoom Out"
        >
          -
        </button>
        <span style={{ color: "#cbd5e1", fontSize: "0.85rem", alignSelf: "center", minWidth: "45px", textAlign: "center" }}>
          {Math.round(zoomLevel * 100)}%
        </span>
        <button
          type="button"
          onClick={handleZoomIn}
          style={{
            background: "none",
            border: "1px solid #475569",
            color: "#fff",
            borderRadius: "4px",
            padding: "2px 8px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
          title="Zoom In"
        >
          +
        </button>
        <button
          type="button"
          onClick={handleResetZoom}
          style={{
            background: "none",
            border: "1px solid #475569",
            color: "#94a3b8",
            borderRadius: "4px",
            padding: "2px 6px",
            cursor: "pointer",
            fontSize: "0.8rem",
          }}
          title="Reset Zoom"
        >
          Reset
        </button>
      </div>

      {/* Main Image View Area */}
      <div
        ref={containerRef}
        onClick={() => onSelectRegion(null)}
        style={{
          flex: 1,
          overflow: "auto",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          padding: "2rem",
        }}
      >
        <div
          style={{
            position: "relative",
            display: "inline-block",
            transform: `scale(${zoomLevel})`,
            transformOrigin: "top center",
            transition: "transform 0.15s ease",
            boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
          }}
        >
          <img
            src={imageUrl}
            alt="Manhwa Page"
            onLoad={handleImageLoad}
            style={{
              display: "block",
              maxWidth: "100%",
              maxHeight: "calc(100vh - 120px)",
              objectFit: "contain",
              userSelect: "none",
            }}
          />

          {!loading && naturalWidth > 0 && (
            <RegionOverlay
              characters={characters}
              texts={texts}
              imageNaturalWidth={naturalWidth}
              imageNaturalHeight={naturalHeight}
              selectedRegion={selectedRegion}
              onSelectRegion={onSelectRegion}
            />
          )}
        </div>
      </div>
    </div>
  );
};
