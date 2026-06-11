# IEEE Statistical Plot Aesthetics Guide

## Venue Format Facts (grounded)

* **Layout:** Two-column. One column width is 3.5 inches (88.9 mm /
  21 picas); figures spanning both columns are 7.16 inches (182 mm /
  43 picas) wide. Large figures may span both columns but must not
  extend into the page margins.
* **Body font:** 10 pt Times Roman / Times New Roman (a proportional
  serif typeface).
* **Captions:** Placed below figures (table heads go above tables).
  "Fig." is abbreviated with a period after the figure number. Captions
  and figure text are set in 8 pt type.
* **Figure labels:** The IEEE conference template specifies 8 pt
  Times New Roman for figure labels; use words rather than symbols or
  abbreviations for axis labels, with units in parentheses (e.g.,
  "Magnetization (A/m)") — do not label axes only with units.
* **Resolution:** Greater than 300 dpi for color/grayscale images and
  greater than 600 dpi for black-and-white line art; acceptable vector
  formats are PS, EPS, and PDF.
* **Placement:** Figures and tables go at the top or bottom of columns;
  avoid placing them in the middle of columns.

---

## 1. The "IEEE Look"

IEEE plots follow a **formal, print-first** aesthetic. Since many IEEE
publications are still read in print or black-and-white PDF, plots must
be fully interpretable without color. The style emphasizes precise axis
labeling, high contrast, and conservative decoration.

---

## 2. Detailed Style Options

### **Color Palettes**

* **Grayscale priority:** Design plots to work in grayscale first, then
  add color as a secondary channel.
* **Categorical:** If using color, stick to high-contrast combinations:
  black, dark blue, red, green. Maximum 4-5 distinct colors.
* **Sequential:** Grayscale gradients or Viridis for heatmaps.
* **Patterns:** Hatching (diagonal lines, crosshatch, dots) is expected
  for bar charts to support black-and-white printing.

### **Axes & Grids**

* **Grid lines:** Light grey dotted or dashed lines. Subtle but present.
* **Spines:** Full box (all four sides) is the IEEE convention.
* **Tick marks:** Inward-facing ticks on all active axes.
* **Axis labels:** Include units in parentheses, e.g., "Frequency (Hz)" —
  never units alone. Use words rather than symbols or abbreviations.
  Times New Roman, matching the paper body.

### **Layout & Typography**

* **Font:** Times New Roman, matching the IEEE body typeface — the
  official conference template sets figure labels in 8 pt Times New
  Roman, and captions/figure text in 8 pt type.
* **Legends:** Boxed legends inside the plot area, or below the figure.
  Include line style and marker descriptions, not just color swatches.
* **Figure numbering:** IEEE uses "Fig. 1." format in captions.
* **Multi-panel figures:** Label panels (a), (b), (c) in the top-left
  corner of each subplot.

---

## 3. Type-Specific Guidelines

### **Line Charts**
* Distinct line styles (solid, dashed, dash-dot, dotted) for each series.
* Distinct markers (circle, square, triangle, diamond) at data points.
* Both line style and marker must differ between series for grayscale
  readability.

### **Bar Charts**
* Fill patterns (hatching) required for grayscale compatibility.
* Thin black outlines on all bars.
* Group bars with clear spacing between groups.

### **Scatter Plots**
* Open vs. filled markers to encode categories.
* Different shapes for different groups.

### **Heatmaps / Confusion Matrices**
* Annotated cell values. Grayscale-friendly colormap.
* Clear axis labels for rows and columns.

### **Box Plots**
* Standard Tukey box plots with whiskers. Outliers as individual points.
* Black outlines, light fill (white or light grey).

---

## 4. Common Pitfalls

* **Color-only differentiation** — plots must be readable in grayscale.
  Always pair color with line style, marker shape, or hatching.
* **Missing axis units** — IEEE reviewers frequently flag this.
* **Font size too small** after scaling to column width.
* **Inconsistent figure style** across the paper.
* **3D effects or shadows** — IEEE style is strictly flat and clean.
* **Missing panel labels** in multi-panel figures.

---

## Sources

Venue format facts verified against official IEEE author resources,
accessed 2026-06-11:

* https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/
* https://www.overleaf.com/latex/templates/ieee-conference-template/grfzhhncsfqn (official IEEE conference template, via https://www.ieee.org/conferences/publishing/templates)
* https://ieee-pes.org/publications/authors-kit/preparation-of-a-formatted-technical-work/
