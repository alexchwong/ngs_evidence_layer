/* Corpus user layer: free-text query, browse/edit modes, copy citation.
   Injected into the card browser template at build time. No dependencies, no
   network, and no storage APIs: the browser is opened from disk and a profile
   leaves it only as an explicit download. */

const AMENDABLE = ["interpretation", "category", "genes", "diseases", "evidence_tier"];
const CATEGORIES = ["diagnosis", "prognosis", "treatment", "biomarker", "germline"];

const CUL = {
  profile: (DATA.cul && DATA.cul.profile) || "custom",
  description: (DATA.cul && DATA.cul.description) || "",
  scope: null,  /* set below, once normaliseScope is defined */
  amendments: Object.assign({}, (DATA.cul && DATA.cul.amendments) || {}),
  dirty: false
};

const baseById = {};
DATA.cards.forEach(c => { baseById[c.id] = c; });

CUL.scope = normaliseScope((DATA.cul && DATA.cul.scope) || null);
CUL.parked = {};   /* rules toggled off in the page, restorable without deleting */
CUL.draft = null;

/* --------------------------------------------------------------------- scope */

/* Hybrid scope model. Paper and category rules stay rules: they are compact and
   they keep applying to cards a later redo adds. Tickboxes only ever write
   card-level `exclude` entries on top of those rules. A card suppressed by a
   rule is shown locked, so a three-rule profile can never be silently expanded
   into a hundred literal card IDs. */

function normaliseDimension(value){
  const v = value || {};
  return { include: (v.include || []).slice(), exclude: (v.exclude || []).slice() };
}

function normaliseRule(value){
  const v = value || {};
  return {
    enabled: v.enabled === undefined ? true : !!v.enabled,
    categories: normaliseDimension(v.categories),
    genes: normaliseDimension(v.genes),
    cards: normaliseDimension(v.cards)
  };
}

function normaliseScope(value){
  const v = value || {};
  const papers = {};
  Object.keys(v.papers || {}).forEach(key => { papers[key] = normaliseRule(v.papers[key]); });
  return {
    enabled: v.enabled === undefined ? true : !!v.enabled,
    global: normaliseRule(v.global),
    papers: papers,
    exemptions: (v.exemptions || []).slice()
  };
}

function dimensionAllows(dimension, values){
  const set = Array.isArray(values) ? values : [values];
  if (dimension.exclude.some(x => set.includes(x))) return false;
  if (dimension.include.length && !dimension.include.some(x => set.includes(x))) return false;
  return true;
}

/* Mirrors scripts/core/corpus.py::_rule_allows so the browser and retrieval
   cannot disagree about what a profile reaches. */
function ruleAllows(view, rule){
  if (!rule.enabled) return false;
  if (!dimensionAllows(rule.categories, view.category)) return false;
  if (!dimensionAllows(rule.genes, (view.genes || []).map(g => g.toUpperCase()))) return false;
  if (!dimensionAllows(rule.cards, view.id)) return false;
  return true;
}

/* Why a card is out of scope, so the UI can lock a rule-derived exclusion and
   allow a card-level one to be toggled back. */
/* Mirrors scripts/core/corpus.py::apply_blacklist. Precedence: an explicit card
   exclusion wins, then an exemption, then the rules. Nothing is locked: ticking
   a rule-suppressed card writes one exemption rather than expanding the rule
   into card ids. */
function scopeState(card){
  const view = effective(card);
  const scope = CUL.scope;
  if (!scope.enabled){
    return { included: false, exempt: false, blockedBy: "scope disabled", reason: "scope disabled" };
  }
  const paper = scope.papers[card.paper];

  if (scope.global.cards.exclude.includes(card.id) ||
      (paper && paper.cards.exclude.includes(card.id))){
    return { included: false, exempt: false, blockedBy: null, reason: "excluded card" };
  }

  const ruleOnly = r => Object.assign({}, r, { cards: { include: [], exclude: [] } });
  let blockedBy = null;
  if (!ruleAllows(view, ruleOnly(scope.global))) blockedBy = "global rule";
  else if (paper && !ruleAllows(view, ruleOnly(paper))){
    blockedBy = "rule on " + (paperName[card.paper] || card.paper);
  }

  if (scope.exemptions.includes(card.id)){
    return { included: true, exempt: true, blockedBy: blockedBy,
             reason: blockedBy ? "exempt from " + blockedBy : "exempt" };
  }
  if (blockedBy) return { included: false, exempt: false, blockedBy: blockedBy, reason: blockedBy };
  return { included: true, exempt: false, blockedBy: null, reason: "" };
}

function setCardIncluded(id, included){
  const card = baseById[id];
  const paper = CUL.scope.papers[card.paper];
  const lists = [CUL.scope.global.cards];
  if (paper) lists.push(paper.cards);
  const exemptions = CUL.scope.exemptions;
  const state = scopeState(card);

  if (included){
    lists.forEach(list => {
      const at = list.exclude.indexOf(id);
      if (at !== -1) list.exclude.splice(at, 1);
    });
    /* A card a rule suppresses is readmitted with one exemption, leaving the
       rule intact and still covering every other card it names. */
    if (state.blockedBy && !exemptions.includes(id)) exemptions.push(id);
  } else {
    const at = exemptions.indexOf(id);
    if (at !== -1) exemptions.splice(at, 1);
    /* Dropping an exemption is enough when a rule already suppresses the card;
       an explicit exclusion would be redundant. */
    if (!state.blockedBy && !CUL.scope.global.cards.exclude.includes(id)){
      CUL.scope.global.cards.exclude.push(id);
    }
  }
  CUL.dirty = true;
}

function exemptCardIds(){
  return CUL.scope.exemptions.slice().sort();
}

function excludedCardIds(){
  const ids = new Set(CUL.scope.global.cards.exclude);
  Object.values(CUL.scope.papers).forEach(rule => rule.cards.exclude.forEach(id => ids.add(id)));
  return Array.from(ids).sort();
}

/* Offered when a bulk exclusion happens to be exactly one paper or one
   category: a rule stays compact and keeps applying to cards added later. */
