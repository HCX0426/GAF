"""Runtime display context: holds live window/DPI/screen parameters.

This is the GAF port of BD2-AUTO's `RuntimeDisplayContext`. It is the
single source of truth for the coordinate transformer: all base→logical→
physical→screen conversions derive from values stored here.

Field vs property naming (TD-008 fix):
- All dataclass FIELDS use singular component suffixes (`*_width`,
  `*_height`, `*_x`, `*_y`). These are the only valid constructor
  arguments and the only settable attributes.
- The matching tuple-returning PROPERTIES use the `*_res` / `*_origin`
  suffix (e.g. `client_physical_res` returns `(width, height)`). These
  are READ-ONLY — passing them as constructor args silently fails
  because the dataclass has no such field, which previously caused
  footguns (see screenshot_diagnostic.py historical comment).
- `__post_init__` validates that no field was mistakenly given a tuple
  value (the most common misuse pattern), raising a clear TypeError.
- For tuple-style construction, use the `from_tuples()` classmethod
  instead of positional or keyword construction.

Field semantics (mirrors BD2-AUTO):
- original_base_*: Reference resolution all ROI coordinates are defined
  against (typically 1920x1080). Set once at construction.
- hwnd: Bound window handle (0/None = unbound).
- is_fullscreen: True when the window covers the screen — skips DPI scaling
  (logical == physical == screen).
- dpi_scale: Physical pixels per logical pixel (1.0 = 100%, 1.25 = 125%).
- client_logical_*: Visual client-area size (DPI-independent).
- client_physical_*: Actual rendered pixels (= client_logical * dpi_scale).
- screen_physical_*: Monitor native resolution.
- client_screen_origin_*: Client area's top-left in screen-physical coords.

The context is mutated in-place via `update_from_window()` whenever the
bound window resizes / moves / DPI changes. The CoordinateTransformer
holds a reference and reads live values, so a single update propagates.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[int, int]


@dataclass
class RuntimeDisplayContext:
    """Live display state shared across the pipeline engine.

    Holds the runtime window/screen parameters required by
    CoordinateTransformer for base↔logical↔physical↔screen conversions.

    Construction:
        Prefer `RuntimeDisplayContext.from_tuples(...)` when you have
        (width, height) tuples — it's clearer and avoids the field/property
        naming footgun. Direct field construction with `*_width`/`*_height`
        keywords is also supported; `__post_init__` validates that no field
        was mistakenly given a tuple value.
    """

    # ── Fixed reference resolution (set once at construction) ──────
    original_base_width: int = 1920
    original_base_height: int = 1080

    # ── Runtime window state (mutated via update_from_window) ──────
    hwnd: int | None = None
    is_fullscreen: bool = False
    dpi_scale: float = 1.0

    # Client-area logical size (DPI-independent visual size)
    client_logical_width: int = 0
    client_logical_height: int = 0

    # Client-area physical size (= logical * dpi_scale, in actual pixels)
    client_physical_width: int = 0
    client_physical_height: int = 0

    # Screen physical resolution (monitor native)
    screen_physical_width: int = 0
    screen_physical_height: int = 0

    # Client-area top-left in screen-physical coords (from ClientToScreen)
    client_screen_origin_x: int = 0
    client_screen_origin_y: int = 0

    # ── Validation (TD-008 fix) ────────────────────────────────────
    def __post_init__(self) -> None:
        """Validate that no scalar field was mistakenly given a tuple.

        Catches the most common footgun: passing a (w, h) tuple to a
        `*_width` or `*_height` field, which would silently store the
        tuple and break arithmetic downstream. The historical cause was
        callers confusing the `*_res` property name (returns a tuple)
        with the `*_width`/`*_height` field names (each take a scalar).
        """
        scalar_int_fields = (
            "original_base_width", "original_base_height",
            "client_logical_width", "client_logical_height",
            "client_physical_width", "client_physical_height",
            "screen_physical_width", "screen_physical_height",
            "client_screen_origin_x", "client_screen_origin_y",
        )
        for name in scalar_int_fields:
            value = getattr(self, name)
            if isinstance(value, (tuple, list)):
                raise TypeError(
                    f"RuntimeDisplayContext field {name!r} must be a scalar int, "
                    f"got {type(value).__name__} {value!r}. "
                    f"You probably meant to use RuntimeDisplayContext.from_tuples(...) "
                    f"to construct from (width, height) tuples, or to pass the "
                    f"matching *_width/*_height fields separately. "
                    f"See utils/display_context.py docstring (TD-008 fix)."
                )

    # ── Tuple-style construction (TD-008 fix) ──────────────────────
    @classmethod
    def from_tuples(
        cls,
        *,
        original_base: Point = (1920, 1080),
        hwnd: int | None = None,
        is_fullscreen: bool = False,
        dpi_scale: float = 1.0,
        client_logical: Point = (0, 0),
        client_physical: Point = (0, 0),
        screen_physical: Point = (0, 0),
        client_origin: Point = (0, 0),
    ) -> RuntimeDisplayContext:
        """Build a RuntimeDisplayContext from (width, height) tuples.

        Preferred constructor when you have tuple-shaped inputs (e.g.
        results from GetClientRect / MonitorFromWindow). Avoids the
        field/property naming footgun described in TD-008.

        Args:
            original_base: (width, height) reference resolution.
            hwnd: Bound window handle.
            is_fullscreen: Fullscreen flag.
            dpi_scale: DPI scale (1.0 = 100%).
            client_logical: (width, height) client logical area.
            client_physical: (width, height) client physical pixels.
            screen_physical: (width, height) monitor native resolution.
            client_origin: (x, y) client area top-left in screen coords.

        Returns:
            Populated RuntimeDisplayContext.
        """
        return cls(
            original_base_width=original_base[0],
            original_base_height=original_base[1],
            hwnd=hwnd,
            is_fullscreen=is_fullscreen,
            dpi_scale=dpi_scale,
            client_logical_width=client_logical[0],
            client_logical_height=client_logical[1],
            client_physical_width=client_physical[0],
            client_physical_height=client_physical[1],
            screen_physical_width=screen_physical[0],
            screen_physical_height=screen_physical[1],
            client_screen_origin_x=client_origin[0],
            client_screen_origin_y=client_origin[1],
        )

    # ── Derived read-only properties ───────────────────────────────
    @property
    def original_base_res(self) -> tuple[int, int]:
        """Reference resolution (width, height)."""
        return (self.original_base_width, self.original_base_height)

    @property
    def client_logical_res(self) -> tuple[int, int]:
        """Client logical resolution (width, height)."""
        return (self.client_logical_width, self.client_logical_height)

    @property
    def client_physical_res(self) -> tuple[int, int]:
        """Client physical resolution (width, height)."""
        return (self.client_physical_width, self.client_physical_height)

    @property
    def screen_physical_res(self) -> tuple[int, int]:
        """Screen physical resolution (width, height)."""
        return (self.screen_physical_width, self.screen_physical_height)

    @property
    def client_screen_origin(self) -> tuple[int, int]:
        """Client area top-left in screen-physical coords (x, y)."""
        return (self.client_screen_origin_x, self.client_screen_origin_y)

    @property
    def effective_physical_res(self) -> tuple[int, int]:
        """Physical resolution used for scaling: screen if fullscreen,
        client physical otherwise."""
        return self.screen_physical_res if self.is_fullscreen else self.client_physical_res

    @property
    def logical_to_physical_ratio(self) -> float:
        """Logical→Physical scale factor.

        Fullscreen mode: 1.0 (logical == physical).
        Window mode: client_physical_width / client_logical_width.
        Returns 1.0 on invalid dimensions to avoid division by zero.
        """
        if self.is_fullscreen:
            return 1.0
        if self.client_logical_width <= 0:
            return 1.0
        return self.client_physical_width / self.client_logical_width

    # ── State update ───────────────────────────────────────────────
    def update_from_window(
        self,
        hwnd: int | None = None,
        is_fullscreen: bool | None = None,
        dpi_scale: float | None = None,
        client_logical: Point | None = None,
        client_physical: Point | None = None,
        screen_physical: Point | None = None,
        client_origin: Point | None = None,
    ) -> None:
        """Batch-update runtime fields. Only non-None args are applied.

        Call this whenever the bound window resizes, moves, changes DPI,
        or toggles fullscreen.

        Args:
            hwnd: Window handle.
            is_fullscreen: Fullscreen flag.
            dpi_scale: DPI scale factor (1.0 = 100%).
            client_logical: (width, height) of client logical area.
            client_physical: (width, height) of client physical pixels.
            screen_physical: (width, height) of monitor native resolution.
            client_origin: (x, y) of client area top-left in screen coords.
        """
        if hwnd is not None:
            self.hwnd = hwnd
        if is_fullscreen is not None:
            self.is_fullscreen = is_fullscreen
        if dpi_scale is not None:
            self.dpi_scale = dpi_scale
        if client_logical:
            self.client_logical_width, self.client_logical_height = client_logical
        if client_physical:
            self.client_physical_width, self.client_physical_height = client_physical
        if screen_physical:
            self.screen_physical_width, self.screen_physical_height = screen_physical
        if client_origin:
            self.client_screen_origin_x, self.client_screen_origin_y = client_origin

    def logical_to_physical(self, x: int, y: int) -> Point:
        """Convert client logical → physical coords (fullscreen-aware).

        Args:
            x: Logical X.
            y: Logical Y.

        Returns:
            (physical_x, physical_y).
        """
        ratio = self.logical_to_physical_ratio
        return (int(round(x * ratio)), int(round(y * ratio)))

    def __str__(self) -> str:
        mode = "fullscreen" if self.is_fullscreen else "windowed"
        return (
            f"RuntimeDisplayContext[{mode}] "
            f"base={self.original_base_res} "
            f"logical={self.client_logical_res} "
            f"physical={self.client_physical_res} "
            f"dpi={self.dpi_scale:.2f} "
            f"screen={self.screen_physical_res} "
            f"ratio={self.logical_to_physical_ratio:.2f}"
        )

    def __repr__(self) -> str:
        return (
            f"RuntimeDisplayContext("
            f"original_base={self.original_base_width}x{self.original_base_height}, "
            f"hwnd={self.hwnd}, is_fullscreen={self.is_fullscreen}, "
            f"dpi_scale={self.dpi_scale:.2f}, "
            f"client_logical={self.client_logical_width}x{self.client_logical_height}, "
            f"client_physical={self.client_physical_width}x{self.client_physical_height}, "
            f"screen_physical={self.screen_physical_width}x{self.screen_physical_height}, "
            f"client_origin=({self.client_screen_origin_x},{self.client_screen_origin_y})"
            f")"
        )
