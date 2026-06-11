# ACL Statistical Plot Aesthetics Guide

## Venue Format Facts (grounded)

* **Layout:** Two-column. Column width 7.7 cm, with 0.6 cm between
  columns and a column height of 24.7 cm. Wide figures may run across
  both columns (~16.0 cm full text width).
* **Body font:** 11 pt Times Roman (Times New Roman or Computer Modern
  Roman if Times Roman is unavailable).
* **Captions:** 10 pt roman type, placed below the figure, in the form
  "Figure 1: Caption of the Figure." One-line captions are centered;
  longer captions are left-aligned.
* **Color/accessibility (official wording):** "To accommodate people who
  are color-blind (as well as those printing with black-and-white
  printers), grayscale readability is strongly encouraged. Color is not
  forbidden, but authors should ensure that tables and figures do not
  rely solely on color to convey critical distinctions."
* **Margins:** All figures must fit within the page margins (2.5 cm on
  all sides).

---

## 1. The "ACL Look"

ACL plots emphasize **readability and comparison**. Papers frequently
include performance tables alongside plots, so figures must justify
their visual form by revealing patterns that tables cannot. Bar charts
comparing models across tasks and line charts showing training dynamics
are the most common plot types.

---

## 2. Detailed Style Options

### **Color Palettes**

* **Categorical:** Muted, well-separated colors. Common choices: navy,
  teal, salmon, olive. One color per model or method, used consistently
  across all figures in the paper.
* **Sequential:** Viridis or Blues for heatmaps (e.g., attention maps,
  confusion matrices).
* **Emphasis:** Bold color (red, gold) reserved for the proposed method;
  baselines in neutral tones (grey, light blue).

### **Axes & Grids**

* **Grid lines:** Light grey dashed lines, behind data elements.
* **Spines:** Boxed (all four sides) is most common in ACL papers.
* **Axis labels:** Clear, with units. Font size must survive scaling to
  the 7.7 cm column width — as a reference point, ACL captions are set
  in 10 pt type.

### **Layout & Typography**

* **Font:** Sans-serif throughout. Match the paper's body font when
  possible.
* **Legends:** Inside the plot area (top-left or top-right) or as a
  shared horizontal legend above grouped subplots.
* **Subplots:** Common for multi-task or multi-dataset comparisons.
  Use shared y-axes and consistent x-axis ordering.

---

## 3. Type-Specific Guidelines

### **Bar Charts (Most Common)**
* Group by task/dataset on x-axis, models as grouped bars.
* Include numeric values above or inside bars for precise comparison.
* Error bars for multiple runs, with flat caps.

### **Line Charts**
* Training curves, learning rate schedules, or scaling experiments.
* Markers at evaluation points. Shaded confidence bands.
* Log scale on x-axis for large-scale experiments.

### **Heatmaps**
* Attention visualizations: token-by-token grids with Viridis colormap.
* Confusion matrices: annotated cells with counts or percentages.
* Square aspect ratio for symmetric matrices.

### **Box / Violin Plots**
* Distribution comparisons across models or datasets.
* Outlier markers as small dots. Median line clearly visible.

---

## 4. Common Pitfalls

* **Bar charts without numeric labels** — when differences are small,
  readers need exact values.
* **Inconsistent model ordering** across subplots.
* **Attention heatmaps without axis labels** — always label source
  and target tokens.
* **Overcrowded legends** — simplify or use direct annotation.
* **Missing significance indicators** — use asterisks or brackets
  for statistical significance where applicable.

---

## Sources

Venue format facts verified against the official ACL style files and
ACLPUB formatting guidelines, accessed 2026-06-11:

* https://github.com/acl-org/acl-style-files (formatting.md)
* https://acl-org.github.io/ACLPUB/formatting.html