function rulePromotion(cards){
  if (cards.length < 2) return null;
  const papers = new Set(cards.map(c => c.paper));
  const categories = new Set(cards.map(c => effective(c).category));
  if (papers.size === 1){
    const key = cards[0].paper;
    const inPaper = DATA.cards.filter(c => c.paper === key);
    if (categories.size === 1 && cards.length < inPaper.length){
      return { kind: "paper-category", paper: key, category: cards[0].category,
               label: 'exclude every "' + Array.from(categories)[0] + '" card from ' +
                      (paperName[key] || key) };
    }
    if (cards.length === inPaper.length){
      return { kind: "paper", paper: key, label: "exclude this whole paper" };
    }
  }
  if (categories.size === 1 && papers.size > 1){
    const category = Array.from(categories)[0];
    const all = DATA.cards.filter(c => effective(c).category === category);
    if (cards.length === all.length){
      return { kind: "category", category: category,
               label: 'exclude every "' + category + '" card corpus-wide' };
    }
  }
  return null;
}

function applyPromotion(promotion){
  if (promotion.kind === "category"){
    if (!CUL.scope.global.categories.exclude.includes(promotion.category)){
      CUL.scope.global.categories.exclude.push(promotion.category);
    }
  } else {
    const key = promotion.paper;
    const rule = CUL.scope.papers[key] || normaliseRule({});
    if (promotion.kind === "paper") rule.enabled = false;
    else if (!rule.categories.exclude.includes(promotion.category)){
      rule.categories.exclude.push(promotion.category);
    }
    CUL.scope.papers[key] = rule;
  }
  CUL.dirty = true;
}

/* ---------------------------------------------------------------- amendments */

function amendmentFor(id){ return CUL.amendments[id] || null; }

function effective(card){
  const a = amendmentFor(card.id);
  if (!a) return card;
  const out = Object.assign({}, card);
  if (a.interpretation !== undefined) out.text = a.interpretation;
  if (a.category !== undefined) out.category = a.category;
  if (a.evidence_tier !== undefined) out.tier = a.evidence_tier;
  if (a.genes !== undefined) out.genes = a.genes.slice();
  if (a.diseases !== undefined) out.diseases = a.diseases.slice();
  out.amended = true;
  out.amendedFields = AMENDABLE.filter(f => a[f] !== undefined);
  out.stale = !!a.stale;
  return out;
}

function changedFields(id){
  const a = amendmentFor(id);
  if (!a) return [];
  const base = baseById[id];
  const map = { interpretation: "text", category: "category", evidence_tier: "tier",
                genes: "genes", diseases: "diseases" };
  return AMENDABLE.filter(f => {
    if (a[f] === undefined) return false;
    const b = base[map[f]];
    return Array.isArray(b) ? b.join("\u0000") !== a[f].join("\u0000") : b !== a[f];
  });
}

function setAmendment(id, field, value){
  const base = baseById[id];
  const map = { interpretation: "text", category: "category", evidence_tier: "tier",
                genes: "genes", diseases: "diseases" };
  const current = base[map[field]];
  const same = Array.isArray(current)
    ? current.join("\u0000") === (value || []).join("\u0000")
    : current === value;
  const entry = Object.assign({}, CUL.amendments[id] || { base_sha256: base.baseSha256 });
  if (same) delete entry[field]; else entry[field] = value;
  entry.base_sha256 = base.baseSha256;
  entry.stale = false;
  const remaining = AMENDABLE.filter(f => entry[f] !== undefined);
  if (!remaining.length) delete CUL.amendments[id];
  else CUL.amendments[id] = entry;
  CUL.dirty = true;
  updateProfileBar();
}

function revertCard(id){
  delete CUL.amendments[id];
  CUL.dirty = true;
  updateProfileBar();
}

/* ------------------------------------------------------------------- search */

/* Free text, not just keywords. Supports:
     bare terms          all must appear (prefix match)
     "quoted phrase"     literal substring
     -term               exclusion
     gene:TP53           field-scoped, also disease: paper: cat: tier: id:
   Terms are scored by frequency and field weight so the closest cards sort
   first; 789 cards are scanned directly, which is faster than shipping and
   parsing an inverted index. */

const FIELD_KEYS = { gene:"genes", genes:"genes", disease:"diseases", diseases:"diseases",
                     paper:"paper", cat:"category", category:"category",
                     tier:"tier", id:"id", locator:"locator" };

function parseQuery(raw){
  const terms = [];
  const re = /(-?)(?:([a-z]+):)?(?:"([^"]*)"|(\S+))/gi;
  let m;
  while ((m = re.exec(raw)) !== null){
    const text = (m[3] !== undefined ? m[3] : m[4] || "").toLowerCase().trim();
    if (!text) continue;
    terms.push({
      negate: m[1] === "-",
      field: m[2] ? FIELD_KEYS[m[2].toLowerCase()] || null : null,
      phrase: m[3] !== undefined,
      text: text
    });
  }
  return terms;
}

function haystack(card){
  const paper = paperByKey[card.paper] || {};
  return {
    text: (card.text || "").toLowerCase(),
    locator: (card.locator || "").toLowerCase(),
    genes: (card.genes || []).join(" ").toLowerCase(),
    diseases: (card.diseases || []).concat(card.ancestors || []).join(" ").toLowerCase(),
    category: (card.category || "").toLowerCase(),
    tier: (card.tier || "").toLowerCase(),
    id: (card.id || "").toLowerCase(),
    paper: ((paper.nickname || "") + " " + (paper.display || "") + " " + card.paper).toLowerCase()
  };
}

const WEIGHT = { text:1, locator:0.6, genes:2, diseases:2, category:1.5, tier:0.8, id:2, paper:1.2 };

