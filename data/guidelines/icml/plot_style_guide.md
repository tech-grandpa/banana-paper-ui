# ICML Statistical Plot Aesthetics Guide

## Venue Format Facts (grounded)

* **Layout:** Two-column on US letter paper. Overall text area is
  6.75 inches wide by 9.0 inches high with 0.25 inches between columns
  (single column = 3.25 inches wide).
* **Body font:** 10 pt Times.
* **Captions:** Set in 9 pt type, placed below the figure with at least
  0.1 inches of space before and after; centered unless the caption runs
  two or more lines, in which case it is flush left. Do not include a
  title inside the figure — the caption serves that function.
* **Artwork:** Lines should be dark and at least 0.5 pt thick for
  reproduction; text should not appear on a gray background. Graphs need
  a name for each axis and a legend that briefly describes each curve.
* **Wide figures:** May span both columns (`figure*`), and two-column
  figures always go at the top or bottom of the page.
* **Graphics format:** Vector graphics (EPS or PDF) are encouraged for
  plots; bitmaps should be limited to illustrations.

---

## 1. The "ICML Look"

ICML plots prioritize **precision and compactness**. The two-column
format means plots must remain legible at smaller sizes. Clean lines,
clear legends, and high data-ink ratio are essential. Avoid decoration
that does not encode information.

---

## 2. Detailed Style Options

### **Color Palettes**

* **Categorical:** Muted but distinguishable colors. A common palette
  uses navy, teal, coral, and slate. Avoid neon or fully saturated hues.
* **Sequential:** Viridis or Plasma for heatmaps. Perceptually uniform
  colormaps are expected.
* **Diverging:** Coolwarm (blue-to-red) for positive/negative splits.
* **Accessibility:** Combine color with marker shapes and line styles
  to support grayscale printing.

### **Axes & Grids**

* **Grid lines:** Light grey dashed lines behind data. Never solid black.
* **Spines:** Either all four sides (boxed) or remove top and right
  (open). Be consistent across figures in the same paper.
* **Tick labels:** Sans-serif, sized to stay legible at the 3.25 inch
  column width (ICML captions are 9 pt — keep tick labels comparable).
  Avoid rotated labels when horizontal fits.

### **Layout & Typography**

* **Font:** Sans-serif throughout (Helvetica, Arial, DejaVu Sans).
* **Legends:** Inside the plot area when space permits; otherwise
  placed horizontally above or below the plot.
* **Annotations:** Direct labeling on lines or bars is preferred over
  legend-only identification.
* **Subplot spacing:** Tight but with clear separation. Use shared
  axes where appropriate to save space.

---

## 3. Type-Specific Guidelines

### **Line Charts**
* Always include markers at data points (circles, squares, triangles).
* Solid lines for primary results, dashed for baselines.
* Shaded bands for confidence intervals (alpha 0.2-0.3).

### **Bar Charts**
* Thin black outlines or borderless fills. Group bars tightly.
* Error bars with flat caps in black.
* Hatching patterns as a secondary differentiator for accessibility.

### **Heatmaps**
* Square cells with numeric annotations inside.
* Viridis or Plasma colormap. Include a labeled colorbar.

### **Scatter Plots**
* Marker shape encodes one dimension, color encodes another.
* Solid opaque markers. Add trend lines where meaningful.

---

## 4. Common Pitfalls

* **Unreadable text** when scaled to column width. Always verify at
  final print size.
* **Too many overlapping lines** without distinguishing markers or styles.
* **Missing units** on axes.
* **Rainbow colormaps** (Jet) — use perceptually uniform alternatives.
* **Legends that obscure data** — reposition or use direct labeling.

---

## Sources

Venue format facts verified against the official ICML 2026 style kit
(`icml2026.sty` / `example_paper.tex`), accessed 2026-06-11:

* https://icml.cc/Conferences/2026/AuthorInstructions
* https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip
