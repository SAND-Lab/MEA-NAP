"""One colour per cell type, shared by the tracking pages.

Both the per-cell page and the run viewer's network view can colour cells by
every marker at once. They are separate pages, so the rule lives here once as a
JavaScript snippet each of them inlines, and the two can never disagree on what
a colour means.

The rule, per cell and day:

* positive for exactly one *subtype* marker (anything but NeuN and Mecp2)
  → that marker's colour;
* positive for more than one → "multiple";
* positive for none → "NeuN+ only" or "NeuN−" when NeuN is known;
* otherwise, "none positive" when some subtype stain came back negative, and
  "unlabelled" when nothing is known.

Mecp2 is not a colour. It is the genotype axis, not a cell type (in Het cultures
it says which allele a cell expresses), and as a colour it would double every
category, or turn every WT PV+ cell into "multiple". It is drawn as the *style*
instead: filled for Mecp2+, outline only for Mecp2−, a faint fill with a ring
when it was not labelled that day (:func:`mecp2Style`). Colour answers "which
cell type", fill answers "which allele".

Colours are Okabe–Ito, which stay distinguishable for the common forms of colour
blindness and read on light and dark backgrounds alike.
"""

TYPE_CATEGORY_JS = r"""
const TYPE_CAT_FIXED = {"PV+": "#D55E00", "SST+": "#009E73", "GAD+": "#CC79A7",
                        "multiple": "#6A3D9A", "NeuN+ only": "#56B4E9",
                        "NeuN−": "#8C6D46", "none positive": "#B0B7BF"};
// subtype markers beyond the three above take these, in marker order
const TYPE_CAT_EXTRA = ["#E69F00", "#0072B2", "#F0E442"];
const TYPE_CAT_NOT_SUBTYPE = new Set(["NeuN", "Mecp2"]);
/** A cell's category on one day. ``get(marker)`` returns 1, -1 or 0. */
function typeCategory(get, markers) {
  const sub = markers.filter(m => !TYPE_CAT_NOT_SUBTYPE.has(m));
  const pos = sub.filter(m => get(m) === 1);
  if (pos.length > 1) return "multiple";
  if (pos.length === 1) return pos[0] + "+";
  const neun = markers.includes("NeuN") ? get("NeuN") : 0;
  if (neun === 1) return "NeuN+ only";
  if (neun === -1) return "NeuN−";
  return sub.some(m => get(m) === -1) ? "none positive" : "unlabelled";
}
function typeCategoryColour(cat, markers, unlabelled) {
  if (cat in TYPE_CAT_FIXED) return TYPE_CAT_FIXED[cat];
  if (cat === "unlabelled") return unlabelled;
  const extra = markers.filter(m => !TYPE_CAT_NOT_SUBTYPE.has(m)
                                    && !((m + "+") in TYPE_CAT_FIXED));
  const k = extra.indexOf(cat.slice(0, -1));
  return TYPE_CAT_EXTRA[(k < 0 ? 0 : k) % TYPE_CAT_EXTRA.length];
}
/** How Mecp2 is drawn over the type colour: "+" filled, "-" outline only,
 *  "?" faint fill with a ring; null when the chain has no Mecp2 stain. */
function mecp2Style(get, markers) {
  if (!markers.includes("Mecp2")) return null;
  const v = get("Mecp2");
  return v === 1 ? "+" : v === -1 ? "-" : "?";
}
/** Legend entries for the three Mecp2 styles, drawn in ``colour``. */
function mecp2Legend(colour, masks) {
  const icon = st => `<svg width="12" height="12" viewBox="0 0 12 12" `
    // sized inline: host pages stretch bare <svg> elements to their width
    + `style="width:12px;height:12px;display:inline-block;vertical-align:-1px;`
    + `margin-right:4px"><circle cx="6" cy="6" r="4.3" `
    + (st === "+" ? `fill="${colour}"` : st === "-"
       ? `fill="none" stroke="${colour}" stroke-width="1.6"`
       : `fill="${colour}" fill-opacity=".35" stroke="${colour}" stroke-width="1.2"`)
    + "/></svg>";
  const word = masks ? {"+": "filled", "-": "outline", "?": "faint"}
                     : {"+": "filled", "-": "ring", "?": "faint + ring"};
  return ["+", "-", "?"].map(st => `<span>${icon(st)}Mecp2${
    st === "+" ? "+" : st === "-" ? "−" : " not labelled"} <span class="sub">(${word[st]})</span></span>`)
    .join(" ");
}
/** Legend order: subtypes, then the rest, each only if present. */
function typeCategoryOrder(present, markers) {
  const sub = markers.filter(m => !TYPE_CAT_NOT_SUBTYPE.has(m)).map(m => m + "+");
  return [...sub, "multiple", "NeuN+ only", "NeuN−", "none positive", "unlabelled"]
    .filter(c => present.has(c));
}
"""