function scoreCard(card, terms){
  if (!terms.length) return 0;
  const hay = haystack(card);
  let score = 0;
  for (const term of terms){
    const fields = term.field ? [term.field] : Object.keys(hay);
    let hits = 0;
    for (const field of fields){
      const value = hay[field] || "";
      if (!value) continue;
      let count = 0;
      if (term.phrase){
        let at = value.indexOf(term.text);
        while (at !== -1){ count++; at = value.indexOf(term.text, at + term.text.length); }
      } else {
        const re = new RegExp("(^|[^a-z0-9])" + term.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g");
        count = (value.match(re) || []).length;
        if (!count && value.includes(term.text)) count = 0.5;
      }
      if (count) hits += count * (WEIGHT[field] || 1);
    }
    if (term.negate){ if (hits) return -1; continue; }
    if (!hits) return -1;
    score += 1 + Math.log(1 + hits);
  }
  return score;
}

/* --------------------------------------------------------------- clipboard */

function copyText(text, button){
  const done = () => {
    const original = button.textContent;
    button.textContent = "Copied";
    button.classList.add("copied");
    setTimeout(() => { button.textContent = original; button.classList.remove("copied"); }, 1200);
  };
  /* navigator.clipboard is unavailable on file:// in several browsers, so the
     textarea path is a real fallback rather than defensive decoration. */
  if (navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(text).then(done, () => legacyCopy(text, done));
  } else {
    legacyCopy(text, done);
  }
}

function legacyCopy(text, done){
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try { document.execCommand("copy"); done(); } catch (err) { window.prompt("Copy:", text); }
  document.body.removeChild(area);
}

function copyRow(card){
  const paper = paperByKey[card.paper] || {};
  const row = document.createElement("div");
  row.className = "copyrow";
  const buttons = [
    ["Copy citation", () => paper.display || paper.nickname || card.paper],
    ["DOI", () => paper.doi || ""]
  ];
  for (const [label, value] of buttons){
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copybtn";
    button.textContent = label;
    button.addEventListener("click", event => {
      event.stopPropagation();
      const text = value();
      if (!text){ button.textContent = "None"; setTimeout(() => { button.textContent = label; }, 1200); return; }
      copyText(text, button);
    });
    row.appendChild(button);
  }
  return row;
}

/* ------------------------------------------------------------------ editing */

const VOCAB = DATA.vocabulary || { categories: [], evidenceTiers: [], diseases: [] };

function tokenList(value){
  return value.split(/[,\s]+/).map(x => x.trim()).filter(Boolean);
}

function displayList(values){
  return (values && values.length) ? values.join(", ") : "\u2014";
}

/* The corpus value is shown only once a field differs from it. Four permanent
   "corpus:" lines on every card would be noise on the cards nobody has touched,
   and the original is exactly what you want the moment one changes. */
function originalLine(text){
  const line = document.createElement("span");
  line.className = "wasline";
  line.textContent = "corpus: " + text;
  return line;
}

function labelled(text, field, changed, originalText){
  const wrap = document.createElement("label");
  wrap.className = "editlabel" + (changed ? " changed" : "");
  const span = document.createElement("span");
  span.textContent = text;
  wrap.appendChild(span);
  wrap.appendChild(field);
  if (changed && originalText !== undefined) wrap.appendChild(originalLine(originalText));
  return wrap;
}

function selectField(options, current, onChange){
  const select = document.createElement("select");
  select.className = "editfield";
  options.forEach(name => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    if (name === current) option.selected = true;
    select.appendChild(option);
  });
  if (current && !options.includes(current)){
    const option = document.createElement("option");
    option.value = current;
    option.textContent = current + " (not in vocabulary)";
    option.selected = true;
    select.insertBefore(option, select.firstChild);
  }
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

/* Diseases are a closed 162-term vocabulary, but 634 of 789 cards carry exactly
   one term. A native multi-select at that size is unusable, so this is a token
   field: chips for what is selected, a filtering list to add. Validating against
   the vocabulary here means an invalid term cannot reach cul.py at all. */
function diseaseField(card, selected, onChange){
  const wrap = document.createElement("div");
  wrap.className = "tokenfield";

  const chips = document.createElement("div");
  chips.className = "chips";
  wrap.appendChild(chips);

  const search = document.createElement("input");
  search.type = "text";
  search.className = "editfield tokeninput";
  search.placeholder = "add disease\u2026";
  search.setAttribute("aria-label", "Add a disease to " + card.id);
  wrap.appendChild(search);

  const list = document.createElement("ul");
  list.className = "tokenlist";
  list.hidden = true;
  wrap.appendChild(list);

  let active = selected.slice();

  function commit(){
    onChange(active.slice());
    paint();
  }

  function paint(){
    chips.innerHTML = "";
    if (!active.length){
      const none = document.createElement("span");
      none.className = "chipnone";
      none.textContent = "none";
      chips.appendChild(none);
    }
    active.forEach(name => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "chipx";
      remove.textContent = "\u00d7";
      remove.setAttribute("aria-label", "Remove " + name);
      remove.addEventListener("click", event => {
        event.stopPropagation();
        active = active.filter(x => x !== name);
        commit();
      });
      chip.appendChild(remove);
      chips.appendChild(chip);
    });
  }

  function options(){
    const needle = search.value.trim().toLowerCase();
    return VOCAB.diseases
      .filter(name => !active.includes(name))
      .filter(name => !needle || name.toLowerCase().includes(needle))
      .slice(0, 40);
  }

  function paintList(){
    const rows = options();
    list.innerHTML = "";
    list.hidden = !rows.length || document.activeElement !== search;
    rows.forEach(name => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tokenopt";
      button.textContent = name;
      button.addEventListener("mousedown", event => {
        event.preventDefault();
        active = active.concat([name]);
        search.value = "";
        commit();
        paintList();
      });
      item.appendChild(button);
      list.appendChild(item);
    });
  }

  search.addEventListener("input", paintList);
  search.addEventListener("focus", paintList);
  search.addEventListener("blur", () => { setTimeout(() => { list.hidden = true; }, 120); });
  search.addEventListener("keydown", event => {
    if (event.key === "Escape"){ search.value = ""; list.hidden = true; }
    if (event.key === "Enter"){
      event.preventDefault();
      const first = options()[0];
      if (first){ active = active.concat([first]); search.value = ""; commit(); paintList(); }
    }
  });

  paint();
  return wrap;
}

