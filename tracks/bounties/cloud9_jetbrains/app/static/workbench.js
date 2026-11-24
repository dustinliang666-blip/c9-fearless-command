"use strict";

const $ = (id) => document.getElementById(id);
const titles = {
  dragon: "First dragon", grubs: "First grubs", herald: "First herald", first_blood: "First blood",
  draft_tendency: "Opening plan", fearless_replacement: "Replacement watch",
  macro: "Objective setup", model_option: "Draft option",
};
const units = { drafts: "drafts", games: "games", pick_turns: "pick turns" };
const nameById = new Map();
let catalog, games, view, board;
let busy = false;
let scoutRequest = 0;

function el(tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  return element;
}

function options(select, rows, selected) {
  select.replaceChildren(...rows.map(({id, name}) => new Option(name, id)));
  if (rows.some(({id}) => id === selected)) select.value = selected;
}

async function request(path, payload) {
  const response = await fetch(path, payload === undefined ? undefined : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function error(message = "") {
  $("error").hidden = !message;
  $("error").textContent = message;
}

function delta(value) {
  return `${(value > 0 ? "+" : "") + value.toFixed(2)} pp`;
}

function tone(value) {
  return value > 0.005 ? "positive" : value < -0.005 ? "negative" : "neutral";
}

function note(text) {
  return el("p", text, "empty");
}

function metric(label, evidence) {
  const {numerator, denominator} = evidence;
  const row = el("div", undefined, "scout-metric");
  row.append(el("span", label), el("strong", denominator ? `${numerator} / ${denominator}` : "—"));
  row.title = evidence.scope;
  const bar = el("div", undefined, "metric-bar");
  const fill = el("i");
  fill.style.width = `${denominator ? Math.min(100, 100 * numerator / denominator) : 0}%`;
  bar.append(fill);
  return [row, bar];
}

function renderScouting(profile) {
  if (!profile.games) {
    $("scouting").replaceChildren(note("No games match these scouting filters."));
    return;
  }
  const scope = el("div", undefined, "scout-metric");
  scope.append(el("span", `${profile.games} games`), el("strong", `${profile.wins} wins`));
  const objectives = el("section", undefined, "scout-section objectives");
  objectives.append(el("h3", "First objectives · by 15:00"));
  for (const row of profile.first_objectives) objectives.append(...metric(titles[row.objective], row.evidence));
  const gold = el("div", undefined, "scout-metric");
  const mean = profile.gold_at_15.mean;
  gold.append(el("span", `GD@15 · n=${profile.gold_at_15.games}`),
    el("strong", mean === null ? "—" : new Intl.NumberFormat("en", {
      maximumFractionDigits: 0, signDisplay: "always",
    }).format(mean)));
  objectives.append(gold);
  const lists = [["Most picked", profile.picks], ["Opening bans", profile.opening_bans]].map(([title, rows]) => {
    const section = el("section", undefined, "scout-section");
    section.append(el("h3", title));
    for (const row of rows) section.append(...metric(row.name, row.evidence));
    if (!rows.length) section.append(note("No ordered draft evidence in scope."));
    return section;
  });
  $("scouting").replaceChildren(scope, objectives, ...lists);
}

async function scouting() {
  const version = ++scoutRequest;
  const query = new URLSearchParams({team: $("opponent").value, patch: $("patch").value, side: $("side").value});
  try {
    const profile = await request(`/api/scouting?${query}`);
    if (version === scoutRequest) renderScouting(profile);
  } catch (problem) {
    if (version === scoutRequest) error(problem.message);
  }
}

function renderTabs(state) {
  const tabs = Array.from({length: 5}, (_, index) => {
    const number = index + 1;
    const button = el("button", `Game ${number}`);
    button.type = "button";
    button.disabled = number > games.length;
    button.setAttribute("aria-pressed", number === view);
    button.addEventListener("click", () => update(games, number));
    return button;
  });
  $("game-tabs").replaceChildren(...tabs);
  const team = $("team").value;
  const opponent = $("opponent").value;
  const score = el("strong", `${state.wins[team]}–${state.wins[opponent]}`);
  $("series-score").replaceChildren(nameById.get(team), score, nameById.get(opponent));
}

function renderSlots(state) {
  const sides = ["blue", "red"].map((side) => {
    const team = el("section", undefined, `team-board ${side}`);
    const title = el("h3", undefined, "team-title");
    title.append(el("span", nameById.get(state[side])), el("small", side.toUpperCase()));
    const slots = el("div", undefined, "slot-grid");
    state.slots.forEach((slot, index) => {
      if (slot.side !== side) return;
      const used = index < state.step;
      const label = `${slot.kind === "ban" ? "Ban" : "Pick"} ${slot.phase}`;
      const marker = el("div", slot.champion || (used ? "Passed" : label), "slot");
      Object.assign(marker.dataset, {kind: slot.kind, used, active: index === state.step});
      marker.title = `${label} · turn ${index + 1}${slot.champion ? ` · ${slot.champion}` : ""}`;
      slots.append(marker);
    });
    team.append(title, slots);
    return team;
  });
  $("draft-slots").replaceChildren(...sides);
}

function svg(tag, attributes, content) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (content !== undefined) node.textContent = content;
  return node;
}

function renderImpact(state) {
  const latest = state.curve.at(-1);
  $("probability").textContent = `${(100 * latest.blue_probability).toFixed(1)}%`;
  $("delta").textContent = delta(latest.delta_pp);
  $("delta").className = tone(latest.delta_pp);
  const span = Math.max(2, 2 * Math.ceil(Math.max(...state.curve.map((point) => Math.abs(point.delta_pp))) / 2));
  const x = (step) => 37 + step * 12.5;
  const y = (value) => 65 - 45 * value / span;
  const lines = [-span, 0, span].flatMap((value) => [
    svg("line", {x1: x(0), x2: x(20), y1: y(value), y2: y(value), class: "gridline"}),
    svg("text", {x: 31, y: y(value) + 3, "text-anchor": "end"}, value > 0 ? `+${value}` : value),
  ]);
  const ticks = [0, 6, 12, 16, 20].map((step) =>
    svg("text", {x: x(step), y: 130, "text-anchor": "middle"}, step || "Pre"));
  const trace = svg("polyline", {
    points: state.curve.map((point) => `${x(point.step)},${y(point.delta_pp)}`).join(" "), class: "trace",
  });
  const dots = state.curve.map((point) => {
    const dot = svg("circle", {cx: x(point.step), cy: y(point.delta_pp), r: 3.2});
    dot.append(svg("title", {}, `Turn ${point.step} · blue ${(100 * point.blue_probability).toFixed(1)}% · ${delta(point.delta_pp)}`));
    return dot;
  });
  $("curve").replaceChildren(...lines, ...ticks, trace, ...dots);
  $("stage-note").textContent = state.next_stage_gamma === 0
    ? "Next stage uses the pre-draft estimate. Forward validation found no BP improvement."
    : "Percentage-point change from the pre-draft estimate.";
}

function evidenceText(sample) {
  const gameCount = sample.unit === "pick_turns" ? ` · ${sample.distinct_games} distinct games` : "";
  return `${sample.numerator}/${sample.denominator} ${units[sample.unit]}${gameCount} · ${sample.scope}`;
}

function renderBrief(cards) {
  $("brief").replaceChildren(...cards.map((entry) => {
    const card = el("article", undefined, "brief-card");
    card.append(el("h3", titles[entry.kind]), el("p", entry.instruction),
      el("small", evidenceText(entry.evidence), "evidence"));
    for (const item of entry.comparison || []) {
      if (item.denominator) card.append(el("small", evidenceText(item), "evidence"));
    }
    return card;
  }));
  if (!cards.length) $("brief").append(note("No supported evidence for this matchup."));
}

function render(state) {
  renderTabs(state);
  renderSlots(state);
  renderImpact(state);
  renderBrief(state.brief);
  const active = view === games.length && !games.at(-1).winner;
  const editing = active && state.turn !== null;
  const turn = state.turn;
  $("turn").textContent = turn
    ? `Turn ${state.step + 1}/20 · ${nameById.get(state[turn[0]])} ${turn[1]}s`
    : state.series_winner ? `${nameById.get(state.series_winner)} wins the series` : "Draft complete";
  $("swap").disabled = !editing || state.step > 0;
  $("priority").disabled = $("swap").disabled;
  $("priority").value = games[view - 1].first_pick_side;
  $("locks").replaceChildren(...state.locks.map((champion) => el("span", champion.name)));
  if (!state.locks.length) $("locks").append(note("No champions carried over."));
  $("lock-count").textContent = state.locks.length;
  $("choose-action").hidden = !active;
  $("champion").disabled = !editing;
  $("apply").disabled = !editing;
  $("pass").disabled = !editing || turn[1] !== "ban";
  $("undo").disabled = !active || !state.step;
  $("result-controls").hidden = !state.can_finish;
  options($("champion"), [{id: "", name: "Select a legal champion"}, ...state.available]);
  options($("winner"), [state.blue, state.red].map((id) => ({id, name: nameById.get(id)})));
  $("next-options").hidden = !editing;
  const list = $("recommendations");
  list.replaceChildren(...state.recommendations.slice(0, 5).map((row) => {
    const button = el("button", undefined, "recommendation");
    button.type = "button";
    button.title = evidenceText(row.evidence);
    button.append(el("span", row.name), el("small", `n=${row.n}`), el("strong", delta(row.delta_pp), tone(row.delta_pp)));
    button.addEventListener("click", () => action(row.champion));
    return button;
  }));
}

async function update(proposed, selected) {
  if (busy) return;
  busy = true;
  $("workspace").setAttribute("aria-busy", "true");
  for (const id of ["team", "opponent", "competition", "patch"]) $(id).disabled = true;
  error();
  try {
    board = await request("/api/draft/evaluate", {
      team: $("team").value, opponent: $("opponent").value, patch: $("patch").value,
      games: proposed, view_game: selected, format_mode: "hard_fearless",
    });
    games = proposed;
    view = selected;
    render(board);
  } catch (problem) {
    error(problem.message);
  } finally {
    for (const id of ["team", "opponent", "competition", "patch"]) $(id).disabled = false;
    busy = false;
    $("workspace").setAttribute("aria-busy", "false");
  }
}

function fresh(blue = $("team").value) {
  return {blue, first_pick_side: "blue", actions: []};
}

function edit(mutator) {
  const proposed = structuredClone(games);
  mutator(proposed.at(-1), proposed);
  return update(proposed, proposed.length);
}

function action(champion) {
  return edit((game) => game.actions.push(champion));
}

function opponents(selected) {
  const region = $("competition").value;
  const opposing = catalog.teams.filter((team) => team.id !== $("team").value);
  const regional = opposing.filter((team) => !region || team.competitions.includes(region));
  if (!regional.length) $("competition").value = "";
  options($("opponent"), regional.length ? regional : opposing, selected);
}

function reset() {
  return update([fresh()], 1);
}

async function start() {
  const [health, teams] = await Promise.all([request("/api/health"), request("/api/teams")]);
  catalog = teams;
  for (const team of catalog.teams) nameById.set(team.id, team.name);
  const demo = health.mode === "synthetic";
  $("mode").lastChild.textContent = demo ? " Synthetic demo" : " Local GRID cache";
  $("source").textContent = demo ? "Practice with original synthetic teams and champions."
    : `${health.coverage.valid_series} pro series · ${health.coverage.valid_games.toLocaleString()} games · serving through ${health.model_as_of.slice(0, 10)}`;
  const regions = [...new Set(catalog.teams.flatMap((team) => team.competitions))].sort();
  const placeholders = (names, placeholder) => [{id: "", name: placeholder},
    ...names.map((name) => ({id: name, name}))];
  options($("competition"), placeholders(regions, "All competitions"));
  options($("patch"), placeholders(catalog.patches, "All patches"));
  options($("team"), catalog.teams, catalog.default_team);
  opponents(catalog.default_opponent);
  $("team").addEventListener("change", () => { opponents($("opponent").value); reset(); scouting(); });
  $("competition").addEventListener("change", () => {
    const previous = $("opponent").value;
    opponents(previous);
    if (previous !== $("opponent").value) reset();
    scouting();
  });
  $("opponent").addEventListener("change", () => { reset(); scouting(); });
  $("side").addEventListener("change", scouting);
  $("patch").addEventListener("change", () => { update(games || [fresh()], view || 1); scouting(); });
  $("swap").addEventListener("click", () => edit((game) => {
    game.blue = game.blue === $("team").value ? $("opponent").value : $("team").value;
  }));
  $("priority").addEventListener("change", () => edit((game) => { game.first_pick_side = $("priority").value; }));
  $("apply").addEventListener("click", () => {
    const champion = $("champion").value;
    if (champion) action(champion);
    else $("champion").focus();
  });
  $("pass").addEventListener("click", () => action(null));
  $("undo").addEventListener("click", () => edit((game) => game.actions.pop()));
  $("reset").addEventListener("click", reset);
  $("finish").addEventListener("click", () => edit((game, proposed) => {
    game.winner = $("winner").value;
    if (board.wins[game.winner] < 2) proposed.push(fresh(game.blue));
  }));
  await Promise.all([reset(), scouting()]);
}

start().catch((problem) => error(problem.message));
