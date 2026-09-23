"""Shared constants used across the backend."""

# Text region types (see docs/UPGRADE_TEXT_EXTRACTION_PLAN.md section 3)
TEXT_REGION_TYPES = (
    "speech",     # spoken dialogue
    "thought",    # internal thought
    "narration",  # narration box
    "caption",    # descriptive caption
    "system",     # system/game/UI text
    "sfx",        # sound effect
    "sign",       # text visible in environment
    "unknown",    # type cannot be determined
    # Aliases for backward compatibility
    "sp",
    "th",
    "na",
    "ca",
    "ui",
    "sx",
    "uk",
)

# Page processing statuses (used starting Phase 3/7)
PAGE_STATUSES = (
    "pending",
    "processing",
    "done",
    "failed",
    "manual_review",
)