function editor(card){
  const base = baseById[card.id];
  const changed = changedFields(card.id);
  const box = document.createElement("div");
  box.className = "editor";

  /* Assertion on the left, classification on the right: the same split the
     report disclosure rule draws. */
  const columns = document.createElement("div");
  columns.className = "editcolumns";

  const left = document.createElement("div");
  left.className = "editmain";

  if (changed.includes("interpretation")){
    const original = document.createElement("div");
    original.className = "original";
    original.innerHTML = "<span class='origlabel'>Corpus interpretation</span>";
    const text = document.createElement("p");
    text.textContent = base.text;
    original.appendChild(text);
    left.appendChild(original);
  }

  const area = document.createElement("textarea");
  area.className = "editarea";
  area.rows = 6;
  area.value = card.text;
  area.setAttribute("aria-label", "Interpretation for " + card.id);
  area.addEventListener("input", () => setAmendment(card.id, "interpretation", area.value.trim()));
  area.addEventListener("change", () => renderAll());
  left.appendChild(area);
  columns.appendChild(left);

  const side = document.createElement("div");
  side.className = "editside";

  side.appendChild(labelled(
    "Category",
    selectField(VOCAB.categories, card.category, value => {
      setAmendment(card.id, "category", value);
      renderAll();
    }),
    changed.includes("category"), base.category
  ));

  side.appendChild(labelled(
    "Evidence tier",
    selectField(VOCAB.evidenceTiers, card.tier, value => {
      setAmendment(card.id, "evidence_tier", value);
      renderAll();
    }),
    changed.includes("evidence_tier"), base.tier
  ));

  const genes = document.createElement("input");
  genes.className = "editfield";
  genes.type = "text";
  genes.value = (card.genes || []).join(", ");
  genes.placeholder = "comma separated";
  genes.addEventListener("change", () => {
    setAmendment(card.id, "genes", tokenList(genes.value).map(x => x.toUpperCase()));
    renderAll();
  });
  side.appendChild(labelled("Genes", genes, changed.includes("genes"), displayList(base.genes)));

  side.appendChild(labelled(
    "Diseases",
    diseaseField(card, card.diseases || [], values => {
      setAmendment(card.id, "diseases", values);
      renderAll();
    }),
    changed.includes("diseases"), displayList(base.diseases)
  ));

  columns.appendChild(side);
  box.appendChild(columns);

  const actions = document.createElement("div");
  actions.className = "editactions";
  if (changed.length){
    const revert = document.createElement("button");
    revert.type = "button";
    revert.className = "revert";
    revert.textContent = "Revert to corpus";
    revert.addEventListener("click", () => { revertCard(card.id); renderAll(); });
    actions.appendChild(revert);
  }
  const note = document.createElement("span");
  note.className = "editnote";
  note.textContent = changed.length
    ? "Amended: " + changed.join(", ")
    : "No change; this card renders exactly as accepted.";
  actions.appendChild(note);
  box.appendChild(actions);
  return box;
}

/* ------------------------------------------------------------- profile bar */

function profileJSON(){
  const amendments = {};
  Object.keys(CUL.amendments).sort().forEach(id => {
    const entry = CUL.amendments[id];
    const out = { base_sha256: baseById[id].baseSha256, amended_at: new Date().toISOString() };
    AMENDABLE.forEach(f => { if (entry[f] !== undefined) out[f] = entry[f]; });
    amendments[id] = out;
  });
  return {
    schema_version: "1.0",
    profile: CUL.profile,
    description: CUL.description,
    authored_against_corpus_sha256: DATA.corpusSha256 || null,
    scope: CUL.scope,
    amendments: amendments
  };
}

function downloadProfile(){
  const blob = new Blob([JSON.stringify(profileJSON(), null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = CUL.profile + ".json";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  CUL.dirty = false;
  updateProfileBar();
}

/* Every field the bar shows is derived from CUL, so all of them are refreshed
   here. Refreshing only the counters left the name box showing the previous
   profile after a load. */
function updateProfileBar(){
  const bar = document.getElementById("profilebar");
  if (!bar) return;

  const name = bar.querySelector(".pname");
  if (name && document.activeElement !== name) name.value = CUL.profile;

  const count = Object.keys(CUL.amendments).length;
  const stale = Object.keys(CUL.amendments).filter(id => CUL.amendments[id].stale);
  const excluded = excludedCardIds().length;
  const rules = Object.keys(CUL.scope.papers).length +
    (CUL.scope.global.categories.exclude.length ? 1 : 0) +
    (CUL.scope.global.categories.include.length ? 1 : 0) +
    (CUL.scope.global.genes.exclude.length ? 1 : 0) +
    (CUL.scope.global.genes.include.length ? 1 : 0);
  const reachable = DATA.cards.filter(c => scopeState(c).included).length;

  const parts = [reachable + "/" + DATA.cards.length + " reachable"];
  if (rules) parts.push(rules + (rules === 1 ? " rule" : " rules"));
  if (excluded) parts.push(excluded + " excluded");
  if (count) parts.push(count + (count === 1 ? " amendment" : " amendments"));
  if (CUL.dirty) parts.push("unsaved");
  bar.querySelector(".pcount").textContent = parts.join(" \u00b7 ");

  const warn = bar.querySelector(".pstale");
  warn.textContent = stale.length ? stale.length + " stale" : "";
  warn.hidden = !stale.length;
}

function buildProfileBar(){
  const bar = document.createElement("div");
  bar.className = "profilebar";
  bar.id = "profilebar";

  /* Every profile in config/cul/ is embedded at build time, so switching does
     not need a rebuild or a file dialog. */
  const names = Object.keys(DATA.profiles || {});
  if (names.length){
    const pick = document.createElement("select");
    pick.className = "editfield pselect";
    pick.setAttribute("aria-label", "Load a profile");
    if (!names.includes(CUL.profile)){
      const current = document.createElement("option");
      current.value = "";
      current.textContent = CUL.profile + " (unsaved)";
      pick.appendChild(current);
    }
    names.forEach(name => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      if (name === CUL.profile) option.selected = true;
      pick.appendChild(option);
    });
    pick.addEventListener("change", () => {
      const chosen = pick.value;
      if (!chosen) return;
      if (CUL.dirty && !window.confirm(
            "Discard unsaved changes and load \u201c" + chosen + "\u201d?")){
        pick.value = names.includes(CUL.profile) ? CUL.profile : "";
        return;
      }
      loadProfile(DATA.profiles[chosen]);
      /* Rebuild rather than update: the option list itself changes when the
         loaded profile replaces an unsaved one. */
      const mount = document.getElementById("profilemount");
      mount.innerHTML = "";
      mount.appendChild(buildProfileBar());
      renderAll();
    });
    bar.appendChild(pick);
  }

  const name = document.createElement("input");
  name.type = "text";
  name.className = "pname";
  name.value = CUL.profile;
  name.setAttribute("aria-label", "Profile name");
  name.addEventListener("change", () => {
    const value = name.value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value)){ name.value = CUL.profile; return; }
    CUL.profile = value; CUL.dirty = true; updateProfileBar();
  });
  bar.appendChild(name);

  const count = document.createElement("span");
  count.className = "pcount";
  bar.appendChild(count);

  const stale = document.createElement("span");
  stale.className = "pstale";
  bar.appendChild(stale);

  const upload = document.createElement("label");
  upload.className = "pbtn";
  upload.textContent = "Open file";
  const file = document.createElement("input");
  file.type = "file";
  file.accept = "application/json,.json";
  file.className = "pfile";
  file.addEventListener("change", () => {
    const chosen = file.files && file.files[0];
    if (!chosen) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        loadProfile(JSON.parse(reader.result));
        renderAll();
      } catch (err) {
        window.alert("That file is not a valid CUL profile: " + err.message);
      }
      file.value = "";
    };
    reader.readAsText(chosen);
  });
  upload.appendChild(file);
  bar.appendChild(upload);

  const diff = document.createElement("button");
  diff.type = "button";
  diff.className = "pbtn";
  diff.textContent = "Review changes";
  diff.addEventListener("click", showChanges);
  bar.appendChild(diff);

  const download = document.createElement("button");
  download.type = "button";
  download.className = "pbtn primary";
  download.textContent = "Download profile";
  download.addEventListener("click", downloadProfile);
  bar.appendChild(download);

  const help = document.createElement("span");
  help.className = "phelp";
  help.textContent =
    "Downloads cannot overwrite files from disk. Install with: " +
    "python scripts/cul.py apply --from <downloaded file>";
  bar.appendChild(help);
  return bar;
}

