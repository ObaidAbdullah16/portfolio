/* Page wiring: form <-> settings, render results. All maths lives in calc.js. */
(function () {
  "use strict";
  var C = window.BedrockCalc, P = window.BEDROCK_PRICES, CFG = window.CALC_CONFIG || {};
  var $ = function (id) { return document.getElementById(id); };
  var form = $("form");

  var LABELS = {
    system: "System prompt + tools", history: "Chat history re-sent", rag: "Retrieved documents (RAG)",
    user: "User messages", tools: "Agent tool results", output: "Answers (output)",
    guardrails: "Guardrails", vectorStore: "Vector store", embeddings: "Embeddings", logging: "Invocation logging"
  };
  var NUMBER_FIELDS = ["users", "conversationsPerUser", "turns", "systemTokens", "userTokens", "outputTokens",
    "historyWindow", "ragChunks", "chunkTokens", "vectorStoreCustom", "corpusTokens", "reindexPerMonth",
    "agentSteps", "toolResultTokens", "stepOutputTokens"];
  var PERCENT_FIELDS = ["retryRate", "batchShare"];
  var SELECT_FIELDS = ["model", "endpoint", "history", "vectorStore", "guardrailScope"];
  var GUARDS = ["contentFilters", "deniedTopics", "pii", "grounding"];
  var overrides = {};

  function money(v) {
    if (!isFinite(v)) return "-";
    var digits = v >= 100 ? 0 : v >= 1 ? 2 : v >= 0.01 ? 3 : 5;
    return "$" + v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  function int(v) { return Math.round(v).toLocaleString("en-US"); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }

  // ---- build the selects ---------------------------------------------------------
  var groups = {};
  P.models.forEach(function (m) { (groups[m.provider] = groups[m.provider] || []).push(m); });
  $("model").innerHTML = Object.keys(groups).map(function (g) {
    return '<optgroup label="' + esc(g) + '">' + groups[g].map(function (m) {
      return '<option value="' + esc(m.id) + '">' + esc(m.name) + " - $" + m.input + " / $" + m.output + "</option>";
    }).join("") + "</optgroup>";
  }).join("");
  $("vectorStore").innerHTML = Object.keys(P.extras.vectorStores).map(function (k) {
    return '<option value="' + k + '">' + esc(P.extras.vectorStores[k].name) + "</option>";
  }).join("");

  // ---- form <-> settings -------------------------------------------------------------
  function writeForm(s) {
    NUMBER_FIELDS.forEach(function (k) { $(k).value = s[k]; });
    PERCENT_FIELDS.forEach(function (k) { $(k).value = Math.round(s[k] * 1000) / 10; });
    SELECT_FIELDS.forEach(function (k) {
      $(k).value = s[k];
      if ($(k).selectedIndex < 0) $(k).selectedIndex = 0;  // unknown value from an old share link
    });
    $("caching").checked = s.caching;
    $("logging").checked = s.logging;
    GUARDS.forEach(function (g) { $("g_" + g).checked = s.guardrails[g]; });
    overrides = s.priceOverrides || {};
    syncOverrideFields();
  }

  function readForm() {
    var s = {};
    NUMBER_FIELDS.forEach(function (k) { s[k] = $(k).value; });
    PERCENT_FIELDS.forEach(function (k) { s[k] = Number($(k).value) / 100; });
    SELECT_FIELDS.forEach(function (k) { s[k] = $(k).value; });
    s.caching = $("caching").checked;
    s.logging = $("logging").checked;
    s.guardrails = {};
    GUARDS.forEach(function (g) { s.guardrails[g] = $("g_" + g).checked; });
    s.priceOverrides = overrides;
    return C.normalise(s);
  }

  function syncOverrideFields() {
    var o = overrides[$("model").value] || {};
    var m = C.findModel(P, $("model").value);
    $("ovInput").value = o.input !== undefined ? o.input : "";
    $("ovOutput").value = o.output !== undefined ? o.output : "";
    $("ovInput").placeholder = m.input;
    $("ovOutput").placeholder = m.output;
  }

  // ---- rendering -----------------------------------------------------------------
  function render() {
    var s = readForm();
    var r = C.estimate(s, P);
    var m = r.model;

    document.querySelectorAll(".dep").forEach(function (el) {
      var parts = el.getAttribute("data-dep").split("=");
      el.hidden = parts[1].split("|").indexOf($(parts[0]).value) < 0;
    });
    $("modelNote").textContent = (m.note || "") + (m.batch ? " Batch: yes." : " Batch: not available.");
    $("cacheNote").textContent = m.cacheRead === null
      ? "This model has no prompt caching on Bedrock."
      : (r.cached ? "Cached reads billed at " + Math.round(m.cacheRead * 100) + "% of input." :
        "Caching needs a prompt prefix of at least " + int(m.cacheMin) + " tokens on this model.");

    $("monthly").textContent = money(r.monthly);
    $("mobileTotal").innerHTML = "<span>Estimated bill</span> <b>" + money(r.monthly) + "/month</b> <span>" +
      (r.multiplier >= 1.05 ? r.multiplier.toFixed(1) + "x the naive estimate" : "") + "</span>";
    $("daily").textContent = money(r.daily);
    $("perConv").textContent = money(r.perConversation);
    $("perUser").textContent = money(r.perUserMonth);
    $("shock").innerHTML = r.multiplier >= 1.05
      ? "The pricing-page estimate (question + answer only) is <b>" + money(r.naiveMonthly) + "</b>. The real bill is <b>" +
        r.multiplier.toFixed(1) + "x</b> that."
      : "Close to the pricing-page estimate of " + money(r.naiveMonthly) + ".";

    var items = Object.keys(r.breakdown).map(function (k) { return { k: k, v: r.breakdown[k] }; })
      .filter(function (i) { return i.v > 0.0005; }).sort(function (a, b) { return b.v - a.v; });
    var max = items.length ? items[0].v : 1;
    $("bars").innerHTML = items.map(function (i, n) {
      var pct = r.monthly ? Math.round(i.v / r.monthly * 100) : 0;
      return '<div class="bar' + (n === 0 ? " top" : "") + '"><div class="bar-label"><span>' + esc(LABELS[i.k]) +
        "</span><b>" + money(i.v) + ' <small>' + pct + '%</small></b></div><div class="track"><div class="fill" style="width:' +
        Math.max(1.5, i.v / max * 100) + '%"></div></div></div>';
    }).join("") || '<p class="muted">Nothing billed yet.</p>';
    $("tokensLine").textContent = "The last message of a conversation sends " + int(r.tokens.lastTurnInput) +
      " input tokens. One conversation = " + int(r.tokens.callsPerConversation) + " model calls, " +
      int(r.tokens.inputPerConversation) + " input + " + int(r.tokens.outputPerConversation) + " output tokens. " +
      int(r.tokens.conversationsPerMonth) + " conversations a month.";

    var sv = C.savings(s, P);
    $("ideas").innerHTML = sv.ideas.slice(0, 5).map(function (i, n) {
      return "<li><div><b>" + esc(i.title) + "</b><span class=\"saves\">-" + money(i.saves) + "/month (" +
        Math.round(i.savesPct * 100) + "%)</span></div><p>" + esc(i.why) + '</p><button type="button" class="link" data-idea="' + n +
        '">Apply</button></li>';
    }).join("") || '<li class="muted">This setup is already lean. Watch the per-user cost as you grow.</li>';
    $("ideas").querySelectorAll("button[data-idea]").forEach(function (b) {
      b.addEventListener("click", function () { writeForm(sv.ideas[Number(b.getAttribute("data-idea"))].settings); render(); });
    });

    try { history.replaceState(null, "", "#s=" + C.encodeState(s)); } catch (e) { /* file:// in some browsers */ }
    lastResult = r;
    lastIdeas = sv.ideas;
  }
  var lastResult = null, lastIdeas = [];

  function summary() {
    var r = lastResult, s = r.settings;
    var top = Object.keys(r.breakdown).map(function (k) { return [LABELS[k], r.breakdown[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 3)
      .map(function (x) { return x[0] + " " + money(x[1]); }).join(", ");
    var lines = [
      "Amazon Bedrock cost estimate (prices checked " + P.checked + ")",
      "Model: " + r.model.name + " - " + int(s.users) + " users x " + s.conversationsPerUser + " conversations/day x " + s.turns + " messages",
      "Estimated monthly bill: " + money(r.monthly) + " (pricing-page estimate " + money(r.naiveMonthly) + ", " + r.multiplier.toFixed(1) + "x)",
      "Biggest items: " + top
    ];
    if (lastIdeas.length) lines.push("Top savings: " + lastIdeas.slice(0, 3).map(function (i) { return i.title + " (-" + money(i.saves) + ")"; }).join("; "));
    lines.push("Estimate only - verify on https://aws.amazon.com/bedrock/pricing/", location.href);
    return lines.join("\n");
  }

  function copy(text) {
    var done = function () { $("copied").textContent = "Copied"; setTimeout(function () { $("copied").textContent = ""; }, 2000); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, function () { prompt("Copy:", text); });
    else prompt("Copy:", text);
  }

  // ---- static parts ----------------------------------------------------------------
  function priceTable() {
    $("priceBasis").textContent = "Checked " + P.checked + ". " + P.basis + ". * = value assumed, not confirmed in a public source.";
    $("priceTable").innerHTML = "<tr><th>Model</th><th class=n>Input $/1M</th><th class=n>Output $/1M</th><th>Prompt caching</th><th>Batch -50%</th></tr>" +
      P.models.map(function (m) {
        return "<tr><td>" + esc(m.name) + "</td><td class=n>" + m.input + "</td><td class=n>" + m.output + "</td><td>" +
          (m.cacheRead === null ? "-" : Math.round(m.cacheRead * 100) + "% of input" + (m.assumed ? "*" : "") + ", min " + int(m.cacheMin)) +
          "</td><td>" + (m.batch ? "yes" : "-") + "</td></tr>";
      }).join("");
    var g = P.extras.guardrails;
    $("sources").innerHTML = "Guardrails: content filters $" + g.contentFilters + ", denied topics $" + g.deniedTopics + ", PII $" + g.pii +
      ", grounding $" + g.grounding + " per 1,000 text units (1,000 characters). Embeddings $" + P.extras.embeddingPerMTok +
      " per 1M tokens. Logs $" + P.extras.logsPerGB + "/GB. Sources: " +
      P.sources.map(function (x) { return '<a href="' + esc(x.url) + '" rel="noopener">' + esc(x.name) + "</a>"; }).join(" &middot; ");
    $("author").textContent = CFG.author || "";
    $("repo").href = CFG.repoUrl || "#";
    $("cta").href = CFG.ctaUrl || "#";
  }

  // ---- events --------------------------------------------------------------------------
  var timer = null;
  form.addEventListener("input", function (e) {
    if (e.target.id === "ovInput" || e.target.id === "ovOutput") {
      var id = $("model").value, o = overrides[id] || {};
      if ($("ovInput").value !== "") o.input = Number($("ovInput").value); else delete o.input;
      if ($("ovOutput").value !== "") o.output = Number($("ovOutput").value); else delete o.output;
      overrides[id] = o;
    }
    if (e.target.id === "model") syncOverrideFields();
    clearTimeout(timer);
    timer = setTimeout(render, 80);
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); });
  $("ovReset").addEventListener("click", function () { delete overrides[$("model").value]; syncOverrideFields(); render(); });
  document.querySelectorAll("[data-preset]").forEach(function (b) {
    b.addEventListener("click", function () {
      writeForm(C.normalise(C.PRESETS[b.getAttribute("data-preset")].values));
      render();
    });
  });
  $("copyLink").addEventListener("click", function () { copy(location.href); });
  $("copySummary").addEventListener("click", function () { copy(summary()); });

  // ---- start: shared link, or the first preset ----------------------------------------
  var m = /#s=([A-Za-z0-9_-]+)/.exec(location.hash);
  var start = (m && C.decodeState(m[1])) || C.normalise(C.PRESETS.support.values);
  priceTable();
  writeForm(start);
  render();
})();
