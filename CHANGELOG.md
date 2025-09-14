# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.html).

## [2.0.0] - 2025-09-14

This release marks a complete rewrite of the frontend visualization engine, migrating from the D3.js library to **Lightweight Charts**. This fundamental change introduces massive performance gains, a highly interactive user experience, and a suite of powerful new analytical features.

### Added

-   **Interactive UI Toolbar**: A comprehensive toolbar has been added to control chart settings in real-time, including:
    -   Candle interval and tick size.
    -   Display modes (`Side-by-side` vs. `Overlay`).
    -   Toggling visibility of Candles, Footprints, Volume Profiles, and Stats.
    -   Adjustable panel widths for side-by-side mode.
-   **Right-Side Aggregated Volume Profile**: A new, powerful volume profile is rendered on the right side of the chart, with modes for:
    -   **Visible Range**: Profiles only the candles currently in view.
    -   **Session**: Profiles the entire day's trading session.
-   **Value Area High/Low (VAH/VAL)**: The right-side profile now indicates the VAH and VAL for the selected range, highlighting key liquidity zones.
-   **Advanced Display Modes**: Users can now view the Candle, Footprint, and an intra-bar Volume Profile in a flexible side-by-side layout with adjustable percentage widths.
-   **Modern Aesthetics**: The entire UI has been redesigned with a professional dark theme for better readability and a modern look and feel.
-   **Crosshair and Time Scale Improvements**: Leverages the native, high-performance crosshair, time scale, and price scale from Lightweight Charts, including detailed tooltips.

### Changed

-   **Core Rendering Engine**: Replaced the D3.js SVG-based rendering with the **Lightweight Charts Canvas-based engine**.
    -   **Performance**: Drastically improved performance, allowing for smooth rendering of thousands of data points, and seamless panning and zooming.
    -   **Responsiveness**: The chart is now fully responsive and resizes correctly with the browser window.
-   **Backend Data Streaming**: The backend now uses Server-Sent Events (SSE) for a more reliable and efficient real-time data stream to the frontend.

### Removed

-   **D3.js Dependency**: The D3.js library and all associated custom SVG rendering logic have been completely removed in favor of the new charting engine.

### Fixed

-   **Data Gap Rendering**: The new rendering logic correctly handles gaps in price data within a footprint, ensuring each price level is drawn with a uniform, accurate height.
-   **Point of Control (POC) Visualization**: The POC is now highlighted with a clean, one-tick high outline, preventing the visual stretching that occurred in the previous version.
-   **Layout Stability**: The chart layout remains stable and correctly spaced, even when only a single candle is visible.
-   **Session Data Aggregation**: Corrected the logic for the "Session" profile to ensure it aggregates data from the correct UTC day, providing an accurate daily profile.

## [1.0.0] - Initial Release

-   Initial version of the order flow chart.
-   Backend built with Python and Flask.
-   Frontend visualization using the D3.js library.
-   Basic footprint rendering inside candlestick bars.
-   Data persistence with SQLite.