function loadProfile(raw){
  CUL.profile = raw.profile || "custom";
  CUL.description = raw.description || "";
  CUL.scope = normaliseScope(raw.scope);
  CUL.amendments = {};
  Object.keys(raw.amendments || {}).forEach(id => {
    /* Amendments for cards this corpus does not contain are dropped rather than
       carried invisibly; cul.py would reject them anyway. */
    if (baseById[id]) CUL.amendments[id] = Object.assign({}, raw.amendments[id]);
  });
  CUL.selected = null;
  CUL.pending = null;
  CUL.parked = {};
  CUL.draft = null;
  CUL.dirty = false;
}

/* ------------------------------------------------------------- changes view */

function modal(title){
  const existing = document.getElementById("culmodal");
  if (existing) existing.remove();
  const back = document.createElement("div");
  back.className = "modalback";
  back.id = "culmodal";
  const box = document.createElement("div");
  box.className = "modalbox";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", title);
  const head = document.createElement("div");
  head.className = "modalhead";
  const heading = document.createElement("h2");
  heading.textContent = title;
  head.appendChild(heading);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "detail-close";
  close.textContent = "close";
  close.addEventListener("click", () => back.remove());
  head.appendChild(close);
  box.appendChild(head);
  back.addEventListener("click", event => { if (event.target === back) back.remove(); });
  back.appendChild(box);
  document.body.appendChild(back);
  return box;
}

function section(parent, title){
  const wrap = document.createElement("div");
  wrap.className = "modalsection";
  const heading = document.createElement("h3");
  heading.textContent = title;
  wrap.appendChild(heading);
  parent.appendChild(wrap);
  return wrap;
}

function showChanges(){
  const box = modal("Profile \u201c" + CUL.profile + "\u201d");

  const ruleKeys = Object.keys(CUL.scope.papers);
  const rules = section(box, "Retrieval rules");
  const globalCats = CUL.scope.global.categories;
  const globalGenes = CUL.scope.global.genes;
  const lines = [];
  if (!CUL.scope.enabled) lines.push("Scope disabled: no card is reachable.");
  if (globalCats.include.length) lines.push("Only these categories: " + globalCats.include.join(", "));
  if (globalCats.exclude.length) lines.push("Excluded categories: " + globalCats.exclude.join(", "));
  if (globalGenes.include.length) lines.push("Only these genes: " + globalGenes.include.join(", "));
  if (globalGenes.exclude.length) lines.push("Excluded genes: " + globalGenes.exclude.join(", "));
  ruleKeys.forEach(key => {
    const rule = CUL.scope.papers[key];
    const label = paperName[key] || key;
    if (!rule.enabled){ lines.push(label + ": whole paper excluded"); return; }
    if (rule.categories.include.length)
      lines.push(label + ": only " + rule.categories.include.join(", "));
    if (rule.categories.exclude.length)
      lines.push(label + ": excluding " + rule.categories.exclude.join(", "));
    if (rule.genes.exclude.length)
      lines.push(label + ": excluding genes " + rule.genes.exclude.join(", "));
  });
  if (!lines.length) lines.push("No rules; every card is reachable unless individually excluded.");
  lines.forEach(text => {
    const p = document.createElement("p");
    p.className = "modalline";
    p.textContent = text;
    rules.appendChild(p);
  });

  const exempt = exemptCardIds();
  const exemptSection = section(box, "Exemptions (" + exempt.length + ")");
  if (!exempt.length){
    const p = document.createElement("p");
    p.className = "modalline";
    p.textContent = "None.";
    exemptSection.appendChild(p);
  } else {
    const lead = document.createElement("p");
    lead.className = "modalline";
    lead.textContent =
      "Each readmits one card a rule would otherwise suppress. Review these if a " +
      "rule exists for a safety reason.";
    exemptSection.appendChild(lead);
    exempt.forEach(id => {
      const card = baseById[id];
      if (!card) return;
      const p = document.createElement("p");
      p.className = "modalline";
      p.textContent = card.shortId + " \u00b7 " + (paperName[card.paper] || card.paper);
      exemptSection.appendChild(p);
    });
  }

  const excluded = excludedCardIds();
  const cardSection = section(box, "Individually excluded cards (" + excluded.length + ")");
  if (!excluded.length){
    const p = document.createElement("p");
    p.className = "modalline";
    p.textContent = "None.";
    cardSection.appendChild(p);
  } else {
    const byPaper = {};
    excluded.forEach(id => {
      const card = baseById[id];
      if (!card) return;
      (byPaper[card.paper] = byPaper[card.paper] || []).push(card.shortId);
    });
    Object.keys(byPaper).sort().forEach(key => {
      const p = document.createElement("p");
      p.className = "modalline";
      p.textContent = (paperName[key] || key) + ": " + byPaper[key].join(", ");
      cardSection.appendChild(p);
    });
  }

  const ids = Object.keys(CUL.amendments).sort();
  const amendSection = section(box, "Card amendments (" + ids.length + ")");
  if (!ids.length){
    const p = document.createElement("p");
    p.className = "modalline";
    p.textContent = "None. This profile changes retrieval scope only.";
    amendSection.appendChild(p);
    return;
  }
  ids.forEach(id => {
    const base = baseById[id];
    const card = effective(base);
    const block = document.createElement("div");
    block.className = "diffblock";
    const title = document.createElement("h3");
    title.textContent = base.shortId + " \u00b7 " + (paperName[base.paper] || base.paper);
    block.appendChild(title);
    const map = { interpretation:"text", category:"category", evidence_tier:"tier",
                  genes:"genes", diseases:"diseases" };
    changedFields(id).forEach(field => {
      const before = base[map[field]];
      const after = card[map[field]];
      const row = document.createElement("div");
      row.className = "diffrow";
      const label = document.createElement("span");
      label.className = "difffield";
      label.textContent = field;
      row.appendChild(label);
      const b = document.createElement("p");
      b.className = "before";
      b.textContent = Array.isArray(before) ? (before.join(", ") || "\u2014") : (before || "\u2014");
      const a = document.createElement("p");
      a.className = "after";
      a.textContent = Array.isArray(after) ? (after.join(", ") || "\u2014") : (after || "\u2014");
      row.appendChild(b);
      row.appendChild(a);
      block.appendChild(row);
    });
    const kind = document.createElement("p");
    kind.className = "diffkind";
    kind.textContent = changedFields(id).includes("interpretation")
      ? "Disclosed in the report reference list."
      : "Reachability only; not disclosed per statement.";
    block.appendChild(kind);
    amendSection.appendChild(block);
  });
}

/* --------------------------------------------------------------- card list */

/* In edit mode the card list becomes a selector: a tickbox for scope, and the
   row itself opens that card in the centre pane. Browse mode is untouched. */
function buildCardRow(card){
  const view = effective(card);
  const scope = scopeState(card);
  const item = document.createElement("li");
  item.className = "pickrow" + (CUL.selected === card.id ? " selected" : "") +
                   (scope.included ? "" : " excluded");
  item.dataset.cardId = card.id;

  const box = document.createElement("input");
  box.type = "checkbox";
  box.className = "pickbox";
  box.checked = scope.included;
  box.title = scope.blockedBy && !scope.exempt
    ? "Suppressed by " + scope.blockedBy + "; ticking exempts this card from it"
    : scope.exempt
      ? "Exempt from " + scope.blockedBy + "; unticking restores the rule"
      : "Include this card in retrieval";
  box.setAttribute("aria-label", "Include " + card.shortId);
  box.addEventListener("click", event => event.stopPropagation());
  box.addEventListener("change", () => { setCardIncluded(card.id, box.checked); renderAll(); });
  item.appendChild(box);

  const body = document.createElement("div");
  body.className = "pickbody";

  const head = document.createElement("div");
  head.className = "pickhead";
  const id = document.createElement("span");
  id.className = "pickid";
  id.textContent = card.shortId;
  head.appendChild(id);
  const paper = document.createElement("span");
  paper.className = "pickpaper";
  paper.textContent = paperName[card.paper] || card.paper;
  head.appendChild(paper);
  if (view.amended){
    const tag = document.createElement("span");
    tag.className = "amendtag" + (view.stale ? " staletag" : "");
    tag.textContent = view.stale ? "stale" : "amended";
    head.appendChild(tag);
  }
  if (scope.exempt){
    const tag = document.createElement("span");
    tag.className = "exempttag";
    tag.textContent = "exempt";
    tag.title = "Exempt from " + scope.blockedBy;
    head.appendChild(tag);
  } else if (scope.blockedBy){
    const tag = document.createElement("span");
    tag.className = "locktag";
    tag.textContent = scope.blockedBy;
    head.appendChild(tag);
  }
  body.appendChild(head);

  const text = document.createElement("p");
  text.className = "picktext";
  text.textContent = view.text;
  body.appendChild(text);
  item.appendChild(body);

  item.tabIndex = 0;
  item.setAttribute("role", "button");
  item.addEventListener("click", () => { CUL.selected = card.id; renderAll(); });
  item.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " "){
      event.preventDefault();
      CUL.selected = card.id;
      renderAll();
    }
  });
  return item;
}

function buildPicker(rows){
  const list = document.getElementById("cards");
  list.innerHTML = "";
  const bar = document.createElement("div");
  bar.className = "pickbar";

  const shown = rows.slice();
  const included = shown.filter(c => scopeState(c).included);

  const all = document.createElement("button");
  all.type = "button";
  all.className = "pbtn";
  all.textContent = "Include " + shown.length + " shown";
  all.disabled = !shown.length || included.length === shown.length;
  all.addEventListener("click", () => {
    shown.forEach(c => setCardIncluded(c.id, true));
    renderAll();
  });
  bar.appendChild(all);

  const none = document.createElement("button");
  none.type = "button";
  none.className = "pbtn";
  /* The label states the consequence: filtering to a gene and clicking this can
     write a hundred exclusions in one gesture. */
  none.textContent = "Exclude " + included.length + " shown";
  none.disabled = !included.length;
  none.addEventListener("click", () => {
    const promotion = rulePromotion(included);
    if (promotion){
      CUL.pending = { cards: included.map(c => c.id), promotion: promotion };
    } else {
      included.forEach(c => setCardIncluded(c.id, false));
      CUL.pending = null;
    }
    renderAll();
  });
  bar.appendChild(none);

  const tally = document.createElement("span");
  tally.className = "picktally";
  const reachable = DATA.cards.filter(c => scopeState(c).included).length;
  tally.textContent = reachable + " of " + DATA.cards.length + " reachable";
  bar.appendChild(tally);
  list.appendChild(bar);

  if (CUL.pending){
    list.appendChild(promotionPrompt());
  }

  const chunk = document.createDocumentFragment();
  rows.forEach(card => chunk.appendChild(buildCardRow(card)));
  list.appendChild(chunk);
}

function promotionPrompt(){
  const box = document.createElement("div");
  box.className = "promptbox";
  const text = document.createElement("p");
  text.textContent = "These " + CUL.pending.cards.length +
    " cards can be excluded as a rule instead: " + CUL.pending.promotion.label +
    ". A rule stays compact and also covers cards a later redo adds.";
  box.appendChild(text);

  const asRule = document.createElement("button");
  asRule.type = "button";
  asRule.className = "pbtn primary";
  asRule.textContent = "Use a rule";
  asRule.addEventListener("click", () => {
    applyPromotion(CUL.pending.promotion);
    CUL.pending = null;
    renderAll();
  });
  box.appendChild(asRule);

  const asCards = document.createElement("button");
  asCards.type = "button";
  asCards.className = "pbtn";
  asCards.textContent = "List each card";
  asCards.addEventListener("click", () => {
    CUL.pending.cards.forEach(id => setCardIncluded(id, false));
    CUL.pending = null;
    renderAll();
  });
  box.appendChild(asCards);

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "pbtn";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => { CUL.pending = null; renderAll(); });
  box.appendChild(cancel);
  return box;
}

function buildEditorPane(){
  const pane = document.getElementById("detail");
  pane.innerHTML = "";
  const card = CUL.selected ? baseById[CUL.selected] : null;
  if (!card){
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = "<h3>Select a card to edit</h3>" +
      "<p>Filter on the left, pick a card on the right. Tickboxes control what " +
      "retrieval can reach; the editor changes what a card says.</p>";
    pane.appendChild(empty);
    return;
  }
  const view = effective(card);

  const head = document.createElement("div");
  head.className = "detail-head";
  const id = document.createElement("div");
  id.className = "detail-id";
  id.textContent = card.id;
  head.appendChild(id);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "detail-close";
  close.textContent = "close";
  close.addEventListener("click", () => { CUL.selected = null; renderAll(); });
  head.appendChild(close);
  pane.appendChild(head);

  const cite = document.createElement("p");
  cite.className = "detail-citation";
  const paper = paperByKey[card.paper] || {};
  cite.textContent = paper.display || paper.nickname || card.paper;
  pane.appendChild(cite);
  pane.appendChild(copyRow(card));

  const state = scopeState(card);
  if (!state.included){
    const note = document.createElement("p");
    note.className = "scopenote";
    note.textContent = state.locked
      ? "Not reachable: " + state.reason + ". Edits are still saved."
      : "Excluded from retrieval by this profile. Edits are still saved.";
    pane.appendChild(note);
  }

  pane.appendChild(editor(view));
}

/* --------------------------------------------------------------- rules panel */

/* Rules are profile-level state, so they live in the rail rather than the card
   list. The card list shows the consequence; this shows the cause. */

function ruleRows(){
  const rows = [];
  const dims = [
    ["categories", "include", "Only these categories"],
    ["categories", "exclude", "Excluding categories"],
    ["genes", "include", "Only these genes"],
    ["genes", "exclude", "Excluding genes"]
  ];
  dims.forEach(([dim, mode, label]) => {
    const values = CUL.scope.global[dim][mode];
    if (values.length) rows.push({ scope: null, dim, mode, label, values, title: "Corpus-wide" });
  });
  Object.keys(CUL.scope.papers).sort().forEach(key => {
    const rule = CUL.scope.papers[key];
    const title = paperName[key] || key;
    if (!rule.enabled){
      rows.push({ scope: key, dim: null, mode: null, label: "Whole paper excluded",
                  values: [], title: title });
    }
    dims.forEach(([dim, mode, label]) => {
      const values = rule[dim][mode];
      if (values.length) rows.push({ scope: key, dim, mode, label, values, title: title });
    });
  });
  return rows;
}

function ruleTarget(row){
  return row.scope ? CUL.scope.papers[row.scope] : CUL.scope.global;
}

/* Disabling clears the dimension's values and parks them, which round-trips
   through the existing schema without adding a per-dimension enabled flag. */
function ruleKey(row){
  return (row.scope || "*") + "|" + (row.dim || "paper") + "|" + (row.mode || "enabled");
}

function ruleEnabled(row){
  return !CUL.parked[ruleKey(row)];
}

function setRuleEnabled(row, on){
  const key = ruleKey(row);
  const target = ruleTarget(row);
  if (on){
    const parked = CUL.parked[key];
    if (!parked) return;
    if (row.dim) target[row.dim][row.mode] = parked.slice();
    else target.enabled = false;
    delete CUL.parked[key];
  } else {
    if (row.dim){
      CUL.parked[key] = target[row.dim][row.mode].slice();
      target[row.dim][row.mode] = [];
    } else {
      CUL.parked[key] = ["paper"];
      target.enabled = true;
    }
  }
  CUL.dirty = true;
}

function removeRule(row){
  const target = ruleTarget(row);
  if (row.dim) target[row.dim][row.mode] = [];
  else target.enabled = true;
  delete CUL.parked[ruleKey(row)];
  if (row.scope){
    const rule = CUL.scope.papers[row.scope];
    const empty = rule.enabled &&
      !rule.categories.include.length && !rule.categories.exclude.length &&
      !rule.genes.include.length && !rule.genes.exclude.length &&
      !rule.cards.include.length && !rule.cards.exclude.length;
    if (empty) delete CUL.scope.papers[row.scope];
  }
  CUL.dirty = true;
}

/* How many cards a candidate rule would remove, computed against the live
   profile. A corpus-wide category rule can move a third of the corpus, so the
   count is shown before the rule is committed. */
function previewRule(draft){
  if (!draft.values.length) return null;
  const before = DATA.cards.filter(c => scopeState(c).included).map(c => c.id);
  const snapshot = JSON.parse(JSON.stringify(CUL.scope));
  const parked = Object.assign({}, CUL.parked);
  applyRuleDraft(draft);
  const after = new Set(DATA.cards.filter(c => scopeState(c).included).map(c => c.id));
  CUL.scope = snapshot;
  CUL.parked = parked;
  const lost = before.filter(id => !after.has(id));
  return { lost: lost, gained: after.size - (before.length - lost.length) };
}

function applyRuleDraft(draft){
  const target = draft.scope
    ? (CUL.scope.papers[draft.scope] = CUL.scope.papers[draft.scope] || normaliseRule({}))
    : CUL.scope.global;
  const list = target[draft.dim][draft.mode];
  draft.values.forEach(value => { if (!list.includes(value)) list.push(value); });
  CUL.dirty = true;
}

function buildRulesPanel(){
  const box = document.createElement("section");
  box.className = "facet rulespanel";

  const head = document.createElement("div");
  head.className = "facet-head";
  const title = document.createElement("h2");
  title.textContent = "Retrieval rules";
  head.appendChild(title);
  box.appendChild(head);

  const rows = ruleRows();
  const list = document.createElement("ul");
  list.className = "rulelist";
  if (!rows.length){
    const empty = document.createElement("li");
    empty.className = "ruleempty";
    empty.textContent = "No rules. Every card is reachable unless excluded individually.";
    list.appendChild(empty);
  }
  rows.forEach(row => {
    const item = document.createElement("li");
    item.className = "ruleitem" + (ruleEnabled(row) ? "" : " off");
    item.id = "rule-" + ruleKey(row).replace(/[^A-Za-z0-9]/g, "-");

    const box2 = document.createElement("input");
    box2.type = "checkbox";
    box2.className = "pickbox";
    box2.checked = ruleEnabled(row);
    box2.setAttribute("aria-label", "Enable rule: " + row.title + " " + row.label);
    box2.addEventListener("change", () => { setRuleEnabled(row, box2.checked); renderAll(); });
    item.appendChild(box2);

    const body = document.createElement("div");
    body.className = "rulebody";
    const scope = document.createElement("span");
    scope.className = "rulescope";
    scope.textContent = row.title;
    body.appendChild(scope);
    const text = document.createElement("span");
    text.className = "ruletext";
    text.textContent = row.values.length ? row.label + ": " + row.values.join(", ") : row.label;
    body.appendChild(text);
    item.appendChild(body);

    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "ruledrop";
    drop.textContent = "\u00d7";
    drop.title = "Remove this rule";
    drop.setAttribute("aria-label", "Remove rule");
    drop.addEventListener("click", () => { removeRule(row); renderAll(); });
    item.appendChild(drop);
    list.appendChild(item);
  });
  box.appendChild(list);

  const exempt = exemptCardIds();
  if (exempt.length){
    const note = document.createElement("p");
    note.className = "ruleexempt";
    note.textContent = exempt.length +
      (exempt.length === 1 ? " card is exempt" : " cards are exempt") +
      " from the rules above.";
    box.appendChild(note);
  }

  box.appendChild(buildRuleForm());
  return box;
}

function buildRuleForm(){
  const form = document.createElement("div");
  form.className = "ruleform";

  const draft = CUL.draft || (CUL.draft = { scope: "", dim: "categories", mode: "exclude", values: [] });

  const where = document.createElement("select");
  where.className = "editfield";
  where.setAttribute("aria-label", "Rule scope");
  const everywhere = document.createElement("option");
  everywhere.value = "";
  everywhere.textContent = "Corpus-wide";
  where.appendChild(everywhere);
  DATA.papers.forEach(paper => {
    const option = document.createElement("option");
    option.value = paper.key;
    option.textContent = paper.nickname || paper.key;
    if (paper.key === draft.scope) option.selected = true;
    where.appendChild(option);
  });
  where.addEventListener("change", () => { draft.scope = where.value; renderAll(); });
  form.appendChild(labelled("Applies to", where, false));

  const what = document.createElement("select");
  what.className = "editfield";
  what.setAttribute("aria-label", "Rule dimension");
  [["categories", "Categories"], ["genes", "Genes"]].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    if (value === draft.dim) option.selected = true;
    what.appendChild(option);
  });
  what.addEventListener("change", () => { draft.dim = what.value; draft.values = []; renderAll(); });
  form.appendChild(labelled("Restrict by", what, false));

  const how = document.createElement("select");
  how.className = "editfield";
  how.setAttribute("aria-label", "Rule mode");
  /* Plain words rather than include/exclude: an include list is a whitelist and
     reads backwards when it is called a blacklist rule. */
  [["exclude", "All except these"], ["include", "Only these"]].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    if (value === draft.mode) option.selected = true;
    how.appendChild(option);
  });
  how.addEventListener("change", () => { draft.mode = how.value; renderAll(); });
  form.appendChild(labelled("Mode", how, false));

  const values = document.createElement("div");
  values.className = "rulevalues";
  if (draft.dim === "categories"){
    VOCAB.categories.forEach(name => {
      const label = document.createElement("label");
      label.className = "rulecheck";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.className = "pickbox";
      box.checked = draft.values.includes(name);
      box.addEventListener("change", () => {
        draft.values = box.checked
          ? draft.values.concat([name])
          : draft.values.filter(x => x !== name);
        renderAll();
      });
      label.appendChild(box);
      const span = document.createElement("span");
      span.textContent = name;
      label.appendChild(span);
      values.appendChild(label);
    });
  } else {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "editfield";
    input.placeholder = "gene symbols, comma separated";
    input.value = draft.values.join(", ");
    input.addEventListener("change", () => {
      draft.values = tokenList(input.value).map(x => x.toUpperCase());
      renderAll();
    });
    values.appendChild(input);
  }
  form.appendChild(labelled("Values", values, false));

  const preview = previewRule(draft);
  const note = document.createElement("p");
  note.className = "rulepreview";
  note.textContent = !draft.values.length
    ? "Choose one or more values."
    : "This rule would remove " + preview.lost.length +
      (preview.lost.length === 1 ? " card." : " cards.");
  form.appendChild(note);

  const add = document.createElement("button");
  add.type = "button";
  add.className = "pbtn primary";
  add.textContent = "Add rule";
  add.disabled = !draft.values.length;
  add.addEventListener("click", () => {
    applyRuleDraft(draft);
    CUL.draft = null;
    renderAll();
  });
  form.appendChild(add);
  return form;
}
